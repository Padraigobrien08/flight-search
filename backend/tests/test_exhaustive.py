from datetime import date, timedelta

import pytest

from app.engine.planner import plan
from app.models import Itinerary, Preferences, TripRequest
from app.providers.base import BudgetedProvider
from app.sim import FareSimulator, candidates, exhaustive_best


def trip(flex: int, return_from: str | None = "LPB") -> TripRequest:
    return TripRequest(
        origin="EDI",
        destination="LIM",
        return_from=return_from,
        depart_earliest=date(2027, 5, 21),
        depart_latest=date(2027, 5, 21) + timedelta(days=flex - 1),
        return_earliest=date(2027, 6, 5),
        return_latest=date(2027, 6, 5) + timedelta(days=flex - 1),
    )


def signature(it: Itinerary) -> tuple:
    """What makes two itineraries the same trip: the tickets' prices and every leg in travel order."""
    legs = tuple((leg.carrier, leg.origin, leg.destination, leg.depart) for j in it.journeys for leg in j.legs)
    return (tuple(sorted(t.price for t in it.tickets)), legs)


CASES = [
    ("open-jaw", trip(2), Preferences()),
    ("lima return", trip(2, return_from=None), Preferences()),
    ("stopover lover", trip(2), Preferences(stopover_bonus=300)),
    ("same-day self-transfer", trip(2), Preferences(allow_same_day_self_transfer=True, min_self_transfer_hours=2)),
    ("wide window", trip(4), Preferences()),
]


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize(("label", "req", "prefs"), CASES, ids=[c[0] for c in CASES])
async def test_every_planned_itinerary_is_in_the_space_and_none_beats_the_optimum(seed, label, req, prefs):
    sim = FareSimulator(seed=seed)
    space = {signature(it) for it in await candidates(sim, req, prefs)}
    best = await exhaustive_best(sim, req, prefs)
    assert best is not None
    for budget in (5, 15, 40):
        res = await plan(req, prefs, BudgetedProvider(sim, budget), sim)
        for s in res.ranked:
            assert signature(s.itinerary) in space, f"{label}: plan built {s.itinerary.id}, outside the space"
            assert s.utility <= best.utility + 1e-6


async def test_optimum_is_feasible_and_deterministic():
    req, prefs = trip(2), Preferences()
    a = await exhaustive_best(FareSimulator(seed=4), req, prefs)
    b = await exhaustive_best(FareSimulator(seed=4), req, prefs)
    assert a is not None and a.model_dump() == b.model_dump()
    assert a.rank == 1
