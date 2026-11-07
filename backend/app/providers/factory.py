from __future__ import annotations

from app.config import Settings
from app.providers.base import BudgetedProvider, CachedFareProvider, LiveFareProvider, NoCache
from app.providers.fixture import FixtureCache, FixtureProvider


def _simulator(settings: Settings):  # noqa: ANN202
    from app.sim import FareSimulator

    return FareSimulator(seed=settings.sim_seed)


def live_provider(settings: Settings) -> LiveFareProvider:
    if settings.fare_provider == "simulator":
        return _simulator(settings)
    if settings.fare_provider == "serpapi":
        if not settings.serpapi_api_key:
            raise RuntimeError("FARE_PROVIDER=serpapi needs SERPAPI_API_KEY")
        from app.providers.serpapi_provider import SerpApiProvider

        return SerpApiProvider(settings.serpapi_api_key, currency=settings.currency)
    if settings.fare_provider == "fli":
        from app.providers.fli_provider import FliProvider

        return FliProvider(currency=settings.currency)
    return FixtureProvider()


def cache_provider(settings: Settings) -> CachedFareProvider:
    if settings.fare_provider == "simulator":  # the simulator's own stale cache, never a real one
        return _simulator(settings)
    if settings.travelpayouts_token:
        from app.providers.travelpayouts import TravelpayoutsCache

        return TravelpayoutsCache(settings.travelpayouts_token, currency=settings.currency)
    if settings.fare_provider == "fixture":
        return FixtureCache()
    return NoCache()


def budgeted(settings: Settings, budget: int) -> BudgetedProvider:
    return BudgetedProvider(live_provider(settings), budget)
