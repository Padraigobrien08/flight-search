import json
from datetime import date

from fastapi.testclient import TestClient

from app.agent.agent import run_agent, to_anthropic
from app.config import get_settings
from app.main import app, get_llm
from tests.fakes import ScriptedLLM

USER = {"id": "u1", "role": "user", "parts": [{"type": "text", "text": "Edinburgh to Lima late May, home from La Paz"}]}


def parse(lines: list[str]) -> list[dict | str]:
    out = []
    for block in "".join(lines).split("\n\n"):
        if not block.startswith("data: "):
            continue
        payload = block[len("data: "):]
        out.append(payload if payload == "[DONE]" else json.loads(payload))
    return out


async def collect(messages, llm, settings):
    return [c async for c in run_agent(messages, "chat-1", llm, settings, today=date(2026, 11, 6))]


async def test_agent_streams_text_tool_call_and_result(settings):
    llm = ScriptedLLM()
    chunks = parse(await collect([USER], llm, settings))
    types = [c["type"] if isinstance(c, dict) else c for c in chunks]
    assert types[0] == "start" and types[-2:] == ["finish", "[DONE]"]
    assert "tool-input-available" in types and "tool-output-available" in types
    out = next(c for c in chunks if isinstance(c, dict) and c["type"] == "tool-output-available")
    assert out["dynamic"] is True
    assert out["output"]["kind"] == "plan" and out["output"]["result"]["ranked"]
    assert json.loads(out["output"]["modelView"])["ranked"][0]["rank"] == 1
    # The second LLM call sees the tool result.
    assert llm.calls[1][-1]["content"][0]["type"] == "tool_result"


async def test_history_round_trip_includes_tool_results(settings):
    chunks = parse(await collect([USER], ScriptedLLM(), settings))
    tool_out = next(c for c in chunks if isinstance(c, dict) and c["type"] == "tool-output-available")
    assistant = {"id": "a1", "role": "assistant", "parts": [
        {"type": "step-start"},
        {"type": "text", "text": "Searching hubs and dates."},
        {"type": "dynamic-tool", "toolName": "plan_trip", "toolCallId": "toolu_1", "state": "output-available",
         "input": {"origin": "EDI"}, "output": tool_out["output"]},
        {"type": "text", "text": "Madrid is best."},
    ]}
    follow = {"id": "u2", "role": "user", "parts": [{"type": "text", "text": "and without Madrid?"}]}
    msgs = to_anthropic([USER, assistant, follow])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant", "user"]
    assert msgs[1]["content"][-1]["type"] == "tool_use"
    assert msgs[2]["content"][0]["type"] == "tool_result"
    assert json.loads(msgs[2]["content"][0]["content"])["ranked"]


def test_chat_endpoint_streams_sse(settings):
    app.dependency_overrides[get_llm] = lambda: ScriptedLLM()
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        client = TestClient(app)
        with client.stream("POST", "/api/chat", json={"id": "c1", "messages": [USER]}) as r:
            assert r.status_code == 200
            assert r.headers["x-vercel-ai-ui-message-stream"] == "v1"
            body = "".join(r.iter_text())
        assert body.rstrip().endswith("data: [DONE]")
    finally:
        app.dependency_overrides.clear()


def test_set_preferences_tool_changes_weights(settings):
    import asyncio

    from app.agent.tools import preferences_for, run_tool

    out = asyncio.run(run_tool("set_preferences", {"stopover_bonus": 200}, "chat-p", settings))
    assert out["ui"]["changed"] == {"stopover_bonus": 200.0}
    assert preferences_for("chat-p").stopover_bonus == 200
