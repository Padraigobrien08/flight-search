"""Fare source interfaces.

Two kinds of source, matching the spec:
- LiveFareProvider: real bookable options for a list of slices. Costs a
  "search" from the budget.
- CachedFareProvider: cheap, possibly stale lowest prices, used only to
  bound and prune. Free.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Protocol

from app.models import Slice, Ticket, TraceEvent


class LiveFareProvider(Protocol):
    name: str

    async def search(self, slices: list[Slice], max_results: int = 5) -> list[Ticket]:
        """Tickets covering all slices on one booking (one-way, return or multi-city)."""
        ...


class CachedFareProvider(Protocol):
    name: str

    async def lowest_price(
        self, origin: str, destination: str, depart: date, return_date: date | None = None
    ) -> float | None:
        """Lowest recently seen price, or None when the cache has nothing."""
        ...


class BudgetExhausted(Exception):
    pass


class BudgetedProvider:
    """Wraps a live provider: counts searches, enforces the budget, memoises.

    Safe under concurrency: the budget is checked and charged before the first
    await, and a search already in flight is shared, so concurrent repeats cost
    nothing, like memoised ones.
    """

    def __init__(self, inner: LiveFareProvider, budget: int):
        self.inner = inner
        self.name = inner.name
        self.budget = budget
        self.used = 0
        self._memo: dict[tuple, list[Ticket]] = {}
        self._inflight: dict[tuple, asyncio.Task[list[Ticket]]] = {}
        self.trace: list[TraceEvent] = []  # one "search" event per charged search, in charge order

    @property
    def remaining(self) -> int:
        return self.budget - self.used

    @staticmethod
    def key(slices: list[Slice]) -> tuple:
        return tuple((s.origin, s.destination, s.date.isoformat()) for s in slices)

    def is_free(self, slices: list[Slice]) -> bool:
        """True when searching these slices would cost nothing (memoised or already in flight)."""
        k = self.key(slices)
        return k in self._memo or k in self._inflight

    def memoised(self, slices: list[Slice]) -> list[Ticket] | None:
        """The result of an earlier search of these slices, or None if they were never searched."""
        return self._memo.get(self.key(slices))

    def known_keys(self) -> set[tuple]:
        """Keys of every search already done or in flight: repeating any of them is free."""
        return set(self._memo) | set(self._inflight)

    def exhausted(self) -> BudgetExhausted:
        return BudgetExhausted(f"search budget of {self.budget} used up")

    async def search(
        self, slices: list[Slice], max_results: int = 5, *, reason: str | None = None, hub: str | None = None
    ) -> list[Ticket]:
        key = self.key(slices)
        if key in self._memo:
            return self._memo[key]
        if key in self._inflight:
            return await self._inflight[key]
        if self.used >= self.budget:
            raise self.exhausted()
        self.used += 1
        self.trace.append(
            TraceEvent(kind="search", hub=hub, slices=list(slices), reason=reason, searches_used=self.used)
        )
        task = asyncio.ensure_future(self._fetch(slices, max_results))
        self._inflight[key] = task
        try:
            result = await task
        finally:
            self._inflight.pop(key, None)
        self._memo[key] = result
        return result

    async def _fetch(self, slices: list[Slice], max_results: int) -> list[Ticket]:
        try:
            return await self.inner.search(slices, max_results=max_results)
        except Exception:  # a failed search still spent budget; report as empty
            return []


class NoCache:
    name = "none"

    async def lowest_price(self, origin, destination, depart, return_date=None):  # noqa: ANN001
        return None
