import json
import time

import pytest

from app.bench import BENCHMARK_TRIPS, run_benchmark
from app.engine.llm_planner import TOOLS, llm_plan
from app.engine.space import candidates
from app.llm.base import TurnResult
from app.providers.base import BudgetedProvider
from app.sim import FareSimulator, SimConfig, exhaustive_best

TRIP = BENCHMARK_TRIPS[0]  # open-jaw, fixed dates


def call(i, name, **args):
    return {"type": "tool_use", "id": f"c{i}", "name": name, "input": args}


class Scripted:
    """Plays a fixed list of turns (each a list of tool calls), then stops. Records what it was sent."""

    def __init__(self, turns, usage=None):
        self.turns, self.seen, self.usage = list(turns), [], usage or {}

    async def stream_turn(self, system, tools, messages):
        self.seen.append(json.loads(json.dumps(messages)))
        if self.turns:
            yield TurnResult(content=self.turns.pop(0), stop_reason="tool_use", usage=self.usage)
        else:
            yield TurnResult(content=[{"type": "text", "text": "done"}], stop_reason="end_turn", usage=self.usage)


def results_of(llm, turn):
    """The tool results the LLM saw after its `turn`-th turn (0-based)."""
    msg = llm.seen[turn + 1][-1]
    return [json.loads(b["content"]) for b in msg["content"]]


class Recorder:
    def __init__(self, sim):
        self.sim, self.name, self.keys = sim, sim.name, []

    async def search(self, slices, max_results=5):
        self.keys.append(slices)
        return await self.sim.search(slices, max_results)


def as_args(slices):
    args = {"origin": slices[0].origin, "destination": slices[0].destination, "date": slices[0].date.isoformat()}
    if len(slices) > 1:
        args |= {
            "return_date": slices[1].date.isoformat(),
            "return_origin": slices[1].origin,
            "return_destination": slices[1].destination,
        }
    return args


async def test_searching_everything_the_exhaustive_search_does_reaches_the_optimum():
    sim = FareSimulator(seed=2)
    rec = Recorder(sim)
    await candidates(rec, TRIP.request, TRIP.prefs)
    calls = [call(i, "search_route", **as_args(s)) for i, s in enumerate(rec.keys)]
    live = BudgetedProvider(sim, len(calls))
    res = await llm_plan(TRIP.request, TRIP.prefs, live, sim, Scripted([calls]))
    best = await exhaustive_best(FareSimulator(seed=2), TRIP.request, TRIP.prefs)
    # Note: the LLM's searches return the top 5 tickets, the exhaustive search all of them.
    assert res.ranked and res.ranked[0].utility <= best.utility + 1e-6
    assert best.utility - res.ranked[0].utility < 1.0, "assembly must cover the candidate space"


async def test_a_sensible_search_finds_a_hub_itinerary_and_spends_only_what_it_uses():
    req = TRIP.request
    turns = [
        [call(0, "cached_price", origin="EDI", destination="MAD", date="2027-05-21", return_date="2027-06-07")],
        [
            call(
                1,
                "search_route",
                origin="MAD",
                destination="LIM",
                date="2027-05-22",
                return_date="2027-06-06",
                return_origin="LPB",
            ),
            call(2, "search_route", origin="EDI", destination="MAD", date="2027-05-21", return_date="2027-06-07"),
        ],
        [call(3, "best_so_far")],
    ]
    sim = FareSimulator(seed=0)
    llm = Scripted(turns, usage={"input_tokens": 100, "cached_tokens": 10, "output_tokens": 20})
    res = await llm_plan(req, TRIP.prefs, BudgetedProvider(sim, 10), sim, llm)
    assert res.searches_used == 2
    assert res.ranked[0].itinerary.hub == "MAD"
    [cached] = results_of(llm, 0)
    assert cached["cached_lowest_gbp"] > 0
    [best] = results_of(llm, 2)
    assert best["best"][0]["utility"] == res.ranked[0].utility and best["remaining_budget"] == 8
    assert res.llm_usage == {"input_tokens": 400, "cached_tokens": 40, "output_tokens": 80, "turns": 4}
    # The task names the hubs, the structures and the budget.
    task = llm.seen[0][0]["content"][0]["text"]
    assert "Madrid" in task and "Search budget: 10" in task and "LPB fix" in task


async def test_over_budget_bad_args_and_unknown_tools_become_tool_errors():
    turns = [
        [
            call(0, "search_route", origin="EDI", destination="MAD", date="2027-05-21"),
            call(1, "search_route", origin="EDI", destination="LHR", date="2027-05-21"),
            call(2, "search_route", origin="EDI"),
            call(3, "teleport"),
        ]
    ]
    sim = FareSimulator(seed=0)
    llm = Scripted(turns)
    res = await llm_plan(TRIP.request, TRIP.prefs, BudgetedProvider(sim, 1), sim, llm)
    ok, over, bad, unknown = results_of(llm, 0)
    assert "tickets" in ok and ok["remaining_budget"] == 0
    assert over == {"error": "search budget used up", "remaining_budget": 0}
    assert bad["error"].startswith("bad arguments")
    assert "unknown tool" in unknown["error"]
    assert res.searches_used == 1


async def test_tool_calls_in_one_turn_run_concurrently():
    sim = FareSimulator(seed=0, config=SimConfig(latency_s=0.05))
    dests = ["MAD", "LHR", "CDG", "AMS", "LIS", "BCN"]
    turn = [call(i, "search_route", origin="EDI", destination=d, date="2027-05-21") for i, d in enumerate(dests)]
    t0 = time.perf_counter()
    res = await llm_plan(TRIP.request, TRIP.prefs, BudgetedProvider(sim, 10), sim, Scripted([turn]))
    assert res.searches_used == 6
    assert time.perf_counter() - t0 < 0.5 * 6 * 0.05


async def test_a_runaway_llm_is_stopped():
    class Forever:
        async def stream_turn(self, system, tools, messages):
            yield TurnResult(content=[call(0, "best_so_far")], stop_reason="tool_use")

    sim = FareSimulator(seed=0)
    res = await llm_plan(TRIP.request, TRIP.prefs, BudgetedProvider(sim, 2), sim, Forever(), max_turns=4)
    assert res.notes == ["stopped after 4 LLM turns"] and res.llm_usage["turns"] == 4


def test_tools_offered_and_benchmark_wiring():
    assert [t["name"] for t in TOOLS] == ["search_route", "cached_price", "best_so_far"]
    recs = run_benchmark(["llm", "heuristic"], [5], [0], BENCHMARK_TRIPS[:1], llm_factory=lambda: Scripted([]))
    llm_rec = next(r for r in recs if r["planner"] == "llm")
    assert llm_rec["searches_used"] == 0 and llm_rec["found"] is False and llm_rec["llm_turns"] == 1


def test_the_default_llm_needs_a_key(monkeypatch):
    from app.config import get_settings

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            run_benchmark(["llm"], [5], [0], BENCHMARK_TRIPS[:1])
    finally:
        get_settings.cache_clear()
