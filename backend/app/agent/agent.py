"""The chat agent: UI messages in, UI message stream out."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from app.agent import stream as ui
from app.agent.llm import LLM, TurnResult
from app.agent.tools import TOOL_DEFS, run_tool
from app.config import Settings

MAX_STEPS = 6

SYSTEM_PROMPT = """You help one person find the best flights for a trip, judged by what they value, not only price.

Today is {today}.

How to work:
- Turn the request into plan_trip arguments: IATA codes, and departure/return date windows. "Back the week of 6 June" means a return window around that week. If the trip ends somewhere other than where it starts (e.g. fly into Lima, home from La Paz), set return_from.
- If origin, destination or rough dates are missing, ask one short question. Otherwise search straight away.
- If the person states a trade-off ("I'd pay more to avoid overnight connections", "I'd love a night in Madrid"), call set_preferences first, with values in GBP.
- After plan_trip, explain the top options against each other in plain sentences: what the extra money buys (a night in a hub, hours saved, a protected connection) or what the cheaper option costs in time and risk. One or two sentences per option, then a recommendation.
- Only use numbers that appear in tool results. Never invent prices, times or durations. Say when a price is an estimate (hotel nights, airport transfers).
- Mention self-transfers on separate tickets plainly: a missed connection is the traveller's problem.
- The results are already shown to the user as cards, so don't repeat every leg; focus on the trade-offs.
"""


def _text_of(part: dict) -> str:
    return part.get("text", "") if part.get("type") == "text" else ""


def to_anthropic(messages: list[dict]) -> list[dict]:
    """Convert AI SDK UI messages into Anthropic messages, including tool calls."""
    out: list[dict] = []

    def push(role: str, blocks: list[dict]) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for msg in messages:
        role = msg.get("role")
        parts = msg.get("parts") or []
        if role == "user":
            push("user", [{"type": "text", "text": t} for t in (_text_of(p) for p in parts) if t])
            continue
        if role != "assistant":
            continue
        assistant: list[dict] = []
        results: list[dict] = []
        for p in parts:
            ptype = p.get("type", "")
            is_tool = ptype == "dynamic-tool" or ptype.startswith("tool-")
            if is_tool and p.get("state") in ("output-available", "output-error"):
                name = p.get("toolName") or ptype.removeprefix("tool-")
                assistant.append({"type": "tool_use", "id": p["toolCallId"], "name": name, "input": p.get("input") or {}})
                output = p.get("output")
                content = (output or {}).get("modelView") if isinstance(output, dict) else None
                if p.get("state") == "output-error":
                    content = p.get("errorText", "tool failed")
                results.append({"type": "tool_result", "tool_use_id": p["toolCallId"],
                                "content": content if isinstance(content, str) else json.dumps(output)})
            elif ptype == "text" and p.get("text"):
                if results:  # text after tool calls starts a new assistant turn
                    push("assistant", assistant)
                    push("user", results)
                    assistant, results = [], []
                assistant.append({"type": "text", "text": p["text"]})
        push("assistant", assistant)
        push("user", results)
    return out


async def run_agent(messages: list[dict], chat_id: str, llm: LLM, settings: Settings,
                    today: date | None = None) -> AsyncIterator[str]:
    history = to_anthropic(messages)
    system = SYSTEM_PROMPT.format(today=(today or date.today()).isoformat())
    yield ui.start(f"msg-{uuid.uuid4().hex[:12]}")
    try:
        for _ in range(MAX_STEPS):
            yield ui.start_step()
            text_id: str | None = None
            result: TurnResult | None = None
            async for item in llm.stream_turn(system, TOOL_DEFS, history):
                if isinstance(item, TurnResult):
                    result = item
                    break
                if item == "":
                    if text_id:
                        yield ui.text_end(text_id)
                    text_id = None
                    continue
                if text_id is None:
                    text_id = f"txt-{uuid.uuid4().hex[:8]}"
                    yield ui.text_start(text_id)
                yield ui.text_delta(text_id, item)
            if text_id:
                yield ui.text_end(text_id)
            if result is None:
                break

            history.append({"role": "assistant", "content": result.content})
            tool_uses = [b for b in result.content if b.get("type") == "tool_use"]
            if result.stop_reason != "tool_use" or not tool_uses:
                yield ui.finish_step()
                break

            tool_results: list[dict[str, Any]] = []
            for block in tool_uses:
                yield ui.tool_input(block["id"], block["name"], block.get("input", {}))
                try:
                    out = await run_tool(block["name"], block.get("input", {}), chat_id, settings)
                    yield ui.tool_output(block["id"], {**out["ui"], "modelView": out["model"]})
                    tool_results.append({"type": "tool_result", "tool_use_id": block["id"], "content": out["model"]})
                except Exception as e:  # report tool failures to both the user and the model
                    yield ui.tool_error(block["id"], str(e))
                    tool_results.append({"type": "tool_result", "tool_use_id": block["id"],
                                         "content": f"Tool failed: {e}", "is_error": True})
            history.append({"role": "user", "content": tool_results})
            yield ui.finish_step()
        yield ui.finish()
    except Exception as e:  # surface model/API errors in the chat instead of a dead stream
        yield ui.error(f"{type(e).__name__}: {e}")
        yield ui.finish("error")
    yield ui.DONE
