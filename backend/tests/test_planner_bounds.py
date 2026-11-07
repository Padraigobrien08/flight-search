from datetime import date

import pytest

from app.engine.planner import MULTI_CITY_DISCOUNT, longhaul_bound
from app.models import TripRequest

D, R = date(2027, 5, 22), date(2027, 6, 6)


class StubCache:
    name = "stub"

    def __init__(self, prices: dict[tuple, float]):
        self.prices = prices

    async def lowest_price(self, origin, destination, depart, return_date=None):  # noqa: ANN001
        return self.prices.get((origin, destination, return_date is not None))


def trip(return_from: str | None) -> TripRequest:
    return TripRequest(
        origin="EDI",
        destination="LIM",
        return_from=return_from,
        depart_earliest=D,
        depart_latest=D,
        return_earliest=R,
        return_latest=R,
    )


async def test_open_jaw_bound_gets_the_multi_city_discount():
    cache = StubCache({("MAD", "LIM", False): 400.0, ("LPB", "MAD", False): 500.0})
    assert await longhaul_bound(cache, trip("LPB"), "MAD", D, R) == pytest.approx(MULTI_CITY_DISCOUNT * 900.0)


async def test_open_jaw_bound_is_unknown_when_either_direction_is_missing():
    cache = StubCache({("LIS", "LIM", False): 400.0})
    assert await longhaul_bound(cache, trip("LPB"), "LIS", D, R) is None


async def test_lima_return_bound_is_the_cached_return_unchanged():
    cache = StubCache({("MAD", "LIM", True): 743.0})
    assert await longhaul_bound(cache, trip(None), "MAD", D, R) == 743.0
