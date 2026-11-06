"""Cached lowest fares from the Travelpayouts / Aviasales Data API.

Prices come from other users' searches over the last 2-7 days, so they are a
cheap, stale prior: good for bounding and pruning, never shown as a price.
"""

from __future__ import annotations

from datetime import date

import httpx

URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


class TravelpayoutsCache:
    name = "travelpayouts"

    def __init__(self, token: str, currency: str = "gbp", timeout: float = 15.0):
        self.token = token
        self.currency = currency.lower()
        self.timeout = timeout
        self._memo: dict[tuple, float | None] = {}

    async def lowest_price(
        self, origin: str, destination: str, depart: date, return_date: date | None = None
    ) -> float | None:
        # Month granularity gives far better cache coverage than exact dates.
        key = (origin, destination, depart.strftime("%Y-%m"), return_date.strftime("%Y-%m") if return_date else None)
        if key in self._memo:
            return self._memo[key]
        params = {
            "origin": origin,
            "destination": destination,
            "departure_at": key[2],
            "currency": self.currency,
            "sorting": "price",
            "limit": 1,
            "token": self.token,
            "one_way": "false" if return_date else "true",
        }
        if return_date:
            params["return_at"] = key[3]
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(URL, params=params)
                resp.raise_for_status()
                data = resp.json().get("data") or []
                price = float(data[0]["price"]) if data else None
        except (httpx.HTTPError, KeyError, ValueError):
            price = None
        self._memo[key] = price
        return price
