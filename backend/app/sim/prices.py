"""The seeded price model: route level x date effect x weekday x noise.

    log fare(service, date) = log base(service)        anchor with its weekday effects divided out
                            + market level(route)       seeded, shared by both directions
                            + service offset(service)   seeded, decides which carrier is cheapest
                            + date effect(route, date)  seeded AR(1) per direction, plus rare jumps
                            + weekday(haul, date)       fixed by config
    ticket = discount(slices) x sum of slice fares x exp(ticket noise)

A cached price is the lowest of k stale observations of the same fares, each
with its own price-history noise (the service's volatility) and drifted back
by how old it is. Its optimism comes from that process, not from a constant.

Every draw is keyed on (seed, what is drawn), never on call order.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date

from app.sim.network import Service

# Mon..Sun log effects.
WEEKDAY_SHORT = (0.0, -0.06, -0.05, 0.0, 0.08, 0.10, 0.09)  # leisure positioning: strong weekends
WEEKDAY_LONG = (0.0, -0.008, -0.008, 0.0, 0.005, 0.01, 0.008)  # spec: +-3 days moved LHR-LIM by under £15


@dataclass(frozen=True)
class SimConfig:
    market_level_sd: float = 0.05
    service_sd: float = 0.03
    date_sd: float = 0.01  # stationary sd of the AR(1) date effect
    date_phi: float = 0.85
    jump_prob: float = 0.02  # chance a (route, date) sits in a dearer fare bucket
    jump_low: float = 0.15
    jump_high: float = 0.35  # spec: Sat 22 May -> Sat 5 Jun jumped from ~£700 to £930
    ticket_sd: float = 0.005  # date-pair noise; spec: +-3 days moved LHR-LIM by under £15
    return_discount: float = 0.8  # a ticket covering several slices: 0.8 x the sum of one-ways
    weekday_short: tuple[float, ...] = WEEKDAY_SHORT
    weekday_long: tuple[float, ...] = WEEKDAY_LONG
    cache_k: int = 4  # observations the cache keeps the lowest of
    cache_staleness_days: int = 7  # observations are 1..staleness days old
    cache_drift_per_day: float = 0.004  # fares rise as seats sell: older observations are lower
    cache_volatility_scale: float = 1.0
    calendar_start: date = date(2026, 11, 6)  # "today" in the simulated world; earlier dates can't be booked


# Robustness setting: one fresh observation with damped noise, so the cache is noisy but close to unbiased.
UNBIASED_CACHE = SimConfig(cache_k=1, cache_staleness_days=0, cache_drift_per_day=0.0, cache_volatility_scale=0.3)


def _key_int(*key: object) -> int:
    text = "|".join(str(k) for k in key)
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


class PriceModel:
    def __init__(self, seed: int, config: SimConfig):
        self.seed = seed
        self.cfg = config
        self._ar: dict[tuple[str, str], list[float]] = {}

    def rng(self, *key: object) -> random.Random:
        return random.Random(_key_int(self.seed, *key))

    def gauss(self, sd: float, *key: object) -> float:
        return self.rng(*key).gauss(0.0, sd) if sd else 0.0

    def weekday(self, svc: Service, day: date) -> float:
        table = self.cfg.weekday_short if svc.haul == "short" else self.cfg.weekday_long
        return table[day.weekday()]

    def base(self, svc: Service) -> float:
        """Weekday-neutral one-way fare implied by the anchor."""
        a = svc.anchor
        if a.fare == "oneway":
            return a.gbp / math.exp(self.weekday(svc, a.seen_out))
        assert a.seen_back is not None
        both = math.exp(self.weekday(svc, a.seen_out)) + math.exp(self.weekday(svc, a.seen_back))
        return a.gbp / (self.cfg.return_discount * both)

    def date_effect(self, origin: str, destination: str, day: date) -> float:
        n = (day - self.cfg.calendar_start).days
        path = self._ar.setdefault((origin, destination), [])
        c = self.cfg
        while len(path) <= n:
            z = self.gauss(1.0, "date", origin, destination, len(path))
            if not path:
                path.append(c.date_sd * z)
            else:
                path.append(c.date_phi * path[-1] + math.sqrt(1 - c.date_phi**2) * c.date_sd * z)
        r = self.rng("jump", origin, destination, day.isoformat())
        jump = r.uniform(c.jump_low, c.jump_high) if r.random() < c.jump_prob else 0.0
        return path[n] + jump

    def fare(self, svc: Service, origin: str, destination: str, day: date) -> float:
        """Expected one-way fare for one direction of a service on a date, before ticket noise."""
        market = "-".join(sorted((origin, destination)))
        log_mult = (
            self.gauss(self.cfg.market_level_sd, "market", market)
            + self.gauss(self.cfg.service_sd, "service", svc.name)
            + self.date_effect(origin, destination, day)
            + self.weekday(svc, day)
        )
        return self.base(svc) * math.exp(log_mult)

    def bookable(self, day: date) -> bool:
        return day >= self.cfg.calendar_start
