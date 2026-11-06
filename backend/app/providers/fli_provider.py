"""Live fares from Google Flights via the unofficial `fli` library.

Prototype only: this talks to Google Flights' internal endpoints, which is
against Google's terms. Use SerpApi for anything you'd share.
"""

from __future__ import annotations

import asyncio

from app.models import Leg, Slice, Ticket


class FliProvider:
    name = "fli"

    def __init__(self, currency: str = "GBP"):
        self.currency = currency

    async def search(self, slices: list[Slice], max_results: int = 5) -> list[Ticket]:
        return await asyncio.to_thread(self._search_sync, slices, max_results)

    def _search_sync(self, slices: list[Slice], max_results: int) -> list[Ticket]:
        from fli.models import (
            Airport,
            FlightSearchFilters,
            FlightSegment,
            PassengerInfo,
        )
        from fli.models.google_flights.base import SortBy, TripType
        from fli.search import SearchFlights

        is_return = (
            len(slices) == 2 and slices[0].origin == slices[1].destination and slices[0].destination == slices[1].origin
        )
        trip_type = TripType.ONE_WAY if len(slices) == 1 else TripType.ROUND_TRIP if is_return else TripType.MULTI_CITY
        filters = FlightSearchFilters(
            trip_type=trip_type,
            passenger_info=PassengerInfo(adults=1),
            flight_segments=[
                FlightSegment(
                    departure_airport=[[Airport[s.origin], 0]],
                    arrival_airport=[[Airport[s.destination], 0]],
                    travel_date=s.date.isoformat(),
                )
                for s in slices
            ],
            sort_by=SortBy.BEST,
        )
        results = SearchFlights().search(filters, top_n=max_results, currency=self.currency) or []
        tickets: list[Ticket] = []
        for r in results[: max_results * 3]:
            parts = r if isinstance(r, tuple) else (r,)
            price = next((p.price for p in reversed(parts) if p.price), None)
            if not price:
                continue
            tickets.append(
                Ticket(
                    provider=self.name,
                    price=float(price),
                    currency=self.currency,
                    journeys=[[_leg(leg) for leg in p.legs] for p in parts],
                    self_transfer_inside=any(bool(p.self_transfer) for p in parts),
                )
            )
        tickets.sort(key=lambda t: t.price)
        return tickets[:max_results]


def _leg(leg) -> Leg:  # noqa: ANN001
    return Leg(
        carrier=getattr(leg.airline, "value", str(leg.airline)),
        flight_number=leg.flight_number,
        origin=leg.departure_airport.name,
        destination=leg.arrival_airport.name,
        depart=leg.departure_datetime,
        arrive=leg.arrival_datetime,
        duration_min=leg.duration,
    )
