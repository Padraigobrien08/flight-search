from datetime import date, datetime

import pytest

from app.engine.journeys import build_journey, night_overlap_minutes
from app.engine.planner import plan, sample_date_pairs
from app.engine.utility import pareto_front, score, violations
from app.models import Itinerary, Leg, Preferences, Ticket, TripRequest
from app.providers.base import BudgetedProvider
from app.providers.fixture import FixtureCache, FixtureProvider


def leg(o, d, dep, arr, mins, carrier="X"):
    return Leg(
        carrier=carrier,
        origin=o,
        destination=d,
        depart=datetime.fromisoformat(dep),
        arrive=datetime.fromisoformat(arr),
        duration_min=mins,
    )


def trip(**kw):
    base = dict(
        origin="EDI",
        destination="LIM",
        return_from="LPB",
        depart_earliest=date(2027, 5, 21),
        depart_latest=date(2027, 5, 24),
        return_earliest=date(2027, 6, 5),
        return_latest=date(2027, 6, 8),
    )
    return TripRequest(**(base | kw))


def test_night_overlap():
    assert night_overlap_minutes(datetime(2027, 5, 1, 23), datetime(2027, 5, 2, 7)) == 360
    assert night_overlap_minutes(datetime(2027, 5, 1, 8), datetime(2027, 5, 1, 20)) == 0


def test_connection_across_tickets_becomes_a_hub_night():
    legs = [
        leg("EDI", "MAD", "2027-05-22T06:00", "2027-05-22T10:05", 185),
        leg("MAD", "LIM", "2027-05-23T13:10", "2027-05-23T19:10", 720),
    ]
    j = build_journey(legs, [0, 1])
    assert j.connections[0].hub_night and j.connections[0].nights == 1
    assert j.travel_minutes == 185 + 720  # the stay is not travel time


def test_impossible_connection_is_rejected():
    legs = [
        leg("EDI", "MAD", "2027-05-22T06:00", "2027-05-22T10:05", 185),
        leg("MAD", "LIM", "2027-05-22T10:30", "2027-05-22T16:30", 720),
    ]
    assert build_journey(legs, [0, 1]) is None  # 25 min self-transfer


def test_same_day_self_transfer_violates_default_limits():
    legs = [
        leg("EDI", "MAD", "2027-05-22T06:00", "2027-05-22T10:05", 185),
        leg("MAD", "LIM", "2027-05-22T13:10", "2027-05-22T19:10", 720),
    ]
    j = build_journey(legs, [0, 1])
    t = Ticket(provider="t", price=100, journeys=[legs])
    it = Itinerary(id="x", structure="split", tickets=[t], journeys=[j])
    assert any("self-transfer" in v for v in violations(it, Preferences()))
    assert not violations(it, Preferences(allow_same_day_self_transfer=True))


def test_score_prefers_short_journey_at_equal_price():
    fast = [leg("EDI", "LIM", "2027-05-22T06:00", "2027-05-22T14:00", 900)]
    slow = [
        leg("EDI", "YYZ", "2027-05-22T06:00", "2027-05-22T09:00", 450),
        leg("YYZ", "LIM", "2027-05-22T12:00", "2027-05-22T20:00", 600),
    ]
    def mk(legs, i):
        return Itinerary(
            id=i,
            structure="through",
            tickets=[Ticket(provider="t", price=800, journeys=[legs])],
            journeys=[build_journey(legs, [0] * len(legs))],
        )
    a, b = score(mk(fast, "a"), Preferences()), score(mk(slow, "b"), Preferences())
    assert a.utility > b.utility
    assert pareto_front([a, b]) == [a]


def test_date_sampling_keeps_ends_and_middle():
    pairs = sample_date_pairs(trip())
    assert pairs[0] == (date(2027, 5, 21), date(2027, 6, 5))
    assert pairs[-1] == (date(2027, 5, 24), date(2027, 6, 8))
    assert len(pairs) == 3


@pytest.mark.asyncio
async def test_planner_on_lima_trip_respects_budget_and_finds_a_stopover():
    live = BudgetedProvider(FixtureProvider(), 30)
    res = await plan(trip(), Preferences(), live, FixtureCache())
    assert res.searches_used <= 30
    assert res.ranked, "expected ranked itineraries"
    assert [s.rank for s in res.ranked] == list(range(1, len(res.ranked) + 1))
    assert any(s.itinerary.structure == "stopover" for s in res.ranked)
    for s in res.ranked:
        assert not violations(s.itinerary, res.preferences)


@pytest.mark.asyncio
async def test_planner_stops_at_budget():
    live = BudgetedProvider(FixtureProvider(), 3)
    res = await plan(trip(), Preferences(), live, FixtureCache())
    assert res.searches_used <= 3


@pytest.mark.asyncio
async def test_a_love_of_stopovers_changes_the_ranking():
    base = await plan(trip(), Preferences(stopover_bonus=0), BudgetedProvider(FixtureProvider(), 30), FixtureCache())
    keen = await plan(trip(), Preferences(stopover_bonus=300), BudgetedProvider(FixtureProvider(), 30), FixtureCache())
    assert keen.ranked[0].itinerary.structure == "stopover"
    assert keen.ranked[0].utility > base.ranked[0].utility
