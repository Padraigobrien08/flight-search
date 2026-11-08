import asyncio

import pytest

from app.bench import BENCHMARK_TRIPS
from app.engine.planner import plan
from app.models import Slice
from app.providers.base import BudgetedProvider
from app.sim import FareSimulator, SimConfig
from tests import serial_planner


def same(a, b) -> bool:
    """Equal in everything but the trace, which the frozen serial planner predates (F12)."""
    return a.model_dump(exclude={"trace"}) == b.model_dump(exclude={"trace"})


@pytest.mark.parametrize("trip", BENCHMARK_TRIPS, ids=[t.name for t in BENCHMARK_TRIPS])
async def test_concurrent_plan_returns_exactly_what_the_serial_one_did(trip):
    for budget in (1, 2, 3, 4, 5, 7, 10, 20):
        sim = FareSimulator(seed=0)
        a = await plan(trip.request, trip.prefs, BudgetedProvider(sim, budget), sim)
        b = await serial_planner.plan(trip.request, trip.prefs, BudgetedProvider(FareSimulator(seed=0), budget), sim)
        assert same(a, b), f"{trip.name} at budget {budget}"


class EmptyLongHaulFrom:
    """A simulator where one hub's long-haul search comes back empty, freeing budget for the next hub."""

    def __init__(self, sim: FareSimulator, hub_airport: str):
        self.sim, self.hub_airport, self.name = sim, hub_airport, sim.name

    async def search(self, slices, max_results=5):
        if len(slices) == 2 and slices[0].origin == self.hub_airport and slices[0].destination == "LIM":
            return []
        return await self.sim.search(slices, max_results)

    async def lowest_price(self, *args):
        return await self.sim.lowest_price(*args)


@pytest.mark.parametrize("hub_airport", ["MAD", "LHR", "BCN"])
async def test_an_empty_long_haul_frees_budget_the_same_way(hub_airport):
    trip = BENCHMARK_TRIPS[2]  # open-jaw, 3-day window
    for budget in range(5, 13):
        live = EmptyLongHaulFrom(FareSimulator(seed=1), hub_airport)
        a = await plan(trip.request, trip.prefs, BudgetedProvider(live, budget), live)
        b = await serial_planner.plan(trip.request, trip.prefs, BudgetedProvider(live, budget), live)
        assert same(a, b), f"{hub_airport} empty at budget {budget}"


async def test_concurrent_identical_searches_cost_one():
    live = BudgetedProvider(FareSimulator(seed=0, config=SimConfig(latency_s=0.01)), budget=5)
    s = [Slice(origin="EDI", destination="MAD", date=__import__("datetime").date(2027, 5, 22))]
    results = await asyncio.gather(*(live.search(s) for _ in range(4)))
    assert live.used == 1
    assert all(r == results[0] for r in results)
