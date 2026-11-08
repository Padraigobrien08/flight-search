"""POST /api/race: per-search regret curves for several planners on the same trip and budget.

mode="replay" serves recorded runs for the demo trip (instant, free). Code planners without a
recording are deterministic, so they are computed and cached. An `llm` run whose source is
"placeholder" came from a scripted stand-in, not a model, and the response says so.

mode="live" runs the planners fresh (the `llm` planner makes real API calls inside the spend
cap) and is limited per client per hour (HTTP 429). The client is identified by Fly's
Fly-Client-IP header behind the Fly proxy, else the socket address; X-Forwarded-For is
ignored because a client can set it to dodge the limit.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_llm_factory
from app.bench.run import LLM_PLANNERS, PLANNERS, all_planners
from app.bench.trips import BenchTrip
from app.config import Settings, get_settings
from app.llm import LLMFactory
from app.models import TripRequest
from app.race.core import RACE_BUDGETS, RACE_TRIP, RaceRun, load_recordings, optimum, recorded_run, run_planner

router = APIRouter()


class RaceRequest(BaseModel):
    budget: int = Field(10, ge=1, le=50)
    planners: list[str] = ["llm", "heuristic"]
    mode: Literal["replay", "live"] = "replay"
    trip: TripRequest | None = Field(None, description="live mode only; default is the demo trip")
    seed: int | None = Field(None, description="fare world; default SIM_SEED")


class RaceResponse(BaseModel):
    mode: str
    trip: str
    budget: int
    seed: int
    optimum_utility: float
    planners: dict[str, RaceRun]


class LiveLimiter:
    """Sliding one-hour window of live races per client."""

    def __init__(self):
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, client: str, per_hour: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[client]
            while hits and now - hits[0] >= 3600:
                hits.popleft()
            if len(hits) >= per_hour:
                return False
            hits.append(now)
            return True


LIMITER = LiveLimiter()
_COMPUTED: dict[tuple[str, int, int], RaceRun] = {}


def get_limiter() -> LiveLimiter:
    return LIMITER


def client_key(request: Request) -> str:
    return request.headers.get("fly-client-ip") or (request.client.host if request.client else "unknown")


def _check_planners(names: list[str]) -> None:
    unknown = [p for p in names if p not in PLANNERS and p not in LLM_PLANNERS]
    if unknown or not names:
        raise HTTPException(status_code=422, detail=f"planners must be some of {all_planners()}; got {names}")


@router.post("/api/race", response_model=RaceResponse)
async def race(
    req: RaceRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    factory: LLMFactory = Depends(get_llm_factory),
    limiter: LiveLimiter = Depends(get_limiter),
) -> RaceResponse:
    _check_planners(req.planners)
    seed = settings.sim_seed if req.seed is None else req.seed

    if req.mode == "replay":
        if req.trip is not None:
            raise HTTPException(status_code=422, detail="replay is recorded for the demo trip only; use mode=live")
        recordings = load_recordings()
        opt = recordings.get("optimum_utility") if recordings.get("seed") == seed else None
        if opt is None:
            opt = await optimum(RACE_TRIP, seed)
        runs: dict[str, RaceRun] = {}
        for name in req.planners:
            run = recorded_run(recordings, name, req.budget, seed)
            if run is None and name in PLANNERS:  # deterministic: computing it is the same as replaying it
                key = (name, req.budget, seed)
                if key not in _COMPUTED:
                    _COMPUTED[key] = await run_planner(name, RACE_TRIP, req.budget, seed, opt, source="recorded")
                run = _COMPUTED[key]
            if run is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"no recorded {name} run at budget {req.budget}; recorded budgets: {list(RACE_BUDGETS)}",
                )
            runs[name] = run
        return RaceResponse(
            mode="replay", trip=RACE_TRIP.name, budget=req.budget, seed=seed, optimum_utility=opt, planners=runs
        )

    if not limiter.allow(client_key(request), settings.race_live_per_hour):
        raise HTTPException(
            status_code=429,
            detail=f"live races are limited to {settings.race_live_per_hour} per hour; replay is unlimited",
        )
    trip = BenchTrip("custom", req.trip) if req.trip else RACE_TRIP
    opt = await optimum(trip, seed)
    results = await asyncio.gather(
        *(run_planner(name, trip, req.budget, seed, opt, lambda: factory("baseline")) for name in req.planners)
    )
    return RaceResponse(
        mode="live",
        trip=trip.name,
        budget=req.budget,
        seed=seed,
        optimum_utility=opt,
        planners=dict(zip(req.planners, results, strict=True)),
    )
