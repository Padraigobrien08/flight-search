"""Run planners against the simulator and score them by exact regret.

One record per (planner, trip, budget, seed). The optimum for each (trip, seed)
is computed once by exhaustive search and shared by every planner and budget.
Everything but `wall_ms` is deterministic for code planners; the `llm` planner
is as deterministic as its model.

A run that finds no itinerary has `found: false` and null `best_utility` and
`regret` (JSON can't carry inf); reports must count those, not drop them.
Negative regret means a planner built an itinerary outside the candidate
space, so it raises instead of being reported.

LLM-driven planners get a fresh LLM per run from `llm_factory` (no arguments).
By default that is the "baseline" role from settings: real API calls, real
spend, inside the spend cap.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from app.bench.trips import BenchTrip
from app.engine.llm_planner import llm_plan
from app.engine.planner import plan
from app.llm.base import LLM
from app.models import PlanResult, Preferences, TripRequest
from app.providers.base import BudgetedProvider, CachedFareProvider
from app.sim import FareSimulator, SimConfig, exhaustive_best

Planner = Callable[[TripRequest, Preferences, BudgetedProvider, CachedFareProvider], Awaitable[PlanResult]]
LLMPlanner = Callable[[TripRequest, Preferences, BudgetedProvider, CachedFareProvider, LLM], Awaitable[PlanResult]]

PLANNERS: dict[str, Planner] = {"heuristic": plan}
LLM_PLANNERS: dict[str, LLMPlanner] = {"llm": llm_plan}


def all_planners() -> list[str]:
    return sorted({*PLANNERS, *LLM_PLANNERS})


class RegretBelowZero(AssertionError):
    pass


def default_llm_factory() -> Callable[[], LLM]:
    from app.config import get_settings
    from app.llm import llm_factory

    make = llm_factory(get_settings())
    return lambda: make("baseline")


async def run_benchmark_async(
    planners: list[str],
    budgets: list[int],
    seeds: list[int],
    trips: list[BenchTrip],
    config: SimConfig | None = None,
    sim_label: str = "realistic",
    llm_factory: Callable[[], LLM] | None = None,
) -> list[dict]:
    unknown = [p for p in planners if p not in PLANNERS and p not in LLM_PLANNERS]
    if unknown:
        raise ValueError(f"unknown planners {unknown}; known: {all_planners()}")
    if llm_factory is None and any(p in LLM_PLANNERS for p in planners):
        llm_factory = default_llm_factory()
    records: list[dict] = []
    for trip in trips:
        for seed in seeds:
            best = await exhaustive_best(FareSimulator(seed, config), trip.request, trip.prefs)
            if best is None:
                raise ValueError(f"trip {trip.name} has no feasible itinerary at seed {seed}")
            for name in planners:
                for budget in budgets:
                    sim = FareSimulator(seed, config)  # fresh per run: nothing carries over between planners
                    live = BudgetedProvider(sim, budget)
                    t0 = time.perf_counter()
                    if name in LLM_PLANNERS:
                        assert llm_factory is not None
                        res = await LLM_PLANNERS[name](trip.request, trip.prefs, live, sim, llm_factory())
                    else:
                        res = await PLANNERS[name](trip.request, trip.prefs, live, sim)
                    wall_ms = (time.perf_counter() - t0) * 1000
                    found = res.ranked[0].utility if res.ranked else None
                    regret = None if found is None else round(best.utility - found, 2)
                    if regret is not None and regret < -1e-6:
                        raise RegretBelowZero(
                            f"{name} found {res.ranked[0].itinerary.id} on {trip.name} seed {seed}, "
                            f"£{-regret:.2f} better than the exhaustive optimum: extend app/engine/space.py"
                        )
                    usage = res.llm_usage or {}
                    records.append(
                        {
                            "planner": name,
                            "trip": trip.name,
                            "budget": budget,
                            "seed": seed,
                            "sim": sim_label,
                            "searches_used": live.used,
                            "found": found is not None,
                            "best_utility": found,
                            "optimum_utility": best.utility,
                            "regret": regret,
                            "best_id": res.ranked[0].itinerary.id if res.ranked else None,
                            "optimum_id": best.itinerary.id,
                            "wall_ms": round(wall_ms, 1),
                            "llm_input_tokens": usage.get("input_tokens", 0),
                            "llm_output_tokens": usage.get("output_tokens", 0),
                            "llm_turns": usage.get("turns", 0),
                        }
                    )
    return records


def run_benchmark(
    planners: list[str],
    budgets: list[int],
    seeds: list[int],
    trips: list[BenchTrip],
    config: SimConfig | None = None,
    sim_label: str = "realistic",
    llm_factory: Callable[[], LLM] | None = None,
) -> list[dict]:
    """Synchronous entry point; use `run_benchmark_async` from inside an event loop."""
    return asyncio.run(run_benchmark_async(planners, budgets, seeds, trips, config, sim_label, llm_factory))
