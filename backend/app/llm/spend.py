"""Monthly spend cap for LLM calls.

Every call is checked before it is made and recorded after, at the model's
list price. Spend resets each calendar month (UTC). With a ledger path the
running totals survive restarts; without one they live in memory.

Prices are per 1M tokens in USD and must be confirmed against
https://openai.com/api/pricing: they could not be fetched from the build
environment. A model with no price is refused (fail closed), because a cap
can't count spend it can't price.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class SpendCapReached(RuntimeError):
    pass


class UnpricedModel(RuntimeError):
    pass


@dataclass(frozen=True)
class Price:
    input: float  # USD per 1M input tokens
    cached_input: float  # USD per 1M cached input tokens
    output: float  # USD per 1M output tokens (reasoning tokens included)
    source: str


PRICES: dict[str, Price] = {
    # Quoted from OpenAI's models page via a search result on 2026-11-07; not fetched directly. Confirm before use.
    "gpt-6-astra": Price(10.0, 1.0, 50.0, "developers.openai.com/api/docs/models via search snippet, 2026-11-07"),
}


def cost_usd(model: str, usage: dict[str, int], prices: dict[str, Price] = PRICES) -> float:
    if model not in prices:
        raise UnpricedModel(f"no price for {model!r}; add it to app/llm/spend.py PRICES from openai.com/api/pricing")
    p = prices[model]
    cached = usage.get("cached_tokens", 0)
    fresh = max(usage.get("input_tokens", 0) - cached, 0)
    return (fresh * p.input + cached * p.cached_input + usage.get("output_tokens", 0) * p.output) / 1_000_000


class SpendGuard:
    def __init__(
        self,
        cap_usd: float,
        ledger_path: str | Path | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.cap_usd = cap_usd
        self.path = Path(ledger_path) if ledger_path else None
        self.clock = clock
        self._lock = threading.Lock()
        self._months: dict[str, float] = {}
        if self.path and self.path.exists():
            self._months = {k: float(v) for k, v in json.loads(self.path.read_text()).items()}

    def _month(self) -> str:
        return self.clock().strftime("%Y-%m")

    def spent(self) -> float:
        """Recorded spend this calendar month, in USD."""
        return self._months.get(self._month(), 0.0)

    def reached(self) -> bool:
        return self.spent() >= self.cap_usd

    def check(self) -> None:
        """Raise SpendCapReached if this month's recorded spend has reached the cap."""
        if self.reached():
            raise SpendCapReached(f"LLM spend this month ${self.spent():.2f} has reached the ${self.cap_usd:.2f} cap")

    def check_priced(self, model: str) -> None:
        """Check the cap, and refuse models the guard can't price."""
        if model not in PRICES:
            raise UnpricedModel(
                f"no price for {model!r}; add it to app/llm/spend.py PRICES from openai.com/api/pricing"
            )
        self.check()

    def record(self, cost_usd: float) -> None:
        with self._lock:
            month = self._month()
            self._months[month] = self._months.get(month, 0.0) + cost_usd
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self._months, indent=1, sort_keys=True))
