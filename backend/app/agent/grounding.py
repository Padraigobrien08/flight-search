"""Grounding check: every money amount and duration an LLM writes must come from tool output.

A claim is a number with a unit: a currency (£1,060, £1.2k, 900 GBP) or a duration
(12 hours, 15h25, 4 hours 15 minutes, 45 min). Numbers without a unit (dates, ranks,
counts such as "2 stops" or "option 1 of 5") are not claims about prices or durations
and are ignored.

Supporting values are typed by where they sit in the tool output: a money claim can only
be supported by a money field (price, total_cost, vs_cheapest, the utility breakdown...),
a duration only by an hours or minutes field. So `searches_used: 16` can't vouch for
"16 hours". Strings inside the output (and outputs that aren't JSON) are read with the
same claim parser, so "£1,060" or "11h45" in a tool's text counts as support.

Tolerance: £1 for money (more for amounts written in thousands, "£1.2k"), 0.1 h for durations.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

Kind = Literal["money", "hours"]
MONEY_TOLERANCE = 1.0
HOURS_TOLERANCE = 0.1
EPS = 1e-9

MONEY_KEYS = (
    "gbp", "cost", "price", "fare", "fee", "total", "cheapest", "extra", "saving",
    "bonus", "penalty", "utility", "breakdown", "regret", "bound",
)  # fmt: skip
HOUR_KEYS = ("hour",)
MINUTE_KEYS = ("minute", "_min")

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_MONEY = re.compile(
    rf"(?P<cur>[£$€])\s?(?P<a>{_NUM})(?P<k>\s?[kK]\b)?"
    rf"|(?<![\w.])(?P<b>{_NUM})\s?(?:GBP|pounds?|quid)\b",
    re.IGNORECASE,
)
_DURATION = re.compile(
    r"(?<![\w.])(?P<ch>\d+)h(?P<cm>\d{1,2})\b"  # 15h25
    r"|(?<![\w.])(?P<h>\d+(?:\.\d+)?)\s*-?\s*(?:hours?|hrs?|h)\b"
    r"(?:\s*(?:and\s+)?(?P<hm>\d{1,2})\s*-?\s*(?:minutes?|mins?|m)\b)?"  # 4 hours 15 minutes, 4h 15m
    r"|(?<![\w.])(?P<m>\d+(?:\.\d+)?)\s*-?\s*(?:minutes?|mins?)\b",  # 45 minutes
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Claim:
    text: str
    kind: Kind
    value: float
    tolerance: float
    start: int


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def claims(text: str) -> list[Claim]:
    """Money amounts and durations in text, in order."""
    out: list[Claim] = []
    for m in _MONEY.finditer(text):
        raw = m.group("a") or m.group("b")
        value, tol = _num(raw), MONEY_TOLERANCE
        if m.group("k"):
            decimals = len(raw.split(".")[1]) if "." in raw else 0
            value, tol = value * 1000, max(MONEY_TOLERANCE, 500 * 10**-decimals)
        out.append(Claim(m.group(0).strip(), "money", value, tol, m.start()))
    for m in _DURATION.finditer(text):
        if m.group("ch"):
            hours = int(m.group("ch")) + int(m.group("cm")) / 60
        elif m.group("h"):
            hours = _num(m.group("h")) + (int(m.group("hm")) / 60 if m.group("hm") else 0)
        else:
            hours = _num(m.group("m")) / 60
        out.append(Claim(m.group(0).strip(), "hours", hours, HOURS_TOLERANCE, m.start()))
    return sorted(out, key=lambda c: c.start)


def _kind_of(path: list[str]) -> tuple[Kind, float] | None:
    """(kind, multiplier to that kind's unit) for a number at this key path, innermost key first."""
    for key in reversed(path):
        k = key.lower()
        if any(s in k for s in MINUTE_KEYS):
            return "hours", 1 / 60
        if any(s in k for s in HOUR_KEYS):
            return "hours", 1.0
        if any(s in k for s in MONEY_KEYS):
            return "money", 1.0
    return None


def _walk(node: Any, path: list[str], pools: dict[Kind, list[float]]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            _walk(v, [*path, str(k)], pools)
    elif isinstance(node, list):
        for v in node:
            _walk(v, path, pools)
    elif isinstance(node, bool):
        return
    elif isinstance(node, int | float):
        typed = _kind_of(path)
        if typed:
            kind, mult = typed
            pools[kind].append(abs(node) * mult)
    elif isinstance(node, str):
        for c in claims(node):
            pools[c.kind].append(c.value)


def supported_values(tool_outputs: Iterable[str]) -> dict[Kind, list[float]]:
    pools: dict[Kind, list[float]] = {"money": [], "hours": []}
    for output in tool_outputs:
        try:
            _walk(json.loads(output), [], pools)
        except (json.JSONDecodeError, TypeError):
            _walk(output, [], pools)
    return pools


def unsupported_numbers(text: str, tool_outputs: Iterable[str]) -> list[str]:
    """Every money amount or duration in `text` that no tool output supports, as written, in order."""
    pools = supported_values(tool_outputs)
    bad: list[str] = []
    for c in claims(text):
        if not any(abs(abs(c.value) - v) <= c.tolerance + EPS for v in pools[c.kind]) and c.text not in bad:
            bad.append(c.text)
    return bad
