"""F10: OpenAI behind the existing LLM protocol, per-role model routing, a spend cap.

The internal format stays Anthropic-style content blocks (text / tool_use / tool_result);
the adapter converts to and from the OpenAI Responses API.
"""

import json

import pytest


def test_tool_conversion():
    from app.agent.tools import TOOL_DEFS
    from app.llm.openai_llm import to_openai_tools

    tools = to_openai_tools(TOOL_DEFS)
    assert [t["name"] for t in tools] == [t["name"] for t in TOOL_DEFS]
    for ours, theirs in zip(TOOL_DEFS, tools, strict=True):
        assert theirs["type"] == "function"
        assert theirs["parameters"] == ours["input_schema"]
        assert theirs["description"] == ours["description"]


def test_message_and_response_conversion():
    from app.llm.openai_llm import from_openai_response, to_openai_input

    history = [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"role": "assistant", "content": [
            {"type": "text", "text": "searching"},
            {"type": "tool_use", "id": "c1", "name": "search_route", "input": {"origin": "EDI"}},
        ]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "[]"}]},
    ]
    items = to_openai_input(history)
    assert [i.get("type", "message") for i in items] == ["message", "message", "function_call", "function_call_output"]
    assert items[2]["call_id"] == "c1" and json.loads(items[2]["arguments"]) == {"origin": "EDI"}
    assert items[3]["call_id"] == "c1" and items[3]["output"] == "[]"

    response = {
        "output": [
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]},
            {"type": "function_call", "call_id": "c2", "name": "search_route", "arguments": '{"origin": "LHR"}'},
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    turn = from_openai_response(response)
    assert turn.stop_reason == "tool_use"
    assert turn.content == [
        {"type": "text", "text": "ok"},
        {"type": "tool_use", "id": "c2", "name": "search_route", "input": {"origin": "LHR"}},
    ]
    assert from_openai_response({"output": [{"type": "message", "content": [{"type": "output_text", "text": "done"}]}]}).stop_reason == "end_turn"


def test_model_routing():
    from app.config import Settings
    from app.llm.routing import model_for

    s = Settings(openai_model_parse="m-parse", openai_model_narrate="m-narrate", openai_model_baseline="m-baseline")
    assert model_for("parse", s) == "m-parse"
    assert model_for("narrate", s) == "m-narrate"
    assert model_for("baseline", s) == "m-baseline"
    with pytest.raises(ValueError):
        model_for("anything-else", s)


def test_spend_guard():
    from app.llm.spend import SpendCapReached, SpendGuard

    guard = SpendGuard(cap_usd=1.0)
    guard.record(cost_usd=0.6)
    guard.check()
    guard.record(cost_usd=0.5)
    with pytest.raises(SpendCapReached):
        guard.check()
