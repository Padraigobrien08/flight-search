"""The simulated route network: fixed data, never seeded.

Which services exist, when they fly, and the real fares they are anchored to.
The reasons behind each part are in NETWORK.md. The seeded price model in
`prices.py` turns these anchors into fares; a seed never changes this file's
answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

from app.models import Leg

SEEN_OUT = date(2027, 5, 22)  # Sat: the outbound date of the spec's 6 Nov 2026 searches
SEEN_BACK = date(2027, 6, 6)  # Sun: the return date

# The 0.8 used to turn La Paz premiums into one-way anchors (a return is 0.8 x two one-ways).
LAPAZ_DERIVATION_DISCOUNT = 0.8

DAILY = frozenset(range(7))
MON_THU_SAT = frozenset({0, 3, 5})

# Late-May UTC offsets, enough to make local arrival times realistic.
UTC_OFFSET = {
    "EDI": 1,
    "LHR": 1,
    "STN": 1,
    "LTN": 1,
    "LIS": 1,
    "MAD": 2,
    "BCN": 2,
    "CDG": 2,
    "AMS": 2,
    "LIM": -5,
    "BOG": -5,
    "LPB": -4,
    "VVI": -4,
    "YYZ": -4,
    "YUL": -4,
}

Source = Literal["spec", "fixture", "design"]


@dataclass(frozen=True)
class Hop:
    carrier: str
    origin: str
    destination: str
    minutes: int


@dataclass(frozen=True)
class Schedule:
    """One direction of a service: hops, the layovers between them, and the local departure time."""

    hops: tuple[Hop, ...]
    layovers: tuple[int, ...]
    depart: time

    @property
    def origin(self) -> str:
        return self.hops[0].origin

    @property
    def destination(self) -> str:
        return self.hops[-1].destination

    def legs(self, day: date) -> list[Leg]:
        out: list[Leg] = []
        clock = datetime.combine(day, self.depart)  # local time at the hop's origin
        for i, hop in enumerate(self.hops):
            arrive = (
                clock
                + timedelta(minutes=hop.minutes)
                + timedelta(hours=UTC_OFFSET[hop.destination] - UTC_OFFSET[hop.origin])
            )
            out.append(
                Leg(
                    carrier=hop.carrier,
                    flight_number=f"{hop.carrier[:2].upper()}{100 + i}",
                    origin=hop.origin,
                    destination=hop.destination,
                    depart=clock,
                    arrive=arrive,
                    duration_min=hop.minutes,
                )
            )
            if i < len(self.layovers):
                clock = arrive + timedelta(minutes=self.layovers[i])
        return out


@dataclass(frozen=True)
class Anchor:
    """An observed fare: what was paid, for which dates, and where the number comes from."""

    gbp: float
    fare: Literal["return", "oneway"]
    source: Source
    note: str
    seen_out: date = SEEN_OUT
    seen_back: date | None = SEEN_BACK


@dataclass(frozen=True)
class Service:
    name: str  # stable id: seeds are keyed on it
    haul: Literal["short", "long"]
    out: Schedule
    back: Schedule | None  # None: sold one way only
    anchor: Anchor
    volatility: float  # log-sd of its price history; drives the cache's optimism
    days: frozenset[int] = DAILY  # weekdays it departs (both directions)


def S(depart: str, hops: list[tuple[str, str, str, int]], layovers: list[int] | None = None) -> Schedule:
    h, m = map(int, depart.split(":"))
    return Schedule(tuple(Hop(*x) for x in hops), tuple(layovers or []), time(h, m))


def ret(gbp: float, source: Source, note: str) -> Anchor:
    return Anchor(gbp, "return", source, note)


def lapaz(hub_return: float, premium: float, note: str) -> Anchor:
    """One-way La Paz anchor derived from a design premium over the hub's Lima return (NETWORK.md)."""
    gbp = round(hub_return / (2 * LAPAZ_DERIVATION_DISCOUNT) + premium / LAPAZ_DERIVATION_DISCOUNT, 2)
    return Anchor(gbp, "oneway", "design", f"premium £{premium:g} over £{hub_return:g}; {note}", SEEN_BACK, None)


LEGACY, LOW_COST, VOLATILE = 0.05, 0.12, 0.25

SERVICES: tuple[Service, ...] = (
    # --- Positioning from Edinburgh (return fares) ---
    Service(
        "EDI-MAD/easyJet",
        "short",
        S("06:00", [("easyJet", "EDI", "MAD", 165)]),
        S("10:05", [("easyJet", "MAD", "EDI", 170)]),
        ret(168, "spec", "pruning rule 3: Madrid £168 positioning"),
        LOW_COST,
    ),
    Service(
        "EDI-MAD/Ryanair",
        "short",
        S("16:25", [("Ryanair", "EDI", "MAD", 175)]),
        S("20:35", [("Ryanair", "MAD", "EDI", 175)]),
        ret(272, "fixture", ""),
        LOW_COST,
    ),
    Service(
        "EDI-STN/Ryanair",
        "short",
        S("07:00", [("Ryanair", "EDI", "STN", 85)]),
        S("19:20", [("Ryanair", "STN", "EDI", 80)]),
        ret(52, "spec", "pruning rule 3: London £52 positioning; 1h25 in the worked example"),
        LOW_COST,
    ),
    Service(
        "EDI-LTN/easyJet",
        "short",
        S("08:55", [("easyJet", "EDI", "LTN", 80)]),
        S("20:10", [("easyJet", "LTN", "EDI", 80)]),
        ret(76, "fixture", ""),
        LOW_COST,
    ),
    Service(
        "EDI-LHR/BA",
        "short",
        S("07:10", [("British Airways", "EDI", "LHR", 85)]),
        S("18:40", [("British Airways", "LHR", "EDI", 85)]),
        ret(140, "fixture", ""),
        0.06,
    ),
    Service(
        "EDI-CDG/easyJet",
        "short",
        S("11:05", [("easyJet", "EDI", "CDG", 110)]),
        S("14:30", [("easyJet", "CDG", "EDI", 105)]),
        ret(153, "fixture", ""),
        LOW_COST,
    ),
    Service(
        "EDI-AMS/KLM",
        "short",
        S("06:00", [("KLM", "EDI", "AMS", 80)]),
        S("21:10", [("KLM", "AMS", "EDI", 85)]),
        ret(190, "fixture", ""),
        0.06,
    ),
    Service(
        "EDI-LIS/easyJet",
        "short",
        S("06:30", [("easyJet", "EDI", "LIS", 175)]),
        S("10:45", [("easyJet", "LIS", "EDI", 170)]),
        ret(215, "fixture", ""),
        LOW_COST,
    ),
    Service(
        "EDI-BCN/Ryanair",
        "short",
        S("11:40", [("Ryanair", "EDI", "BCN", 160)]),
        S("15:05", [("Ryanair", "BCN", "EDI", 165)]),
        ret(188, "fixture", ""),
        LOW_COST,
    ),
    # --- Long-haul from the hubs (return fares) ---
    Service(
        "MAD-LIM/AirEuropa",
        "long",
        S("23:45", [("Air Europa", "MAD", "LIM", 705)]),
        S("20:00", [("Air Europa", "LIM", "MAD", 680)]),
        ret(743, "spec", "pruning rule 3: Madrid £743 long-haul; 11h45 non-stop in the worked example"),
        LEGACY,
    ),
    Service(
        "MAD-LIM/Iberia",
        "long",
        S("13:10", [("Iberia", "MAD", "LIM", 720)]),
        S("18:45", [("Iberia", "LIM", "MAD", 690)]),
        ret(769, "fixture", ""),
        LEGACY,
    ),
    Service(
        "LHR-LIM/Avianca",
        "long",
        S("22:05", [("Avianca", "LHR", "BOG", 640), ("Avianca", "BOG", "LIM", 215)], [255]),
        S("07:40", [("Avianca", "LIM", "BOG", 205), ("Avianca", "BOG", "LHR", 600)], [150]),
        ret(710, "spec", "pruning rule 3: London £710 long-haul; 18h30 with 4h15 in Bogotá"),
        LEGACY,
    ),
    Service(
        "LHR-LIM/Iberia",
        "long",
        S("09:00", [("Iberia", "LHR", "MAD", 140), ("Iberia", "MAD", "LIM", 720)], [50]),
        S("18:45", [("Iberia", "LIM", "MAD", 690), ("Iberia", "MAD", "LHR", 145)], [85]),
        ret(858, "fixture", ""),
        LEGACY,
    ),
    Service(
        "CDG-LIM/AirFrance-Avianca",
        "long",
        S("08:55", [("Air France", "CDG", "BOG", 660), ("Avianca", "BOG", "LIM", 200)], [280]),
        S("06:30", [("Avianca", "LIM", "BOG", 200), ("Air France", "BOG", "CDG", 630)], [240]),
        ret(774, "fixture", "fixture had Avianca on CDG-BOG"),
        LEGACY,
    ),
    Service(
        "CDG-LIM/AirFrance",
        "long",
        S("10:10", [("Air France", "CDG", "LIM", 755)]),
        S("17:30", [("Air France", "LIM", "CDG", 715)]),
        ret(1086, "fixture", ""),
        LEGACY,
    ),
    Service(
        "AMS-LIM/KLM",
        "long",
        S("09:40", [("KLM", "AMS", "LIM", 765)]),
        S("17:00", [("KLM", "LIM", "AMS", 740)]),
        ret(850, "design", "spec: £700-850 from every hub (upper end); fixture had £950"),
        LEGACY,
    ),
    Service(
        "LIS-LIM/AirEuropa",
        "long",
        S("20:05", [("Air Europa", "LIS", "MAD", 75), ("Air Europa", "MAD", "LIM", 705)], [85]),
        S("20:00", [("Air Europa", "LIM", "MAD", 680), ("Air Europa", "MAD", "LIS", 80)], [100]),
        ret(728, "fixture", ""),
        LEGACY,
    ),
    Service(
        "BCN-LIM/LEVEL",
        "long",
        S("13:40", [("LEVEL", "BCN", "LIM", 775)]),
        S("17:55", [("LEVEL", "LIM", "BCN", 750)]),
        ret(766, "fixture", ""),
        VOLATILE,
    ),
    # --- Through tickets Edinburgh <-> Lima (return fares) ---
    Service(
        "EDI-LIM/KLM",
        "long",
        S("06:00", [("KLM", "EDI", "AMS", 80), ("KLM", "AMS", "LIM", 765)], [80]),
        S("17:00", [("KLM", "LIM", "AMS", 740), ("KLM", "AMS", "EDI", 85)], [100]),
        ret(1174, "spec", "worked example: via Amsterdam, 15h25, 1 stop"),
        LEGACY,
    ),
    Service(
        "EDI-LIM/AirFrance",
        "long",
        S("05:40", [("Air France", "EDI", "CDG", 105), ("Air France", "CDG", "LIM", 755)], [105]),
        S("17:30", [("Air France", "LIM", "CDG", 715), ("Air France", "CDG", "EDI", 105)], [125]),
        ret(1097, "fixture", ""),
        LEGACY,
    ),
    Service(
        "EDI-LIM/AirFrance-Avianca",
        "long",
        S(
            "11:35",
            [("Air France", "EDI", "CDG", 115), ("Air France", "CDG", "BOG", 660), ("Avianca", "BOG", "LIM", 200)],
            [120, 70],
        ),
        S(
            "06:30",
            [("Avianca", "LIM", "BOG", 200), ("Air France", "BOG", "CDG", 630), ("Air France", "CDG", "EDI", 105)],
            [240, 150],
        ),
        ret(942, "fixture", ""),
        LEGACY,
    ),
    Service(
        "EDI-LIM/Iberia",
        "long",
        S("06:20", [("Iberia", "EDI", "MAD", 165), ("Iberia", "MAD", "LIM", 720)], [185]),
        S("18:45", [("Iberia", "LIM", "MAD", 690), ("Iberia", "MAD", "EDI", 170)], [120]),
        ret(985, "design", "between the Madrid split (£911) and Air France via Paris (£1,097)"),
        LEGACY,
    ),
    Service(
        "EDI-LIM/AirCanada",
        "long",
        S(
            "09:00",
            [("Air Canada", "EDI", "YYZ", 450), ("Air Canada", "YYZ", "YUL", 80), ("Air Canada", "YUL", "LIM", 420)],
            [150, 165],
        ),
        S(
            "23:30",
            [("Air Canada", "LIM", "YUL", 425), ("Air Canada", "YUL", "YYZ", 85), ("Air Canada", "YYZ", "EDI", 415)],
            [140, 170],
        ),
        ret(915, "spec", "worked example: via Toronto and Montréal, 21h, 2 stops"),
        LEGACY,
    ),
    # --- The La Paz end (one-way fares, seen for Sun 6 Jun) ---
    Service(
        "LPB-MAD/BoA-AirEuropa",
        "long",
        S("15:40", [("BoA", "LPB", "VVI", 60), ("Air Europa", "VVI", "MAD", 650)], [170]),
        None,
        lapaz(743, 150, "the best La Paz link, Mon/Thu/Sat only"),
        0.08,
        MON_THU_SAT,
    ),
    Service(
        "LPB-MAD/Avianca",
        "long",
        S("03:25", [("Avianca", "LPB", "BOG", 225), ("Avianca", "BOG", "MAD", 585)], [95]),
        None,
        lapaz(743, 230, ""),
        LEGACY,
    ),
    Service(
        "LPB-LHR/Avianca",
        "long",
        S("03:25", [("Avianca", "LPB", "BOG", 225), ("Avianca", "BOG", "LHR", 600)], [255]),
        None,
        lapaz(710, 230, ""),
        LEGACY,
    ),
    Service(
        "LPB-CDG/Avianca-AirFrance",
        "long",
        S("03:25", [("Avianca", "LPB", "BOG", 225), ("Air France", "BOG", "CDG", 630)], [240]),
        None,
        lapaz(774, 200, ""),
        LEGACY,
    ),
    Service(
        "LPB-BCN/Avianca",
        "long",
        S("03:25", [("Avianca", "LPB", "BOG", 225), ("Avianca", "BOG", "BCN", 600)], [180]),
        None,
        lapaz(766, 210, ""),
        LEGACY,
    ),
    Service(
        "LPB-AMS/Avianca-KLM",
        "long",
        S("03:25", [("Avianca", "LPB", "BOG", 225), ("KLM", "BOG", "AMS", 640)], [200]),
        None,
        lapaz(850, 220, ""),
        LEGACY,
    ),
    Service(
        "LPB-EDI/Avianca-KLM",
        "long",
        S(
            "03:25",
            [("Avianca", "LPB", "BOG", 225), ("KLM", "BOG", "AMS", 640), ("KLM", "AMS", "EDI", 85)],
            [120, 140],
        ),
        None,
        lapaz(915, 200, "over the cheapest through return (Air Canada)"),
        LEGACY,
    ),
    Service(
        "LPB-LIM/BoA",
        "long",
        S("15:40", [("BoA", "LPB", "VVI", 60), ("BoA", "VVI", "LIM", 175)], [195]),
        None,
        Anchor(226, "oneway", "fixture", "", SEEN_BACK, None),
        0.08,
    ),
    Service(
        "LPB-LIM/Avianca",
        "long",
        S("03:25", [("Avianca", "LPB", "BOG", 225), ("Avianca", "BOG", "LIM", 200)], [75]),
        None,
        Anchor(234, "oneway", "fixture", "", SEEN_BACK, None),
        LEGACY,
    ),
)


def schedules(origin: str, destination: str) -> list[tuple[Service, Schedule]]:
    """Every service selling origin -> destination, with the schedule for that direction."""
    out: list[tuple[Service, Schedule]] = []
    for svc in SERVICES:
        for sched in (svc.out, svc.back):
            if sched is not None and sched.origin == origin and sched.destination == destination:
                out.append((svc, sched))
    return out
