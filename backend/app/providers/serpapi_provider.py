"""Live fares from SerpApi's Google Flights engine (free tier: 250 searches/month).

Round-trip and multi-city results only describe the first slice; the later
slices come from follow-up calls with `departure_token`. Each follow-up is a
SerpApi search too, so this provider expands only the cheapest few options.
"""

from __future__ import annotations

import json
from datetime import datetime

import httpx

from app.models import Leg, Slice, Ticket

SERPAPI_URL = "https://serpapi.com/search.json"


class SerpApiProvider:
    name = "serpapi"

    def __init__(self, api_key: str, currency: str = "GBP", expand_top: int = 2, timeout: float = 30.0):
        self.api_key = api_key
        self.currency = currency
        self.expand_top = expand_top
        self.timeout = timeout

    def _base_params(self, slices: list[Slice]) -> dict:
        params: dict = {
            "engine": "google_flights",
            "api_key": self.api_key,
            "currency": self.currency,
            "hl": "en",
            "gl": "uk",
        }
        is_return = (
            len(slices) == 2
            and slices[0].origin == slices[1].destination
            and slices[0].destination == slices[1].origin
        )
        if len(slices) == 1:
            params |= {"type": 2, "departure_id": slices[0].origin, "arrival_id": slices[0].destination,
                       "outbound_date": slices[0].date.isoformat()}
        elif is_return:
            params |= {"type": 1, "departure_id": slices[0].origin, "arrival_id": slices[0].destination,
                       "outbound_date": slices[0].date.isoformat(), "return_date": slices[1].date.isoformat()}
        else:
            params |= {"type": 3, "multi_city_json": json.dumps(
                [{"departure_id": s.origin, "arrival_id": s.destination, "date": s.date.isoformat()} for s in slices]
            )}
        return params

    async def search(self, slices: list[Slice], max_results: int = 5) -> list[Ticket]:
        params = self._base_params(slices)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            first = await self._get(client, params)
            options = sorted(_options(first), key=lambda o: o.get("price") or 1e9)[:max_results]
            tickets: list[Ticket] = []
            for i, opt in enumerate(options):
                journeys = [[_leg(f) for f in opt.get("flights", [])]]
                token = opt.get("departure_token")
                price = opt.get("price")
                # Fill later slices for the cheapest few options only.
                while len(journeys) < len(slices) and token and i < self.expand_top:
                    nxt = await self._get(client, params | {"departure_token": token})
                    nxt_opts = sorted(_options(nxt), key=lambda o: o.get("price") or 1e9)
                    if not nxt_opts:
                        break
                    journeys.append([_leg(f) for f in nxt_opts[0].get("flights", [])])
                    price = nxt_opts[0].get("price", price)
                    token = nxt_opts[0].get("departure_token")
                if len(journeys) < len(slices) or not price:
                    continue
                tickets.append(Ticket(provider=self.name, price=float(price), currency=self.currency,
                                      journeys=journeys))
            return tickets

    async def _get(self, client: httpx.AsyncClient, params: dict) -> dict:
        resp = await client.get(SERPAPI_URL, params=params)
        resp.raise_for_status()
        return resp.json()


def _options(payload: dict) -> list[dict]:
    return list(payload.get("best_flights", [])) + list(payload.get("other_flights", []))


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def _leg(f: dict) -> Leg:
    return Leg(
        carrier=f.get("airline", "?"),
        flight_number=f.get("flight_number"),
        origin=f["departure_airport"]["id"],
        destination=f["arrival_airport"]["id"],
        depart=_parse_time(f["departure_airport"]["time"]),
        arrive=_parse_time(f["arrival_airport"]["time"]),
        duration_min=int(f.get("duration", 0)) or 1,
    )
