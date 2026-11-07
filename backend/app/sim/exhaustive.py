"""The true optimum: the best itinerary in the whole candidate space, searched with no budget.

The space itself is defined in app/engine/space.py. The optimum is the highest-utility
feasible itinerary (hard limits applied, no Pareto filter: a dominated option can still
score higher).
"""

from __future__ import annotations

from app.engine.space import candidates
from app.engine.utility import score, violations
from app.models import Preferences, ScoredItinerary, TripRequest
from app.providers.base import LiveFareProvider

__all__ = ["candidates", "exhaustive_best"]


async def exhaustive_best(live: LiveFareProvider, req: TripRequest, prefs: Preferences) -> ScoredItinerary | None:
    """The highest-utility feasible itinerary in the whole candidate space, or None if there is none."""
    best: ScoredItinerary | None = None
    for it in await candidates(live, req, prefs):
        if violations(it, prefs):
            continue
        s = score(it, prefs)
        if best is None or s.utility > best.utility:
            best = s
    if best is not None:
        best.rank = 1
    return best
