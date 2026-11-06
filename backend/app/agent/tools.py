"""Tools the LLM can call. The LLM structures the request and explains the
result; all prices, scores and rankings come from here."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.engine.planner import plan
from app.models import PlanResult, Preferences, Slice, TripRequest
from app.providers.factory import budgeted, cache_provider

# Per-chat preferences, in memory. Fine for a single-user personal tool.
PREFERENCES: dict[str, Preferences] = {}


class SearchRouteInput(BaseModel):
    origin: str = Field(description="IATA code")
    destination: str = Field(description="IATA code")
    date: date
    return_date: date | None = None


class PlanTripInput(TripRequest):
    pass


def _schema(model: type[BaseModel]) -> dict:
    s = model.model_json_schema()
    s.pop("title", None)
    return s


TOOL_DEFS = [
    {
        "name": "plan_trip",
        "description": (
            "Search hubs, flexible dates and ticket structures (through tickets, split tickets with a planned "
            "night in a hub, open-jaw) and return itineraries ranked by the user's preferences. Use for any "
            "trip-planning request once origin, destination and date windows are known. Dates are windows: "
            "earliest/latest departure and earliest/latest return."
        ),
        "input_schema": _schema(PlanTripInput),
    },
    {
        "name": "search_route",
        "description": "Look up live fares for one route and date (optionally a return). Use for quick follow-up questions.",
        "input_schema": _schema(SearchRouteInput),
    },
    {
        "name": "set_preferences",
        "description": (
            "Update how itineraries are scored for this chat. Values are in GBP. Only include fields the user "
            "expressed a view on. Call before plan_trip when the user states a trade-off, e.g. 'I'd pay £150 "
            "to avoid an overnight connection'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {k: v for k, v in Preferences.model_json_schema()["properties"].items()},
        },
    },
]


def preferences_for(chat_id: str) -> Preferences:
    return PREFERENCES.setdefault(chat_id, Preferences())


def _journey_view(j) -> dict:  # noqa: ANN001
    return {
        "route": " > ".join([j.legs[0].origin] + [leg.destination for leg in j.legs]),
        "carriers": sorted({leg.carrier for leg in j.legs}),
        "depart": j.legs[0].depart.isoformat(timespec="minutes"),
        "arrive": j.legs[-1].arrive.isoformat(timespec="minutes"),
        "travel_hours": round(j.travel_minutes / 60, 1),
        "stops": j.stops,
        "stays": [f"{c.nights} night(s) at {c.airport}" for c in j.connections if c.hub_night],
    }


def plan_model_view(result: PlanResult) -> dict:
    """Compact facts for the LLM to explain. It must not invent other numbers."""
    return {
        "ranked": [
            {
                "rank": s.rank,
                "structure": s.itinerary.structure,
                "hub": s.itinerary.hub,
                "total_cost_gbp": s.itinerary.total_cost,
                "fares_gbp": s.itinerary.fare_total,
                "extra_costs_gbp": s.itinerary.extra_cost,
                "extra_costs_note": s.itinerary.extra_cost_note,
                "vs_cheapest_shown_gbp": s.vs_cheapest,
                "score": s.utility,
                "score_breakdown_gbp": s.breakdown,
                "tickets": len(s.itinerary.tickets),
                "journeys": [_journey_view(j) for j in s.itinerary.journeys],
                "flags": s.flags,
            }
            for s in result.ranked
        ],
        "pruned_hubs": [p.model_dump() for p in result.pruned],
        "searches_used": f"{result.searches_used}/{result.search_budget}",
        "date_pairs_searched": [f"{d} -> {r}" for d, r in result.date_pairs],
        "notes": result.notes,
    }


async def run_tool(name: str, args: dict[str, Any], chat_id: str, settings: Settings) -> dict[str, Any]:
    """Returns {"ui": <shown to the user>, "model": <JSON string for the LLM>}."""
    try:
        if name == "plan_trip":
            req = PlanTripInput.model_validate(args)
            prefs = preferences_for(chat_id)
            result = await plan(req, prefs, budgeted(settings, req.search_budget), cache_provider(settings))
            view = plan_model_view(result)
            return {"ui": {"kind": "plan", "result": result.model_dump(mode="json")}, "model": json.dumps(view)}
        if name == "search_route":
            inp = SearchRouteInput.model_validate(args)
            slices = [Slice(origin=inp.origin, destination=inp.destination, date=inp.date)]
            if inp.return_date:
                slices.append(Slice(origin=inp.destination, destination=inp.origin, date=inp.return_date))
            provider = budgeted(settings, 1)
            tickets = await provider.search(slices)
            view = [
                {"price_gbp": t.price, "journeys": [
                    {"route": " > ".join([j[0].origin] + [leg.destination for leg in j]),
                     "carriers": sorted({leg.carrier for leg in j}),
                     "depart": j[0].depart.isoformat(timespec="minutes"),
                     "arrive": j[-1].arrive.isoformat(timespec="minutes")} for j in t.journeys]}
                for t in tickets
            ]
            return {"ui": {"kind": "route", "tickets": view}, "model": json.dumps(view)}
        if name == "set_preferences":
            current = preferences_for(chat_id)
            updated = current.model_copy(update=Preferences.model_validate(current.model_dump() | args).model_dump())
            PREFERENCES[chat_id] = updated
            changed = {k: v for k, v in updated.model_dump().items() if current.model_dump()[k] != v}
            return {"ui": {"kind": "preferences", "changed": changed, "preferences": updated.model_dump()},
                    "model": json.dumps({"updated": changed})}
        return {"ui": {"kind": "error", "message": f"unknown tool {name}"}, "model": f"Unknown tool {name}"}
    except ValidationError as e:
        msg = f"Invalid arguments: {e.errors(include_url=False)}"
        return {"ui": {"kind": "error", "message": msg}, "model": msg}
