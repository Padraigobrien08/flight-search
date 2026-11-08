"""The planner race: best-so-far utility and regret after each search, per planner.

A run's steps come from its trace. Every itinerary a planner assembled is tagged with the
search that made it possible (the latest search any of its tickets came from); after search
k the planner's best is the top-ranked itinerary among those available by then. The running
maximum is kept, so regret never rises, and the final step is what the planner returned.

Replay serves recorded runs (data/race/recordings.json) for the demo trip. Runs whose
`source` is "placeholder" were made with a scripted stand-in, not a real model, and say so.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from app.bench.run import LLM_PLANNERS, PLANNERS, all_planners
from app.bench.trips import BenchTrip, _req
from app.engine.utility import rank, score
from app.llm.base import LLM
from app.models import Ticket
from app.providers.base import BudgetedProvider
from app.sim import FareSimulator, exhaustive_best

RECORDINGS = Path(__file__).resolve().parents[2] / "data" / "race" / "recordings.json"
RACE_BUDGETS = (5, 10, 20, 30)
RACE_TRIP = BenchTrip(
    "race-demo",
    _req(date(2027, 5, 21), date(2027, 6, 5), 4),
    why="the demo's default: Edinburgh to Lima out 21-24 May, home from La Paz 5-8 Jun 2027",
)
PLACEHOLDER_NOTE = (
    "Scripted stand-in, not a real model. Replace with: OPENAI_API_KEY=... uv run python -m app.race --planners llm"
)

Source = Literal["recorded", "placeholder", "live"]


class Step(BaseModel):
    searches_used: int
    best_utility: float | None
    regret: float | None
    hub: str | None = None
    reason: str | None = None


class RaceRun(BaseModel):
    planner: str
    budget: int
    source: Source
    note: str | None = None
    model: str | None = None
    steps: list[Step]


def _sig(t: Ticket) -> tuple:
    return (
        t.price,
        tuple((leg.carrier, leg.origin, leg.destination, leg.depart) for legs in t.journeys for leg in legs),
    )


async def run_planner(
    name: str,
    trip: BenchTrip,
    budget: int,
    seed: int,
    optimum: float,
    llm_factory: Callable[[], LLM] | None = None,
    source: Source = "live",
    note: str | None = None,
) -> RaceRun:
    if name not in PLANNERS and name not in LLM_PLANNERS:
        raise ValueError(f"unknown planner {name!r}; known: {all_planners()}")
    sim = FareSimulator(seed)
    live = BudgetedProvider(sim, budget)
    model = None
    if name in LLM_PLANNERS:
        if llm_factory is None:
            raise ValueError(f"planner {name!r} needs an LLM")
        llm = llm_factory()
        model = getattr(llm, "model", None)
        res = await LLM_PLANNERS[name](trip.request, trip.prefs, live, sim, llm)
    else:
        res = await PLANNERS[name](trip.request, trip.prefs, live, sim)

    searches = [e for e in res.trace if e.kind == "search"]
    first_seen: dict[tuple, int] = {}
    for e in searches:
        for t in live.memoised(e.slices or []) or []:
            first_seen.setdefault(_sig(t), e.searches_used or 0)
    available_at = [(max(first_seen.get(_sig(t), 10**9) for t in it.tickets), it) for it in res.candidates]

    steps: list[Step] = []
    best: float | None = None
    for e in searches:
        k = e.searches_used or 0
        ranked = rank([score(it, trip.prefs) for at, it in available_at if at <= k], trip.prefs, top_k=1)
        if ranked and (best is None or ranked[0].utility > best):
            best = ranked[0].utility
        steps.append(
            Step(
                searches_used=k,
                best_utility=best,
                regret=None if best is None else round(max(optimum - best, 0.0), 2),
                hub=e.hub,
                reason=e.reason,
            )
        )
    if not steps:
        steps = [Step(searches_used=0, best_utility=None, regret=None, reason="no searches")]
    return RaceRun(planner=name, budget=budget, source=source, note=note, model=model, steps=steps)


async def optimum(trip: BenchTrip, seed: int) -> float:
    best = await exhaustive_best(FareSimulator(seed), trip.request, trip.prefs)
    if best is None:
        raise ValueError(f"no feasible itinerary for {trip.name} at seed {seed}")
    return best.utility


def load_recordings(path: Path = RECORDINGS) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def recorded_run(recordings: dict[str, Any], planner: str, budget: int, seed: int) -> RaceRun | None:
    if recordings.get("trip") != RACE_TRIP.name or recordings.get("seed") != seed:
        return None
    run = recordings.get("runs", {}).get(planner, {}).get(str(budget))
    return RaceRun.model_validate(run) if run else None
