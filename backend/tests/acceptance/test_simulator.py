import statistics
from datetime import date, timedelta

from app.models import Preferences, Slice

from ._trips import lima_trip


async def test_determinism():
    from app.sim import FareSimulator

    slices = [
        Slice(origin="EDI", destination="LIM", date=date(2027, 5, 22)),
        Slice(origin="LIM", destination="EDI", date=date(2027, 6, 6)),
    ]
    a = await FareSimulator(seed=1).search(slices)
    b = await FareSimulator(seed=1).search(slices)
    c = await FareSimulator(seed=2).search(slices)
    assert a, "simulator returned no tickets for a benchmark route"
    assert [t.model_dump() for t in a] == [t.model_dump() for t in b]
    assert [t.price for t in a] != [t.price for t in c]
    assert await FareSimulator(seed=1).lowest_price("EDI", "LIM", date(2027, 5, 22), date(2027, 6, 6)) is not None


async def _min_price(sim, slices):
    tickets = await sim.search(slices)
    return min(t.price for t in tickets)


async def test_structure():
    from app.sim import FareSimulator

    sim = FareSimulator(seed=0)
    # Weekday effect: Saturdays dearer than Tuesdays on average over 8 weeks.
    start = date(2027, 5, 1)
    sats = [start + timedelta(days=i) for i in range(56) if (start + timedelta(days=i)).weekday() == 5]
    tues = [start + timedelta(days=i) for i in range(56) if (start + timedelta(days=i)).weekday() == 1]
    sat = statistics.mean([await _min_price(sim, [Slice(origin="EDI", destination="MAD", date=d)]) for d in sats])
    tue = statistics.mean([await _min_price(sim, [Slice(origin="EDI", destination="MAD", date=d)]) for d in tues])
    assert sat > tue

    # A return is cheaper than two one-ways.
    out, back = date(2027, 5, 22), date(2027, 6, 6)
    ret = await _min_price(
        sim, [Slice(origin="MAD", destination="LIM", date=out), Slice(origin="LIM", destination="MAD", date=back)]
    )
    ow = await _min_price(sim, [Slice(origin="MAD", destination="LIM", date=out)]) + await _min_price(
        sim, [Slice(origin="LIM", destination="MAD", date=back)]
    )
    assert ret < ow

    # The cache is a noisy, stale view of the truth: correlated, not identical.
    truth, cached = [], []
    for o, d in [("EDI", "MAD"), ("EDI", "LHR"), ("EDI", "CDG"), ("MAD", "LIM"), ("LHR", "LIM"), ("CDG", "LIM")]:
        for k in range(5):
            day = date(2027, 5, 18) + timedelta(days=3 * k)
            truth.append(await _min_price(sim, [Slice(origin=o, destination=d, date=day)]))
            cached.append(await sim.lowest_price(o, d, day))
    assert all(c is not None for c in cached)
    assert statistics.correlation(truth, cached) > 0.8
    assert any(abs(t - c) > 1 for t, c in zip(truth, cached, strict=True))


async def test_ground_truth():
    from app.sim import FareSimulator, exhaustive_best

    from app.engine.planner import plan
    from app.providers.base import BudgetedProvider

    sim = FareSimulator(seed=0)
    trip, prefs = lima_trip(), Preferences()
    best = await exhaustive_best(sim, trip, prefs)
    assert best is not None
    for budget in (3, 10, 30):
        res = await plan(trip, prefs, BudgetedProvider(sim, budget), sim)
        if res.ranked:
            assert res.ranked[0].utility <= best.utility + 1e-6
