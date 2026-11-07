"""Seeded fare simulator: a live provider and a fare cache with a known truth.

One `FareSimulator(seed)` is both a `LiveFareProvider` (bookable tickets for a
list of slices) and a `CachedFareProvider` (a noisy, stale view of the lowest
prices). Routes and schedules come from `network.py` (fixed data); prices from
`prices.py` (seeded). Same seed and config, same answers, in any call order.
"""

from __future__ import annotations

import asyncio
import itertools
import math
from datetime import date

from app.models import Slice, Ticket
from app.sim.network import Schedule, Service, schedules
from app.sim.prices import PriceModel, SimConfig


class FareSimulator:
    name = "sim"

    def __init__(self, seed: int = 0, config: SimConfig | None = None):
        self.seed = seed
        self.config = config or SimConfig()
        self.model = PriceModel(seed, self.config)

    @staticmethod
    def _flying(origin: str, destination: str, day: date) -> list[tuple[Service, Schedule]]:
        return [(svc, s) for svc, s in schedules(origin, destination) if day.weekday() in svc.days]

    async def search(self, slices: list[Slice], max_results: int = 5) -> list[Ticket]:
        if self.config.latency_s:
            await asyncio.sleep(self.config.latency_s)
        if not slices or not all(self.model.bookable(s.date) for s in slices):
            return []
        per_slice = [self._flying(s.origin, s.destination, s.date) for s in slices]
        if any(not opts for opts in per_slice):
            return []
        trip_key = ";".join(f"{s.origin}-{s.destination}@{s.date.isoformat()}" for s in slices)
        discount = self.config.return_discount if len(slices) > 1 else 1.0
        tickets: list[Ticket] = []
        for combo in itertools.product(*per_slice):
            fares = [
                self.model.fare(svc, s.origin, s.destination, s.date) for (svc, _), s in zip(combo, slices, strict=True)
            ]
            names = ",".join(svc.name for svc, _ in combo)
            noise = math.exp(self.model.gauss(self.config.ticket_sd, "ticket", trip_key, names))
            tickets.append(
                Ticket(
                    provider=self.name,
                    price=round(discount * sum(fares) * noise, 2),
                    journeys=[sched.legs(s.date) for (_, sched), s in zip(combo, slices, strict=True)],
                )
            )
        tickets.sort(key=lambda t: t.price)
        return tickets[:max_results]

    def _observed_low(self, origin: str, destination: str, day: date, obs: int, key: tuple) -> float | None:
        """The lowest fare one past observation saw for this direction, or None if nothing flies."""
        opts = self._flying(origin, destination, day)
        if not opts:
            return None
        c = self.config
        lows = []
        for svc, _ in opts:
            z = self.model.gauss(svc.volatility * c.cache_volatility_scale, "cache", *key, obs, svc.name)
            lows.append(self.model.fare(svc, origin, destination, day) * math.exp(z))
        return min(lows)

    async def lowest_price(
        self, origin: str, destination: str, depart: date, return_date: date | None = None
    ) -> float | None:
        if not self.model.bookable(depart) or (return_date and not self.model.bookable(return_date)):
            return None
        c = self.config
        key = (origin, destination, depart.isoformat(), return_date.isoformat() if return_date else "")
        seen: list[float] = []
        for obs in range(max(1, c.cache_k)):
            out = self._observed_low(origin, destination, depart, obs, key)
            if out is None:
                return None
            price = out
            if return_date is not None:
                back = self._observed_low(destination, origin, return_date, obs, key)
                if back is None:
                    return None
                price = c.return_discount * (out + back)
            age = (
                self.model.rng("cache-age", *key, obs).randint(1, c.cache_staleness_days)
                if c.cache_staleness_days
                else 0
            )
            seen.append(price * math.exp(-c.cache_drift_per_day * age))
        return round(min(seen), 2)
