"""Seeded fare simulator: a live provider and a fare cache with a known truth.

One `FareSimulator(seed)` is both a `LiveFareProvider` (bookable tickets for a
list of slices) and a `CachedFareProvider` (a noisy, stale view of the lowest
prices). Every random draw is keyed on the seed and on what is being priced,
never on call order, so the same question always gets the same answer and
results can't depend on which planner asked first.

The schedule network (which carriers fly which routes, at what times) is the
route table in `app.providers.fixture`. Prices start from the same real
anchors; the seeded noise here is the first layer of the model. F2 replaces it
with the hierarchical model (route level x date effect x weekday x noise).
"""

from __future__ import annotations

import hashlib
import itertools
import math
import random
from datetime import date

from app.models import Slice, Ticket
from app.providers.fixture import _legs, _templates

RETURN_DISCOUNT = 0.8  # a ticket covering several slices costs 0.8 x the sum of one-ways
TICKET_NOISE = 0.08  # log-sd of the per-ticket price noise
CACHE_NOISE = 0.06  # log-sd of the cache's error against the cheapest one-way level


class FareSimulator:
    name = "sim"

    def __init__(self, seed: int = 0):
        self.seed = seed

    def _rng(self, *key: object) -> random.Random:
        """A generator seeded on (seed, key): stable across processes and call order."""
        text = "|".join(str(k) for k in (self.seed, *key))
        return random.Random(int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big"))

    def _lognormal(self, sd: float, *key: object) -> float:
        return math.exp(self._rng(*key).gauss(0.0, sd))

    async def search(self, slices: list[Slice], max_results: int = 5) -> list[Ticket]:
        per_slice = [_templates(s.origin, s.destination) for s in slices]
        if not slices or any(not ts for ts in per_slice):
            return []
        trip_key = ";".join(f"{s.origin}-{s.destination}@{s.date.isoformat()}" for s in slices)
        tickets: list[Ticket] = []
        for idx in itertools.product(*(range(len(ts)) for ts in per_slice)):
            combo = [ts[i] for ts, i in zip(per_slice, idx, strict=True)]
            price = sum(t.oneway_price for t in combo)
            if len(slices) > 1:
                price *= RETURN_DISCOUNT
            price *= self._lognormal(TICKET_NOISE, "ticket", trip_key, idx)
            tickets.append(
                Ticket(
                    provider=self.name,
                    price=round(price, 2),
                    journeys=[_legs(t, s.date) for t, s in zip(combo, slices, strict=True)],
                )
            )
        tickets.sort(key=lambda t: t.price)
        return tickets[:max_results]

    async def lowest_price(
        self, origin: str, destination: str, depart: date, return_date: date | None = None
    ) -> float | None:
        out = _templates(origin, destination)
        if not out:
            return None
        level = min(t.oneway_price for t in out)
        if return_date is not None:
            back = _templates(destination, origin)
            if not back:
                return None
            level = (level + min(t.oneway_price for t in back)) * RETURN_DISCOUNT
        key = (origin, destination, depart.isoformat(), return_date.isoformat() if return_date else "")
        return round(level * self._lognormal(CACHE_NOISE, "cache", *key), 2)
