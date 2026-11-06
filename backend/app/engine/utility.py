"""Score itineraries in pounds, apply hard limits, and keep the Pareto front.

U = -(fares + extras) - v_t * hours - v_n * night_wait_hours - penalties + bonuses

Higher is better. Every term is reported in the breakdown so the explanation
layer can cite real numbers instead of inventing them.
"""

from __future__ import annotations

from app.models import Itinerary, Preferences, ScoredItinerary


def violations(it: Itinerary, prefs: Preferences) -> list[str]:
    """Hard-limit violations; any violation removes the itinerary."""
    out: list[str] = []
    for j in it.journeys:
        if j.travel_minutes / 60 > prefs.max_journey_hours:
            out.append(f"journey over {prefs.max_journey_hours:g} h")
        if j.stops > prefs.max_stops:
            out.append(f"more than {prefs.max_stops} stops")
        for c in j.connections:
            if c.hub_night:
                continue
            if c.between_tickets:
                if not prefs.allow_same_day_self_transfer:
                    out.append(f"same-day self-transfer at {c.airport}")
                elif c.minutes < prefs.min_self_transfer_hours * 60:
                    out.append(f"self-transfer under {prefs.min_self_transfer_hours:g} h at {c.airport}")
            if not prefs.allow_airport_overnight and c.night_minutes >= 180 and c.minutes >= 6 * 60:
                out.append(f"night in the airport at {c.airport}")
    return out


def score(it: Itinerary, prefs: Preferences) -> ScoredItinerary:
    b: dict[str, float] = {}
    b["fares"] = -it.fare_total
    b["extras"] = -it.extra_cost
    flags: list[str] = []

    hours = sum(j.travel_minutes for j in it.journeys) / 60
    b["travel_time"] = -prefs.value_of_hour * hours

    night_wait = sum(c.night_minutes for j in it.journeys for c in j.connections if not c.hub_night) / 60
    b["night_waiting"] = -prefs.value_of_night_hour * night_wait

    stops = sum(j.stops for j in it.journeys)
    b["stops"] = -prefs.per_stop * stops

    conn_pen = 0.0
    self_transfer_pen = 0.0
    hub_nights = 0
    for j in it.journeys:
        for c in j.connections:
            if c.hub_night:
                hub_nights += 1
                continue
            tight = 90 if c.between_tickets else 60
            if c.minutes < tight:
                conn_pen += prefs.short_connection_penalty
                flags.append(f"tight {c.minutes} min connection at {c.airport}")
            elif c.minutes > 6 * 60:
                conn_pen += prefs.long_connection_penalty
                flags.append(f"{c.minutes // 60} h wait at {c.airport}")
            if c.between_tickets:
                self_transfer_pen += prefs.self_transfer_penalty
                flags.append(f"self-transfer at {c.airport} (separate tickets)")
            if "->" in c.airport:
                flags.append(f"change of airport {c.airport}")
    b["connections"] = -conn_pen
    b["self_transfer"] = -self_transfer_pen

    b["stopover"] = prefs.stopover_bonus * hub_nights
    if hub_nights:
        flags.append(f"{hub_nights} planned stay(s) in {it.hub}, {sum(c.nights for j in it.journeys for c in j.connections)} night(s)")

    red_eye = sum(1 for j in it.journeys if 0 <= j.arrival.hour < 6)
    b["red_eye_arrival"] = -prefs.red_eye_arrival_penalty * red_eye
    if red_eye:
        flags.append("lands between 00:00 and 06:00")

    for t in it.tickets:
        if t.self_transfer_inside:
            flags.append("provider flags a self-transfer inside one ticket")

    b = {k: round(v, 2) for k, v in b.items()}
    return ScoredItinerary(itinerary=it, utility=round(sum(b.values()), 2), breakdown=b, flags=flags)


def pareto_front(items: list[ScoredItinerary]) -> list[ScoredItinerary]:
    """Drop anything another option beats on cost, time and risk together."""

    def key(s: ScoredItinerary) -> tuple[float, float, float]:
        it = s.itinerary
        hours = sum(j.travel_minutes for j in it.journeys)
        risk = -s.breakdown.get("self_transfer", 0.0) - s.breakdown.get("connections", 0.0)
        return (it.total_cost, hours, risk)

    keys = [key(s) for s in items]
    front = []
    for i, s in enumerate(items):
        ki = keys[i]
        dominated = any(
            all(kj[d] <= ki[d] for d in range(3)) and any(kj[d] < ki[d] for d in range(3))
            for j, kj in enumerate(keys)
            if j != i
        )
        # A planned stopover is a benefit the dominance key can't see; keep those.
        if not dominated or s.breakdown.get("stopover", 0) > 0:
            front.append(s)
    return front


def rank(items: list[ScoredItinerary], prefs: Preferences, top_k: int = 5) -> list[ScoredItinerary]:
    feasible = [s for s in items if not violations(s.itinerary, prefs)]
    front = pareto_front(feasible)
    front.sort(key=lambda s: s.utility, reverse=True)
    # Deduplicate near-identical options (same tickets' legs).
    seen: set[tuple] = set()
    out: list[ScoredItinerary] = []
    for s in front:
        sig = tuple(
            (leg.carrier, leg.flight_number, leg.depart.isoformat())
            for j in s.itinerary.journeys
            for leg in j.legs
        )
        if sig in seen:
            continue
        seen.add(sig)
        out.append(s)
        if len(out) == top_k:
            break
    if out:
        cheapest = min(s.itinerary.total_cost for s in out)
        for i, s in enumerate(out, 1):
            s.rank = i
            s.vs_cheapest = round(s.itinerary.total_cost - cheapest, 2)
    return out
