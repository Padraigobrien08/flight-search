"""POST /api/plan and POST /api/rerank.

A plan runs the planner once (spending its search budget) and keeps every
itinerary it assembled under a plan_id. A rerank scores those same itineraries
for new preferences: no searches, no LLM, so moving a slider is instant.

Preferences in both requests are partial: a plan's fields default to
`Preferences()`, a rerank's fields default to the plan's own preferences (send
every slider value to be explicit).
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.engine.planner import plan, reprice
from app.engine.utility import rank, score, violations
from app.models import Itinerary, PlanResult, Preferences, ScoredItinerary, TripRequest
from app.providers.factory import budgeted, cache_provider

router = APIRouter()
MAX_PLANS = 200


@dataclass
class StoredPlan:
    result: PlanResult
    candidates: list[Itinerary] = field(default_factory=list)


class PlanStore:
    """The most recent plans, in memory (one process; a restart forgets them)."""

    def __init__(self, capacity: int = MAX_PLANS):
        self.capacity = capacity
        self._plans: OrderedDict[str, StoredPlan] = OrderedDict()
        self._lock = Lock()

    def put(self, stored: StoredPlan) -> str:
        plan_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._plans[plan_id] = stored
            while len(self._plans) > self.capacity:
                self._plans.popitem(last=False)
        return plan_id

    def get(self, plan_id: str) -> StoredPlan | None:
        with self._lock:
            stored = self._plans.get(plan_id)
            if stored:
                self._plans.move_to_end(plan_id)
            return stored


STORE = PlanStore()


def get_store() -> PlanStore:
    return STORE


class PlanRequest(BaseModel):
    trip: TripRequest
    preferences: dict[str, Any] = {}


class RerankRequest(BaseModel):
    plan_id: str
    preferences: dict[str, Any] = {}


class PlanStats(BaseModel):
    searches_used: int
    search_budget: int
    candidates: int
    feasible: int
    elapsed_ms: float


class PlanResponse(PlanResult):
    plan_id: str
    stats: PlanStats


def _prefs(base: Preferences, update: dict[str, Any]) -> Preferences:
    try:
        return Preferences.model_validate(base.model_dump() | update)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _rank(cands: list[Itinerary], prefs: Preferences) -> list[ScoredItinerary]:
    return rank([score(reprice(it, prefs), prefs) for it in cands], prefs)


def _response(plan_id: str, result: PlanResult, cands: list[Itinerary], elapsed_ms: float) -> PlanResponse:
    feasible = sum(1 for it in cands if not violations(it, result.preferences))
    return PlanResponse(
        **result.model_dump(),
        plan_id=plan_id,
        stats=PlanStats(
            searches_used=result.searches_used,
            search_budget=result.search_budget,
            candidates=len(cands),
            feasible=feasible,
            elapsed_ms=round(elapsed_ms, 1),
        ),
    )


@router.post("/api/plan", response_model=PlanResponse)
async def plan_endpoint(
    req: PlanRequest, settings: Settings = Depends(get_settings), store: PlanStore = Depends(get_store)
) -> PlanResponse:
    """Run the planner (spends the trip's search budget) and keep its candidates for re-ranking."""
    prefs = _prefs(Preferences(), req.preferences)
    t0 = time.perf_counter()
    result = await plan(req.trip, prefs, budgeted(settings, req.trip.search_budget), cache_provider(settings))
    plan_id = store.put(StoredPlan(result=result, candidates=result.candidates))
    return _response(plan_id, result, result.candidates, (time.perf_counter() - t0) * 1000)


@router.post("/api/rerank", response_model=PlanResponse)
async def rerank_endpoint(req: RerankRequest, store: PlanStore = Depends(get_store)) -> PlanResponse:
    """Re-score a plan's stored itineraries for new preferences. No searches, no LLM."""
    stored = store.get(req.plan_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="unknown or expired plan_id; run /api/plan again")
    t0 = time.perf_counter()
    prefs = _prefs(stored.result.preferences, req.preferences)
    ranked = _rank(stored.candidates, prefs)
    result = stored.result.model_copy(update={"preferences": prefs, "ranked": ranked})
    return _response(req.plan_id, result, stored.candidates, (time.perf_counter() - t0) * 1000)
