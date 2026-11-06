"""Fare source interfaces.

Two kinds of source, matching the spec:
- LiveFareProvider: real bookable options for a list of slices. Costs a
  "search" from the budget.
- CachedFareProvider: cheap, possibly stale lowest prices, used only to
  bound and prune. Free.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.models import Slice, Ticket


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
    """Wraps a live provider: counts searches, enforces the budget, memoises."""

    def __init__(self, inner: LiveFareProvider, budget: int):
        self.inner = inner
        self.name = inner.name
        self.budget = budget
        self.used = 0
        self._memo: dict[tuple, list[Ticket]] = {}

    @property
    def remaining(self) -> int:
        return self.budget - self.used

    async def search(self, slices: list[Slice], max_results: int = 5) -> list[Ticket]:
        key = tuple((s.origin, s.destination, s.date.isoformat()) for s in slices)
        if key in self._memo:
            return self._memo[key]
        if self.used >= self.budget:
            raise BudgetExhausted(f"search budget of {self.budget} used up")
        self.used += 1
        try:
            result = await self.inner.search(slices, max_results=max_results)
        except Exception:  # a failed search still spent budget; report as empty
            result = []
        self._memo[key] = result
        return result


class NoCache:
    name = "none"

    async def lowest_price(self, origin, destination, depart, return_date=None):  # noqa: ANN001
        return None
