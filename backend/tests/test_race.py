import pytest
from fastapi.testclient import TestClient

from app.api.race import LiveLimiter, get_limiter
from app.config import Settings, get_settings
from app.engine.planner import plan
from app.llm.base import TurnResult
from app.main import app, get_llm_factory
from app.providers.base import BudgetedProvider
from app.race.core import RACE_BUDGETS, RACE_TRIP, load_recordings, optimum, recorded_run, run_planner
from app.sim import FareSimulator


class Done:
    async def stream_turn(self, system, tools, messages):
        yield TurnResult(content=[{"type": "text", "text": "done"}], stop_reason="end_turn")


@pytest.fixture
def client():
    limiter = LiveLimiter()
    app.dependency_overrides[get_settings] = lambda: Settings(
        fare_provider="simulator", llm_spend_ledger=None, race_live_per_hour=2
    )
    app.dependency_overrides[get_llm_factory] = lambda: lambda role: Done()
    app.dependency_overrides[get_limiter] = lambda: limiter
    yield TestClient(app)
    app.dependency_overrides.clear()


def race(client, **body):
    return client.post("/api/race", json=body)


async def test_final_step_is_what_the_planner_returns_and_regret_never_rises():
    opt = await optimum(RACE_TRIP, 0)
    for budget in (5, 10, 20):
        run = await run_planner("heuristic", RACE_TRIP, budget, 0, opt)
        sim = FareSimulator(0)
        res = await plan(RACE_TRIP.request, RACE_TRIP.prefs, BudgetedProvider(sim, budget), sim)
        assert run.steps[-1].best_utility == res.ranked[0].utility
        assert [s.searches_used for s in run.steps] == list(range(1, res.searches_used + 1))
        regrets = [s.regret for s in run.steps if s.regret is not None]
        assert all(r >= 0 for r in regrets) and regrets == sorted(regrets, reverse=True)
        assert all(s.reason for s in run.steps)


async def test_committed_heuristic_recordings_match_the_code():
    data = load_recordings()
    opt = await optimum(RACE_TRIP, data["seed"])
    assert data["optimum_utility"] == opt, "optimum changed: re-record with `uv run python -m app.race --placeholder`"
    for budget in RACE_BUDGETS:
        fresh = await run_planner("heuristic", RACE_TRIP, budget, data["seed"], opt, source="recorded")
        rec = recorded_run(data, "heuristic", budget, data["seed"])
        assert rec is not None and rec.steps == fresh.steps, f"stale recording at budget {budget}: re-record"


def test_placeholder_runs_are_always_labelled():
    data = load_recordings()
    for planner, runs in data["runs"].items():
        for budget, run in runs.items():
            if run["source"] == "placeholder":
                assert "not a real model" in run["note"], (planner, budget)
            if planner == "llm":
                assert run["source"] in ("placeholder", "recorded")


def test_replay_serves_recordings_with_their_labels(client):
    body = race(client, budget=10, planners=["llm", "heuristic"], mode="replay").json()
    assert body["optimum_utility"] == load_recordings()["optimum_utility"]
    llm, heur = body["planners"]["llm"], body["planners"]["heuristic"]
    if llm["source"] == "placeholder":
        assert "not a real model" in llm["note"]
    assert heur["source"] == "recorded" and heur["steps"][-1]["regret"] is not None


def test_replay_edges(client):
    assert race(client, budget=7, planners=["heuristic"], mode="replay").status_code == 200  # computed, deterministic
    assert race(client, budget=7, planners=["llm"], mode="replay").status_code == 404
    assert race(client, budget=10, planners=["nope"], mode="replay").status_code == 422
    trip = RACE_TRIP.request.model_dump(mode="json")
    assert race(client, budget=10, planners=["heuristic"], mode="replay", trip=trip).status_code == 422


def test_live_is_limited_per_client_and_xff_does_not_help(client):
    def live(headers):
        return client.post("/api/race", json={"budget": 3, "planners": ["heuristic"], "mode": "live"}, headers=headers)

    a = {"fly-client-ip": "1.1.1.1"}
    assert [live(a).status_code for _ in range(3)] == [200, 200, 429]
    assert live({"fly-client-ip": "1.1.1.1", "x-forwarded-for": "9.9.9.9"}).status_code == 429
    assert live({"fly-client-ip": "2.2.2.2"}).status_code == 200


def test_live_runs_a_custom_trip(client):
    trip = RACE_TRIP.request.model_copy(update={"return_from": None}).model_dump(mode="json")
    body = race(client, budget=5, planners=["heuristic", "llm"], mode="live", trip=trip).json()
    assert body["trip"] == "custom" and body["planners"]["llm"]["source"] == "live"
    assert body["planners"]["llm"]["steps"][0]["searches_used"] == 0  # the fake searched nothing


def test_limiter_window_slides():
    lim = LiveLimiter()
    assert lim.allow("x", 1, now=0) and not lim.allow("x", 1, now=10)
    assert lim.allow("x", 1, now=3600)
