"""The benchmark trips: variants of the one Lima trip, each with a preference profile.

Windows, flexibility, trip shape (open-jaw from La Paz or a Lima return) and the
person's preferences are what vary; the route network never does. The first two
are one-day windows so quick checks stay quick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.models import Preferences, TripRequest


@dataclass(frozen=True)
class BenchTrip:
    name: str
    request: TripRequest
    prefs: Preferences = field(default_factory=Preferences)
    why: str = ""


def _req(out: date, back: date, flex: int = 1, return_from: str | None = "LPB") -> TripRequest:
    return TripRequest(
        origin="EDI",
        destination="LIM",
        return_from=return_from,
        depart_earliest=out,
        depart_latest=out + timedelta(days=flex - 1),
        return_earliest=back,
        return_latest=back + timedelta(days=flex - 1),
    )


SAT_22_MAY, SUN_6_JUN = date(2027, 5, 22), date(2027, 6, 6)

BENCHMARK_TRIPS: list[BenchTrip] = [
    BenchTrip("oj-spec-dates", _req(SAT_22_MAY, SUN_6_JUN), why="the spec's trip, fixed dates"),
    BenchTrip("rt-spec-dates", _req(SAT_22_MAY, SUN_6_JUN, return_from=None), why="the same dates as a Lima return"),
    BenchTrip("oj-flex3", _req(date(2027, 5, 21), date(2027, 6, 5), 3), why="a few days either way"),
    BenchTrip("rt-flex3", _req(date(2027, 5, 21), date(2027, 6, 5), 3, return_from=None)),
    BenchTrip(
        "oj-flex7",
        _req(date(2027, 5, 19), date(2027, 6, 2), 7),
        why="the spec's search space: 7 outbound x 7 return dates",
    ),
    BenchTrip("oj-early-may", _req(date(2027, 5, 1), date(2027, 5, 15), 4), why="another window, same route"),
    BenchTrip("oj-late-june", _req(date(2027, 6, 12), date(2027, 6, 26), 4)),
    BenchTrip(
        "oj-stopover-lover",
        _req(date(2027, 5, 21), date(2027, 6, 5), 3),
        Preferences(stopover_bonus=150),
        "rates a night in a hub at the top of the spec's +£50-150",
    ),
    BenchTrip(
        "oj-no-stopovers",
        _req(date(2027, 5, 21), date(2027, 6, 5), 3),
        Preferences(stopover_bonus=0, hotel_cost_per_night=120),
        "a hub night is pure cost",
    ),
    BenchTrip(
        "oj-time-poor",
        _req(date(2027, 5, 21), date(2027, 6, 5), 3),
        Preferences(value_of_hour=30, per_stop=60),
        "pays for speed and fewer stops",
    ),
    BenchTrip(
        "oj-budget-traveller",
        _req(date(2027, 5, 21), date(2027, 6, 5), 3),
        Preferences(value_of_hour=4, per_stop=10, allow_same_day_self_transfer=True, min_self_transfer_hours=3),
        "cheap time, accepts same-day self-transfers with a 3 h buffer",
    ),
    BenchTrip(
        "rt-one-week",
        _req(SAT_22_MAY, date(2027, 5, 29), 2, return_from=None),
        why="a short trip: return and stay length interact",
    ),
]
