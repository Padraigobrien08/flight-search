"""Run planners against the simulator and score them by exact regret.

One record per (planner, trip, budget, seed). The optimum for each (trip, seed)
is computed once by exhaustive search and shared by every planner and budget.
Everything but `wall_ms` is deterministic.

A run that finds no itinerary has `found: false` and null `best_utility` and
`regret` (JSON can't carry inf); reports must count those, not drop them.
Negative regret means a planner built an itinerary outside the exhaustive
space, so it raises instead of being reported.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from app.bench.trips import BenchTrip
from app.engine.planner import plan
from app.models import PlanResult, Preferences, TripRequest
from app.providers.base import BudgetedProvider, CachedFareProvider
from app.sim import FareSimulator, SimConfig, exhaustive_best

Planner = Callable[[TripRequest, Preferences, BudgetedProvider, CachedFareProvider], Awaitable[PlanResult]]

PLANNERS: dict[str, Planner] = {"heuristic": plan}


class RegretBelowZero(AssertionError):
    pass


async def run_benchmark_async(
    planners: list[str],
    budgets: list[int],
    seeds: list[int],
    trips: list[BenchTrip],
    config: SimConfig | None = None,
    sim_label: str = "realistic",
) -> list[dict]:
    unknown = [p for p in planners if p not in PLANNERS]
    if unknown:
        raise ValueError(f"unknown planners {unknown}; known: {sorted(PLANNERS)}")
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
                    res = await PLANNERS[name](trip.request, trip.prefs, live, sim)
                    wall_ms = (time.perf_counter() - t0) * 1000
                    found = res.ranked[0].utility if res.ranked else None
                    regret = None if found is None else round(best.utility - found, 2)
                    if regret is not None and regret < -1e-6:
                        raise RegretBelowZero(
                            f"{name} found {res.ranked[0].itinerary.id} on {trip.name} seed {seed}, "
                            f"£{-regret:.2f} better than the exhaustive optimum: extend app/sim/exhaustive.py"
                        )
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
) -> list[dict]:
    """Synchronous entry point; use `run_benchmark_async` from inside an event loop."""
    return asyncio.run(run_benchmark_async(planners, budgets, seeds, trips, config, sim_label))
