from datetime import date, timedelta

from app.engine.hubs import GATEWAYS, HUBS
from app.engine.journeys import build_journey
from app.engine.planner import plan
from app.models import Preferences, Slice, TripRequest
from app.providers.base import BudgetedProvider
from app.sim import UNBIASED_CACHE, FareSimulator
from app.sim.network import SERVICES, schedules

OUT = Slice(origin="EDI", destination="MAD", date=date(2027, 5, 22))
BACK = Slice(origin="MAD", destination="EDI", date=date(2027, 6, 6))


def lima_open_jaw() -> TripRequest:
    return TripRequest(
        origin="EDI",
        destination="LIM",
        return_from="LPB",
        depart_earliest=date(2027, 5, 22),
        depart_latest=date(2027, 5, 22),
        return_earliest=date(2027, 6, 6),
        return_latest=date(2027, 6, 6),
    )


async def test_answers_do_not_depend_on_call_order():
    a = FareSimulator(seed=3)
    first = await a.search([OUT])
    b = FareSimulator(seed=3)
    await b.search([BACK])
    await b.lowest_price("EDI", "LIM", date(2027, 5, 22))
    assert [t.model_dump() for t in await b.search([OUT])] == [t.model_dump() for t in first]


async def test_unknown_route_past_dates_and_empty_searches():
    sim = FareSimulator()
    assert await sim.search([Slice(origin="EDI", destination="SYD", date=date(2027, 5, 22))]) == []
    assert await sim.lowest_price("EDI", "SYD", date(2027, 5, 22)) is None
    assert await sim.search([]) == []
    past = date(2026, 1, 10)
    assert await sim.search([Slice(origin="EDI", destination="MAD", date=past)]) == []
    assert await sim.lowest_price("EDI", "MAD", past) is None


async def test_tickets_sorted_capped_and_tagged():
    tickets = await FareSimulator().search([OUT, BACK], max_results=2)
    assert len(tickets) == 2
    assert tickets[0].price <= tickets[1].price
    assert all(t.provider == "sim" and len(t.journeys) == 2 for t in tickets)


async def test_seeds_change_prices_never_routes():
    slices = [Slice(origin="LPB", destination="MAD", date=date(2027, 6, 5))]
    a, b = await FareSimulator(seed=0).search(slices), await FareSimulator(seed=9).search(slices)

    def routes(tickets):
        return sorted(str(t.journeys) for t in tickets)

    assert routes(a) == routes(b)
    assert [t.price for t in a] != [t.price for t in b]


def test_every_anchor_has_a_source_and_every_schedule_connects():
    names = [s.name for s in SERVICES]
    assert len(names) == len(set(names)), "service names key the seeds; they must be unique"
    for svc in SERVICES:
        assert svc.anchor.source in ("spec", "fixture", "design")
        assert svc.anchor.gbp > 0
        for sched in (svc.out, svc.back):
            if sched is None:
                continue
            legs = sched.legs(date(2027, 5, 22))
            assert build_journey(legs, [0] * len(legs)) is not None, f"{svc.name} legs don't connect"


def test_every_lima_gateway_has_positioning_and_long_haul():
    for code in GATEWAYS["LIM"]:
        hub = HUBS[code]
        assert any(schedules("EDI", a) and schedules(a, "EDI") for a in hub.arrival_airports), code
        assert schedules(hub.longhaul_airport, "LIM") and schedules("LIM", hub.longhaul_airport), code


async def test_la_paz_links_follow_the_design():
    sim = FareSimulator()
    # Lisbon has no La Paz link (NETWORK.md #5).
    assert await sim.lowest_price("LPB", "LIS", date(2027, 6, 6)) is None
    # The Santa Cruz link to Madrid flies Mon, Thu, Sat only (NETWORK.md #4).
    for k in range(7):
        day = date(2027, 6, 7) + timedelta(days=k)
        carriers = {
            leg.carrier
            for t in await sim.search([Slice(origin="LPB", destination="MAD", date=day)])
            for leg in t.journeys[0]
        }
        assert ("Air Europa" in carriers) == (day.weekday() in (0, 3, 5)), day


async def test_cache_is_optimistic_by_default_and_near_unbiased_when_asked():
    async def median_ratio(config, o, d):
        out = []
        for seed in range(10):
            sim = FareSimulator(seed=seed, config=config)
            for k in range(0, 15, 3):
                day = date(2027, 5, 18) + timedelta(days=k)
                truth = (await sim.search([Slice(origin=o, destination=d, date=day)]))[0].price
                out.append(await sim.lowest_price(o, d, day) / truth)
        out.sort()
        return out[len(out) // 2]

    assert await median_ratio(None, "MAD", "LIM") < 0.97
    assert await median_ratio(None, "BCN", "LIM") < await median_ratio(None, "MAD", "LIM") - 0.1  # NETWORK.md #3
    assert abs(await median_ratio(UNBIASED_CACHE, "MAD", "LIM") - 1) < 0.02
    assert abs(await median_ratio(UNBIASED_CACHE, "BCN", "LIM") - 1) < 0.05


async def test_planner_runs_on_the_simulator_within_budget():
    sim = FareSimulator(seed=0)
    live = BudgetedProvider(sim, 10)
    res = await plan(lima_open_jaw(), Preferences(), live, sim)
    assert res.ranked
    assert live.used <= 10
