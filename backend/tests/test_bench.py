import pytest

from app.bench import BENCHMARK_TRIPS, PLANNERS, RegretBelowZero, run_benchmark
from app.engine.planner import plan


def test_trip_names_are_unique_and_cover_both_shapes():
    names = [t.name for t in BENCHMARK_TRIPS]
    assert len(names) == len(set(names)) >= 10
    assert {t.request.return_from for t in BENCHMARK_TRIPS} == {"LPB", None}


def test_unknown_planner_is_rejected():
    with pytest.raises(ValueError, match="unknown planners"):
        run_benchmark(["nope"], [5], [0], BENCHMARK_TRIPS[:1])


def test_a_planner_that_finds_nothing_is_recorded_not_dropped(monkeypatch):
    async def empty(req, prefs, live, cache):
        res = await plan(req, prefs, live, cache)
        return res.model_copy(update={"ranked": []})

    monkeypatch.setitem(PLANNERS, "empty", empty)
    [rec] = run_benchmark(["empty"], [5], [0], BENCHMARK_TRIPS[:1])
    assert rec["found"] is False and rec["best_utility"] is None and rec["regret"] is None
    assert rec["optimum_utility"] is not None


def test_beating_the_optimum_raises(monkeypatch):
    async def cheat(req, prefs, live, cache):
        res = await plan(req, prefs, live, cache)
        top = res.ranked[0].model_copy(update={"utility": res.ranked[0].utility + 10_000})
        return res.model_copy(update={"ranked": [top]})

    monkeypatch.setitem(PLANNERS, "cheat", cheat)
    with pytest.raises(RegretBelowZero, match="extend app/engine/space.py"):
        run_benchmark(["cheat"], [5], [0], BENCHMARK_TRIPS[:1])
