import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.bench import BENCHMARK_TRIPS
from app.config import Settings, get_settings
from app.engine.llm_planner import llm_plan
from app.engine.planner import plan
from app.llm.base import TurnResult
from app.main import app
from app.models import Slice
from app.providers.base import BudgetedProvider
from app.sim import FareSimulator, SimConfig


def searches(res):
    return [e for e in res.trace if e.kind == "search"]


@pytest.mark.parametrize("trip", BENCHMARK_TRIPS, ids=[t.name for t in BENCHMARK_TRIPS])
async def test_one_numbered_search_event_per_budgeted_search(trip):
    for budget in (1, 3, 5, 10, 20):
        sim = FareSimulator(seed=1)
        res = await plan(trip.request, trip.prefs, BudgetedProvider(sim, budget), sim)
        evs = searches(res)
        assert len(evs) == res.searches_used, (trip.name, budget)
        assert [e.searches_used for e in evs] == list(range(1, res.searches_used + 1))
        assert all(e.reason and e.slices for e in evs)


async def test_every_prune_note_is_in_the_trace_and_bounds_come_before_hub_searches():
    trip = BENCHMARK_TRIPS[2]
    for budget in (6, 9, 20):
        sim = FareSimulator(seed=0)
        res = await plan(trip.request, trip.prefs, BudgetedProvider(sim, budget), sim)
        prunes = [(e.hub, e.reason) for e in res.trace if e.kind == "prune"]
        assert sorted(prunes) == sorted((p.hub, p.reason) for p in res.pruned)
        kinds = [e.kind for e in res.trace]
        hub_searches = [i for i, e in enumerate(res.trace) if e.kind == "search" and e.hub]
        last_bound = max(i for i, k in enumerate(kinds) if k == "cache_bound")
        assert all(last_bound < i for i in hub_searches)
        if budget >= 9:
            assert hub_searches, "budget 9+ leaves room for hub searches"
        assert {e.hub for e in res.trace if e.kind == "cache_bound"} == {"MAD", "LON", "PAR", "AMS", "LIS", "BCN"}


async def test_free_searches_leave_no_search_event():
    live = BudgetedProvider(FareSimulator(seed=0, config=SimConfig(latency_s=0.01)), budget=5)
    s = [Slice(origin="EDI", destination="MAD", date=date(2027, 5, 22))]
    await asyncio.gather(*(live.search(s, reason="dup") for _ in range(3)))  # in flight together
    await live.search(s, reason="memo")  # memoised
    assert [(e.searches_used, e.reason) for e in live.trace] == [(1, "dup")]


async def test_the_llm_planner_traces_its_searches_and_cache_lookups():
    calls = [
        {
            "type": "tool_use",
            "id": "a",
            "name": "cached_price",
            "input": {"origin": "EDI", "destination": "MAD", "date": "2027-05-21"},
        },
        {
            "type": "tool_use",
            "id": "b",
            "name": "search_route",
            "input": {"origin": "EDI", "destination": "MAD", "date": "2027-05-21"},
        },
    ]

    class Once:
        def __init__(self):
            self.done = False

        async def stream_turn(self, system, tools, messages):
            if self.done:
                yield TurnResult(content=[{"type": "text", "text": "ok"}], stop_reason="end_turn")
            else:
                self.done = True
                yield TurnResult(content=calls, stop_reason="tool_use")

    sim = FareSimulator(seed=0)
    res = await llm_plan(BENCHMARK_TRIPS[0].request, BENCHMARK_TRIPS[0].prefs, BudgetedProvider(sim, 3), sim, Once())
    kinds = [(e.kind, e.reason) for e in res.trace]
    assert ("search", "LLM search_route (b)") in kinds
    cache = [e for e in res.trace if e.kind == "cache_bound"]
    assert len(cache) == 1 and cache[0].bound and "EDI-MAD" in cache[0].reason
    assert len(searches(res)) == res.searches_used == 1


def test_the_api_returns_the_trace_and_rerank_keeps_it():
    app.dependency_overrides[get_settings] = lambda: Settings(fare_provider="simulator", llm_spend_ledger=None)
    try:
        c = TestClient(app)
        trip = BENCHMARK_TRIPS[2].request.model_dump(mode="json")
        body = c.post("/api/plan", json={"trip": trip}).json()
        assert len([e for e in body["trace"] if e["kind"] == "search"]) == body["searches_used"]
        again = c.post("/api/rerank", json={"plan_id": body["plan_id"], "preferences": {"value_of_hour": 30}}).json()
        assert again["trace"] == body["trace"]
    finally:
        app.dependency_overrides.clear()
