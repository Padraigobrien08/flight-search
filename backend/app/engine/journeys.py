"""Turn legs (possibly from several tickets) into journeys with connections."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from app.models import Connection, Journey, Leg

# Airports that count as one place for connections. A change between them is
# allowed but costs transfer time and is flagged.
CITY_GROUPS: dict[str, set[str]] = {
    "LON": {"LHR", "LGW", "STN", "LTN", "LCY", "SEN"},
    "PAR": {"CDG", "ORY", "BVA"},
    "MIL": {"MXP", "LIN", "BGY"},
    "ROM": {"FCO", "CIA"},
    "NYC": {"JFK", "EWR", "LGA"},
    "MAD": {"MAD"},
    "BCN": {"BCN"},
    "LIS": {"LIS"},
    "AMS": {"AMS"},
}

AIRPORT_TO_CITY = {ap: city for city, aps in CITY_GROUPS.items() for ap in aps}

HUB_NIGHT_MIN_HOURS = 12
AIRPORT_TRANSFER_MINUTES = 120  # extra time assumed for changing airport


def city_of(code: str) -> str:
    return AIRPORT_TO_CITY.get(code, code)


def same_place(a: str, b: str) -> bool:
    return a == b or city_of(a) == city_of(b)


def night_overlap_minutes(start: datetime, end: datetime) -> int:
    """Minutes of [start, end] falling between 00:00 and 06:00 local time."""
    if end <= start:
        return 0
    total = 0
    day = start.date()
    while datetime.combine(day, time(0)) < end:
        window_start = datetime.combine(day, time(0))
        window_end = window_start + timedelta(hours=6)
        lo, hi = max(start, window_start), min(end, window_end)
        if hi > lo:
            total += int((hi - lo).total_seconds() // 60)
        day += timedelta(days=1)
    return total


def build_journey(legs: list[Leg], ticket_of_leg: list[int]) -> Journey | None:
    """Assemble a journey; return None if the legs can't physically connect."""
    connections: list[Connection] = []
    for i in range(1, len(legs)):
        prev, nxt = legs[i - 1], legs[i]
        if not same_place(prev.destination, nxt.origin):
            return None
        minutes = int((nxt.depart - prev.arrive).total_seconds() // 60)
        between_tickets = ticket_of_leg[i] != ticket_of_leg[i - 1]
        if prev.destination != nxt.origin:
            # Changing airport within a city: needs extra time.
            minutes_needed = AIRPORT_TRANSFER_MINUTES
        else:
            minutes_needed = 45 if between_tickets else 0
        if minutes < minutes_needed:
            return None
        night = night_overlap_minutes(prev.arrive, nxt.depart)
        hub_night = between_tickets and minutes >= HUB_NIGHT_MIN_HOURS * 60 and night > 0
        connections.append(
            Connection(
                airport=nxt.origin if prev.destination == nxt.origin else f"{prev.destination}->{nxt.origin}",
                minutes=minutes,
                night_minutes=night,
                between_tickets=between_tickets,
                hub_night=hub_night,
                nights=max(1, (nxt.depart.date() - prev.arrive.date()).days) if hub_night else 0,
            )
        )
    return Journey(legs=legs, connections=connections)
