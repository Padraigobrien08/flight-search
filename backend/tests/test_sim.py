from datetime import date

from app.engine.planner import plan
from app.models import Preferences, Slice, TripRequest
from app.providers.base import BudgetedProvider
from app.sim import FareSimulator

OUT = Slice(origin="EDI", destination="MAD", date=date(2027, 5, 22))
BACK = Slice(origin="MAD", destination="EDI", date=date(2027, 6, 6))


async def test_answers_do_not_depend_on_call_order():
    a = FareSimulator(seed=3)
    first = await a.search([OUT])
    b = FareSimulator(seed=3)
    await b.search([BACK])
    await b.lowest_price("EDI", "LIM", date(2027, 5, 22))
    assert [t.model_dump() for t in await b.search([OUT])] == [t.model_dump() for t in first]


async def test_unknown_route_has_no_tickets_and_no_cache():
    sim = FareSimulator()
    assert await sim.search([Slice(origin="EDI", destination="SYD", date=date(2027, 5, 22))]) == []
    assert await sim.lowest_price("EDI", "SYD", date(2027, 5, 22)) is None
    assert await sim.search([]) == []


async def test_tickets_sorted_capped_and_tagged():
    tickets = await FareSimulator().search([OUT, BACK], max_results=2)
    assert len(tickets) == 2
    assert tickets[0].price <= tickets[1].price
    assert all(t.provider == "sim" and len(t.journeys) == 2 for t in tickets)


async def test_planner_runs_on_the_simulator_within_budget():
    sim = FareSimulator(seed=0)
    trip = TripRequest(
        origin="EDI",
        destination="LIM",
        return_from="LPB",
        depart_earliest=date(2027, 5, 22),
        depart_latest=date(2027, 5, 22),
        return_earliest=date(2027, 6, 6),
        return_latest=date(2027, 6, 6),
    )
    live = BudgetedProvider(sim, 10)
    res = await plan(trip, Preferences(), live, sim)
    assert res.ranked
    assert live.used <= 10
