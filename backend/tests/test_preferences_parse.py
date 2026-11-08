import json
import math
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent.preferences import _json_object, clean, json_schema, parse_preferences
from app.config import Settings, get_settings
from app.llm.base import TurnResult
from app.llm.openai_llm import OpenAILLM
from app.llm.spend import SpendCapReached, SpendGuard
from app.main import app, get_llm_factory
from app.models import PREFERENCE_BOUNDS, Preferences


class Reply:
    def __init__(self, text):
        self.text, self.seen = text, []

    async def stream_turn(self, system, tools, messages):
        self.seen.append((system, messages))
        yield TurnResult(content=[{"type": "text", "text": self.text}], stop_reason="end_turn")


def test_clean_keeps_known_fields_clamps_and_explains_the_rest():
    r = clean(
        {
            "stopover_bonus": 150,
            "value_of_hour": 99999,
            "per_stop": -5,
            "max_stops": 2.6,
            "allow_same_day_self_transfer": True,
            "allow_airport_overnight": "yes",
            "hotel_cost_per_night": "cheap",
            "red_eye_arrival_penalty": True,
            "value_of_night_hour": math.nan,
            "favourite_colour": "blue",
            "long_connection_penalty": None,
        }
    )
    assert r.update == {
        "stopover_bonus": 150,
        "value_of_hour": 200,
        "per_stop": 0,
        "max_stops": 3,
        "allow_same_day_self_transfer": True,
    }
    assert r.clamped["value_of_hour"] == {"asked": 99999, "used": 200}
    assert set(r.ignored) == {
        "allow_airport_overnight",
        "hotel_cost_per_night",
        "red_eye_arrival_penalty",
        "value_of_night_hour",
        "favourite_colour",
    }
    Preferences(**r.update)  # always a valid update


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('```json\n{"per_stop": 50}\n```', {"per_stop": 50}),
        ('Sure! Here you go: {"per_stop": 50} Hope that helps.', {"per_stop": 50}),
        ("[1, 2]", None),
        ("nope", None),
    ],
)
def test_json_extraction(reply, expected):
    assert _json_object(reply) == expected


def test_schema_is_strict_and_covers_every_field():
    s = json_schema()
    assert s["additionalProperties"] is False and set(s["required"]) == set(Preferences.model_fields)
    assert all("null" in p["type"] for p in s["properties"].values())


def test_defaults_lie_inside_their_bounds():
    d = Preferences()
    for name, (lo, hi) in PREFERENCE_BOUNDS.items():
        assert lo <= getattr(d, name) <= hi, name


async def test_openai_gets_strict_structured_output_and_the_current_settings():
    calls = []

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def __aiter__(self):
            async def gen():
                if False:
                    yield None

            return gen()

        async def get_final_response(self):
            return {
                "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"stopover_bonus": 120}'}]}]
            }

    client = SimpleNamespace(responses=SimpleNamespace(stream=lambda **kw: calls.append(kw) or Stream()))
    llm = OpenAILLM("gpt-6-astra", SpendGuard(cap_usd=10), client=client)
    r = await parse_preferences("a night in Madrid is worth £120", llm, current=Preferences(per_stop=45))
    assert r.update == {"stopover_bonus": 120}
    fmt = calls[0]["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True and fmt["schema"] == json_schema()
    assert '"per_stop":45.0' in json.dumps(calls[0]["input"]).replace(" ", "").replace('\\"', '"')
    assert llm.text_format is None, "with_json_schema must not change the shared LLM"


@pytest.fixture
def client():
    def build(llm):
        roles = []
        app.dependency_overrides[get_settings] = lambda: Settings(llm_spend_ledger=None)
        app.dependency_overrides[get_llm_factory] = lambda: lambda role: roles.append(role) or llm
        return TestClient(app), roles

    yield build
    app.dependency_overrides.clear()


def test_endpoint_uses_the_parse_model_and_reports_clamping(client):
    c, roles = client(Reply('{"value_of_hour": 500, "colour": "red"}'))
    body = c.post("/api/preferences/parse", json={"text": "time is everything"}).json()
    assert roles == ["parse"]
    assert body["preferences_update"] == {"value_of_hour": 200}
    assert body["clamped"] == {"value_of_hour": {"asked": 500, "used": 200}} and "colour" in body["ignored"]


def test_endpoint_edges(client):
    llm = Reply("{}")
    c, roles = client(llm)
    assert c.post("/api/preferences/parse", json={"text": "   "}).json()["preferences_update"] == {}
    assert roles == [] and llm.seen == []
    assert c.post("/api/preferences/parse", json={"text": "x" * 1001}).status_code == 422
    assert c.post("/api/preferences/parse", json={"text": "hi", "current": {"max_stops": "lots"}}).status_code == 422

    class Capped:
        async def stream_turn(self, system, tools, messages):
            raise SpendCapReached("LLM spend this month $20.00 has reached the $20.00 cap")
            yield  # pragma: no cover

    c, _ = client(Capped())
    r = c.post("/api/preferences/parse", json={"text": "I hate layovers"})
    assert r.status_code == 503 and "sliders still work" in r.json()["detail"]


def test_bounds_endpoint(client):
    c, _ = client(Reply("{}"))
    b = c.get("/api/preferences/bounds").json()
    assert b["value_of_hour"] == {"min": 0, "max": 200, "default": 10.0}
    assert set(b) == set(PREFERENCE_BOUNDS)
