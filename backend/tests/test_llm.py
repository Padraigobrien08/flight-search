import pathlib
import re
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.llm import llm_factory, model_for
from app.llm.openai_llm import OpenAILLM, from_openai_response, to_openai_input
from app.llm.spend import PRICES, SpendCapReached, SpendGuard, UnpricedModel, cost_usd

FINAL = {
    "status": "completed",
    "output": [
        {"type": "reasoning", "id": "rs_1", "encrypted_content": "opaque", "summary": []},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hello there"}]},
    ],
    "usage": {"input_tokens": 1000, "input_tokens_details": {"cached_tokens": 400}, "output_tokens": 200},
}


class FakeStream:
    def __init__(self, events, final):
        self.events, self.final = events, final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for e in self.events:
                yield e

        return gen()

    async def get_final_response(self):
        return self.final


class FakeClient:
    def __init__(self, final=FINAL):
        self.calls: list[dict] = []
        self.final = final
        self.responses = SimpleNamespace(stream=self.stream)

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        events = [
            SimpleNamespace(type="response.output_item.added", item=SimpleNamespace(type="reasoning")),
            SimpleNamespace(type="response.output_item.added", item=SimpleNamespace(type="message")),
            SimpleNamespace(type="response.output_text.delta", delta="Hello "),
            SimpleNamespace(type="response.output_text.delta", delta="there"),
        ]
        return FakeStream(events, self.final)


async def collect(llm, messages=None, tools=None):
    return [x async for x in llm.stream_turn("system", tools or [], messages or [{"role": "user", "content": "hi"}])]


async def test_stream_turn_streams_text_records_cost_and_keeps_reasoning():
    guard, client = SpendGuard(cap_usd=10), FakeClient()
    llm = OpenAILLM("gpt-6-astra", guard, reasoning_effort="high", client=client)
    out = await collect(llm, tools=[{"name": "t", "description": "d", "input_schema": {"type": "object"}}])
    assert out[:3] == ["", "Hello ", "there"]
    result = out[-1]
    assert result.stop_reason == "end_turn"
    assert result.content[0]["type"] == "openai_reasoning"
    assert result.content[1] == {"type": "text", "text": "Hello there"}
    call = client.calls[0]
    assert call["store"] is False and call["instructions"] == "system"
    assert call["reasoning"] == {"effort": "high"} and call["include"] == ["reasoning.encrypted_content"]
    assert call["tools"][0]["type"] == "function"
    # 600 fresh x $10 + 400 cached x $1 + 200 out x $50, per 1M tokens.
    assert guard.spent() == pytest.approx((600 * 10 + 400 * 1 + 200 * 50) / 1e6)
    # Reasoning goes back to the API verbatim on the next turn.
    items = to_openai_input([{"role": "assistant", "content": result.content}])
    assert items[0] == FINAL["output"][0]


async def test_no_request_is_sent_once_the_cap_is_reached():
    guard, client = SpendGuard(cap_usd=1.0), FakeClient()
    guard.record(1.0)
    with pytest.raises(SpendCapReached):
        await collect(OpenAILLM("gpt-6-astra", guard, client=client))
    assert client.calls == []


async def test_a_model_without_a_price_is_refused_before_any_request():
    client = FakeClient()
    with pytest.raises(UnpricedModel):
        await collect(OpenAILLM("some-unpriced-model", SpendGuard(cap_usd=100), client=client))
    assert client.calls == []
    with pytest.raises(UnpricedModel):
        cost_usd("some-unpriced-model", {"input_tokens": 1})


def test_spend_resets_each_month_and_survives_a_restart(tmp_path):
    now = [datetime(2026, 11, 30, 23, 0, tzinfo=UTC)]
    ledger = tmp_path / "spend.json"
    a = SpendGuard(cap_usd=1.0, ledger_path=ledger, clock=lambda: now[0])
    a.record(1.2)
    assert a.reached()
    b = SpendGuard(cap_usd=1.0, ledger_path=ledger, clock=lambda: now[0])  # a restart
    with pytest.raises(SpendCapReached):
        b.check()
    now[0] = datetime(2026, 12, 1, 0, 1, tzinfo=UTC)
    b.check()
    assert b.spent() == 0.0


def test_input_conversion_edge_cases():
    items = to_openai_input(
        [
            {"role": "user", "content": "plain string"},
            {"role": "assistant", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "c1", "content": [{"type": "text", "text": "x"}]}],
            },
        ]
    )
    assert items[0] == {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "plain string"}]}
    assert [p["text"] for p in items[1]["content"]] == ["a", "b"]
    assert items[2] == {"type": "function_call_output", "call_id": "c1", "output": "x"}


def test_response_conversion_edge_cases():
    truncated = from_openai_response(
        {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": []}
    )
    assert truncated.stop_reason == "max_tokens"
    bad = from_openai_response(
        {"output": [{"type": "function_call", "call_id": "c", "name": "n", "arguments": "{not json"}]}
    )
    assert bad.content[0]["input"] == {"_unparsed_arguments": "{not json"}
    sdk_like = SimpleNamespace(model_dump=lambda exclude_none=True: FINAL)
    assert from_openai_response(sdk_like).usage == {"input_tokens": 1000, "cached_tokens": 400, "output_tokens": 200}


def test_factory_routes_roles_and_needs_a_key():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm_factory(Settings(openai_api_key=None))
    s = Settings(openai_api_key="sk-test", openai_model_parse="gpt-6-astra", llm_spend_ledger=None)
    make = llm_factory(s)
    assert make("baseline").model == model_for("baseline", s)
    assert make("baseline").reasoning_effort == "high"
    with pytest.raises(ValueError):
        make("chat")


def test_default_models_are_priced():
    s = Settings()
    for role in ("parse", "narrate", "baseline"):
        assert model_for(role, s) in PRICES


def test_no_vendor_sdk_outside_app_llm():
    app = pathlib.Path(__file__).resolve().parents[1] / "app"
    pattern = re.compile(r"^\s*(from|import)\s+(openai|anthropic)\b", re.M)
    offenders = [
        str(p.relative_to(app)) for p in app.rglob("*.py") if p.parent.name != "llm" and pattern.search(p.read_text())
    ]
    assert offenders == []
