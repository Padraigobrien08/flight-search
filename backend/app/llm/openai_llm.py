"""OpenAI Responses API behind the LLM protocol. The only module that imports the OpenAI SDK.

Internal content blocks <-> Responses API items:
    text (user)        <-> message, input_text
    text (assistant)   <-> message, output_text
    tool_use           <-> function_call (arguments as a JSON string)
    tool_result        <-> function_call_output
    openai_reasoning   <-> reasoning item, passed back verbatim (encrypted) so a reasoning
                           model keeps its chain of thought across tool calls with store=False
"""

from __future__ import annotations

import itertools
import json
from typing import Any

from app.llm.base import TurnResult
from app.llm.spend import SpendGuard, cost_usd


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {"type": "function", "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}
        for t in tools
    ]


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return json.dumps(content)


def _item(block: dict) -> dict | None:
    """One non-text content block as a Responses API input item."""
    kind = block.get("type")
    if kind == "tool_use":
        return {
            "type": "function_call",
            "call_id": block["id"],
            "name": block["name"],
            "arguments": json.dumps(block.get("input") or {}),
        }
    if kind == "tool_result":
        return {
            "type": "function_call_output",
            "call_id": block["tool_use_id"],
            "output": _text_of(block.get("content")),
        }
    if kind == "openai_reasoning":
        return block["item"]
    return None


def to_openai_input(messages: list[dict]) -> list[dict]:
    """Internal history (role + content blocks) to Responses API input items, keeping block order.

    Consecutive text blocks in one message become one message item.
    """
    items: list[dict] = []
    for msg in messages:
        role, content = msg["role"], msg["content"]
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        text_type = "output_text" if role == "assistant" else "input_text"
        for is_text, run in itertools.groupby(content, key=lambda b: b.get("type") == "text"):
            if is_text:
                parts = [{"type": text_type, "text": b["text"]} for b in run]
                items.append({"type": "message", "role": role, "content": parts})
            else:
                items.extend(i for i in map(_item, run) if i is not None)
    return items


def _as_dict(obj: Any) -> dict:
    return obj if isinstance(obj, dict) else obj.model_dump(exclude_none=True)


def from_openai_response(response: Any) -> TurnResult:
    """A Responses API response (dict or SDK object) to internal content blocks and a stop reason."""
    r = _as_dict(response)
    content: list[dict] = []
    for item in r.get("output") or []:
        item = _as_dict(item)
        kind = item.get("type")
        if kind == "message":
            for part in item.get("content") or []:
                if part.get("type") == "output_text" and part.get("text"):
                    content.append({"type": "text", "text": part["text"]})
        elif kind == "function_call":
            try:
                args = json.loads(item.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_unparsed_arguments": item.get("arguments")}
            content.append({"type": "tool_use", "id": item["call_id"], "name": item["name"], "input": args})
        elif kind == "reasoning":
            content.append({"type": "openai_reasoning", "item": item})
    if any(b["type"] == "tool_use" for b in content):
        stop = "tool_use"
    elif r.get("status") == "incomplete" and (r.get("incomplete_details") or {}).get("reason") == "max_output_tokens":
        stop = "max_tokens"
    else:
        stop = "end_turn"
    u = r.get("usage") or {}
    usage = {
        "input_tokens": u.get("input_tokens", 0),
        "cached_tokens": (u.get("input_tokens_details") or {}).get("cached_tokens", 0),
        "output_tokens": u.get("output_tokens", 0),
    }
    return TurnResult(content=content, stop_reason=stop, usage=usage)


class OpenAILLM:
    """Streams one turn from the Responses API, inside a spend cap."""

    def __init__(
        self,
        model: str,
        guard: SpendGuard,
        api_key: str | None = None,
        reasoning_effort: str | None = None,
        max_output_tokens: int = 16_000,
        client: Any = None,
    ):
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key)
        self.client = client
        self.model = model
        self.guard = guard
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens

    async def stream_turn(self, system, tools, messages):  # noqa: ANN001, ANN201
        self.guard.check_priced(self.model)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": system,
            "input": to_openai_input(messages),
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
        if self.reasoning_effort:
            kwargs["reasoning"] = {"effort": self.reasoning_effort}
            kwargs["include"] = ["reasoning.encrypted_content"]
        async with self.client.responses.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "response.output_item.added" and getattr(event.item, "type", None) == "message":
                    yield ""  # marks a new text block
                elif event.type == "response.output_text.delta":
                    yield event.delta
            final = await stream.get_final_response()
        result = from_openai_response(final)
        self.guard.record(cost_usd(self.model, result.usage))
        yield result
