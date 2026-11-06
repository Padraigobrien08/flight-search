"""Static route knowledge: which hubs are worth considering for a destination.

This is the "route map first" rule. It is free, fixed data; extend it per
destination. Each hub lists the airport its long-haul leaves from and the
airports a positioning flight from home may arrive at.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hub:
    city: str
    longhaul_airport: str
    arrival_airports: tuple[str, ...]


HUBS: dict[str, Hub] = {
    "MAD": Hub("Madrid", "MAD", ("MAD",)),
    "LON": Hub("London", "LHR", ("LHR", "STN", "LTN")),
    "PAR": Hub("Paris", "CDG", ("CDG",)),
    "AMS": Hub("Amsterdam", "AMS", ("AMS",)),
    "LIS": Hub("Lisbon", "LIS", ("LIS",)),
    "BCN": Hub("Barcelona", "BCN", ("BCN",)),
}

# Hubs with good long-haul service to each destination.
GATEWAYS: dict[str, list[str]] = {
    "LIM": ["MAD", "LON", "PAR", "AMS", "LIS", "BCN"],
}

DEFAULT_HUBS = ["MAD", "LON", "PAR", "AMS"]


def hubs_for(destination: str, requested: list[str] | None = None) -> list[str]:
    if requested:
        return [h for h in requested if h in HUBS]
    return GATEWAYS.get(destination, DEFAULT_HUBS)
