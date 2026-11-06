"""Core data model: what a ticket, a journey and an itinerary are.

Times are local to the airport they refer to (that is what every fare source
returns). Durations therefore come from the provider per leg, and a
connection is only ever measured at a single airport, where both local
times share a timezone.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field

Structure = Literal["through", "split", "stopover"]


class Leg(BaseModel):
    """One flight (or train) between two places."""

    carrier: str
    flight_number: str | None = None
    origin: str
    destination: str
    depart: datetime
    arrive: datetime
    duration_min: int
    mode: Literal["air", "rail"] = "air"


class Slice(BaseModel):
    """One direction of a search: origin to destination on a date."""

    origin: str
    destination: str
    date: date


class Ticket(BaseModel):
    """One booking. A return or multi-city ticket covers several journeys."""

    provider: str
    price: float
    currency: str = "GBP"
    journeys: list[list[Leg]]  # one list of legs per slice searched
    booking_url: str | None = None
    self_transfer_inside: bool = False  # a self-transfer the provider already flags


class Connection(BaseModel):
    airport: str
    minutes: int
    night_minutes: int  # minutes of the connection between 00:00 and 06:00 local
    between_tickets: bool  # True = self-transfer across separate bookings
    hub_night: bool  # True = a planned overnight stay, not a wait
    nights: int = 0  # hotel nights needed for a planned stay


class Journey(BaseModel):
    """Door-to-door travel in one direction, possibly across tickets."""

    legs: list[Leg]
    connections: list[Connection]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def travel_minutes(self) -> int:
        """Flying time plus waiting time, excluding planned hub nights."""
        flying = sum(leg.duration_min for leg in self.legs)
        waiting = sum(c.minutes for c in self.connections if not c.hub_night)
        return flying + waiting

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stops(self) -> int:
        return sum(1 for c in self.connections if not c.hub_night)

    @property
    def arrival(self) -> datetime:
        return self.legs[-1].arrive

    @property
    def departure(self) -> datetime:
        return self.legs[0].depart


class Itinerary(BaseModel):
    """A complete trip: one or more tickets assembled into journeys."""

    id: str
    structure: Structure
    hub: str | None = None
    tickets: list[Ticket]
    journeys: list[Journey]
    extra_cost: float = 0.0  # hotel nights, transfers
    extra_cost_note: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fare_total(self) -> float:
        return round(sum(t.price for t in self.tickets), 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_cost(self) -> float:
        return round(self.fare_total + self.extra_cost, 2)


class Preferences(BaseModel):
    """Weights (in pounds) and hard limits. Defaults are starting guesses."""

    value_of_hour: float = Field(10.0, description="£ per hour of travel time")
    value_of_night_hour: float = Field(15.0, description="extra £ per hour waiting between 00:00 and 06:00")
    per_stop: float = Field(30.0, description="£ penalty per connection")
    short_connection_penalty: float = Field(40.0, description="£ for a connection under 60 min (90 between tickets)")
    long_connection_penalty: float = Field(40.0, description="£ for a connection over 6 h")
    self_transfer_penalty: float = Field(150.0, description="£ for a same-day self-transfer")
    stopover_bonus: float = Field(80.0, description="£ value of a planned night in a hub city")
    red_eye_arrival_penalty: float = Field(40.0, description="£ for landing between 00:00 and 06:00")
    hotel_cost_per_night: float = Field(90.0, description="£ estimate for a hub night")

    max_journey_hours: float = Field(32.0, description="drop journeys longer than this")
    max_stops: int = Field(3, description="drop journeys with more connections")
    allow_same_day_self_transfer: bool = False
    min_self_transfer_hours: float = Field(3.0, description="buffer when same-day self-transfers are allowed")
    allow_airport_overnight: bool = False


class TripRequest(BaseModel):
    """What the person asked for, after the LLM has structured it."""

    origin: str = Field(description="IATA code of home airport or city, e.g. EDI")
    destination: str = Field(description="IATA code where the trip starts, e.g. LIM")
    return_from: str | None = Field(None, description="IATA code the trip ends at, if not the destination (open-jaw), e.g. LPB")
    depart_earliest: date
    depart_latest: date
    return_earliest: date
    return_latest: date
    hubs: list[str] | None = Field(None, description="hub airports/cities to consider; default = route table")
    search_budget: int = Field(30, ge=1, le=200, description="max live searches")

    @property
    def end_airport(self) -> str:
        return self.return_from or self.destination


class ScoredItinerary(BaseModel):
    itinerary: Itinerary
    utility: float
    rank: int = 0
    vs_cheapest: float = 0.0
    breakdown: dict[str, float]
    flags: list[str]


class PruneNote(BaseModel):
    hub: str
    reason: str
    bound: float | None = None


class PlanResult(BaseModel):
    request: TripRequest
    preferences: Preferences
    ranked: list[ScoredItinerary]
    pruned: list[PruneNote]
    searches_used: int
    search_budget: int
    date_pairs: list[tuple[date, date]]
    notes: list[str] = []
