"""F11-F15: the demo API. Fares come from the simulator; LLMs are injected fakes."""

import time

import pytest
from fastapi.testclient import TestClient

TRIP = {
    "origin": "EDI", "destination": "LIM", "return_from": "LPB",
    "depart_earliest": "2027-05-21", "depart_latest": "2027-05-24",
    "return_earliest": "2027-06-05", "return_latest": "2027-06-08",
    "search_budget": 20,
}


class FakeLLM:
    """Returns scripted replies in order; the last one repeats."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    async def stream_turn(self, system, tools, messages):
        from app.agent.llm import TurnResult

        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        yield TurnResult(content=[{"type": "text", "text": reply}], stop_reason="end_turn")


@pytest.fixture
def make_client():
    from app.config import Settings, get_settings
    from app.main import app, get_llm_factory

    def build(replies=("done",), **settings):
        fake = FakeLLM(replies)
        app.dependency_overrides[get_settings] = lambda: Settings(fare_provider="simulator", **settings)
        app.dependency_overrides[get_llm_factory] = lambda: (lambda role: fake)
        return TestClient(app), fake

    yield build
    app.dependency_overrides.clear()


def _plan(client, **prefs):
    r = client.post("/api/plan", json={"trip": TRIP, "preferences": prefs})
    assert r.status_code == 200, r.text
    return r.json()


def test_plan_and_rerank(make_client):
    client, _ = make_client()
    body = _plan(client, stopover_bonus=0)
    assert body["plan_id"] and body["ranked"]
    t0 = time.perf_counter()
    r = client.post("/api/rerank", json={"plan_id": body["plan_id"], "preferences": {"stopover_bonus": 400}})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    again = r.json()
    assert again["searches_used"] == body["searches_used"]
    assert again["ranked"][0]["itinerary"]["structure"] == "stopover"
    assert elapsed < 0.2


def test_trace(make_client):
    client, _ = make_client()
    body = _plan(client)
    trace = body["trace"]
    assert all(e["kind"] in {"cache_bound", "prune", "search"} for e in trace)
    searches = [e for e in trace if e["kind"] == "search"]
    assert len(searches) == body["searches_used"]
    assert [e["searches_used"] for e in searches] == list(range(1, len(searches) + 1))
    assert all(e.get("reason") for e in trace if e["kind"] == "prune")


def test_race(make_client):
    client, _ = make_client(race_live_per_hour=2)
    r = client.post("/api/race", json={"budget": 10, "planners": ["llm", "heuristic"], "mode": "replay"})
    assert r.status_code == 200, r.text
    planners = r.json()["planners"]
    for name in ("llm", "heuristic"):
        steps = planners[name]["steps"]
        assert steps and steps[-1]["searches_used"] <= 10
        # regret is null until a planner has a complete itinerary, then never increases
        regrets = [s["regret"] for s in steps if s["regret"] is not None]
        assert all(a >= b for a, b in zip(regrets, regrets[1:], strict=False)), "regret must never increase"
    assert planners["heuristic"]["steps"][-1]["regret"] is not None
    live = [client.post("/api/race", json={"budget": 5, "planners": ["llm", "heuristic"], "mode": "live"}).status_code
            for _ in range(3)]
    assert live[:2] == [200, 200] and live[2] == 429


def test_parse_preferences(make_client):
    client, _ = make_client(replies=['{"stopover_bonus": 150, "value_of_hour": 99999}'])
    r = client.post("/api/preferences/parse", json={"text": "I'd pay £150 for a night in Madrid, time is precious"})
    update = r.json()["preferences_update"]
    assert update["stopover_bonus"] == 150
    assert update["value_of_hour"] <= 200  # clamped to the valid range

    client, _ = make_client(replies=["{}"])
    assert client.post("/api/preferences/parse", json={"text": "what's the weather?"}).json()["preferences_update"] == {}

    client, _ = make_client(replies=["not json at all"])
    r = client.post("/api/preferences/parse", json={"text": "something"})
    assert r.status_code == 200 and r.json()["preferences_update"] == {}


def test_explain_grounded(make_client):
    client, fake = make_client(replies=["Madrid costs £5 and is best.", "Madrid with a night each way is the best value."])
    body = _plan(client)
    r = client.post("/api/explain", json={"plan_id": body["plan_id"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["retries"] == 1
    assert out["unsupported"] == []
    assert out["text"] == "Madrid with a night each way is the best value."
    assert fake.calls == 2
