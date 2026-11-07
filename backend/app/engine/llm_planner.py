"""The `llm` baseline planner: an LLM chooses the searches, code builds and scores the itineraries.

This is the planner the project's claim is measured against, so it gets the strongest setup:
- the strongest reasoning model (role "baseline"), with its reasoning kept across turns;
- the same knowledge the code planners have: the trip, the hubs and their airports, the ticket
  structures that count, the person's preferences, and the budget;
- the same tools: a raw live search (any one-way, return, open-jaw or multi-city ticket) that
  spends budget through the same BudgetedProvider (repeats free), and the same free, stale
  fare cache; plus a free view of the best itineraries its searches allow so far;
- parallel tool calls, run concurrently.

When it stops, every itinerary in the candidate space (app/engine/space.py) that can be built
from the tickets it bought is scored with the same utility as every other planner. So the LLM
never produces a price or a score, and its regret is exact.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json

from pydantic import BaseModel, Field, ValidationError

from app.engine.hubs import HUBS, hubs_for
from app.engine.space import candidates
from app.engine.utility import rank, score
from app.llm.base import LLM, TurnResult
from app.models import PlanResult, Preferences, Slice, Ticket, TripRequest
from app.providers.base import BudgetedProvider, BudgetExhausted, CachedFareProvider

MAX_CACHE_LOOKUPS = 300
RESULTS_PER_SEARCH = 5  # what a live search returns, as for the heuristic


class SearchRouteArgs(BaseModel):
    origin: str = Field(description="IATA code the ticket starts from")
    destination: str = Field(description="IATA code of the first slice's destination")
    date: dt.date = Field(description="departure date of the first slice")
    return_date: dt.date | None = Field(None, description="date of the second slice; omit for a one-way")
    return_origin: str | None = Field(None, description="where the second slice starts (default: destination)")
    return_destination: str | None = Field(None, description="where the second slice ends (default: origin)")

    def slices(self) -> list[Slice]:
        out = [Slice(origin=self.origin.upper(), destination=self.destination.upper(), date=self.date)]
        if self.return_date:
            out.append(
                Slice(
                    origin=(self.return_origin or self.destination).upper(),
                    destination=(self.return_destination or self.origin).upper(),
                    date=self.return_date,
                )
            )
        return out


class CachedPriceArgs(BaseModel):
    origin: str
    destination: str
    date: dt.date
    return_date: dt.date | None = Field(None, description="for a return fare on the same route")


def _schema(model: type[BaseModel]) -> dict:
    s = model.model_json_schema()
    s.pop("title", None)
    return s


TOOLS = [
    {
        "name": "search_route",
        "description": (
            "Live fares for one booking: one slice (one-way) or two slices (return, open-jaw or multi-city) on "
            "one ticket. Costs one search from the budget; repeating an identical search is free. Returns up to "
            f"{RESULTS_PER_SEARCH} tickets, cheapest first, with legs (local times) and prices in GBP."
        ),
        "input_schema": _schema(SearchRouteArgs),
    },
    {
        "name": "cached_price",
        "description": (
            "Free: the lowest recently cached price for a one-way or a same-route return. Stale and usually "
            "optimistic (it keeps the lowest of several old observations); null when the cache has nothing."
        ),
        "input_schema": _schema(CachedPriceArgs),
    },
    {
        "name": "best_so_far",
        "description": (
            "Free: the best complete itineraries that can be built from the tickets you have searched so far, "
            "scored with the person's preferences (utility in GBP, higher is better)."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

SYSTEM = """You plan the live fare searches for one trip. Each live search costs one unit of a fixed budget; the
cache and best_so_far are free. When you stop, every complete itinerary that can be built from the tickets you
searched is scored with the person's preferences and the best one is the result. Your goal: the highest-utility
itinerary you can find within the budget. Stop (reply without tool calls) when more searches are unlikely to help
or the budget is spent. You can call several tools at once; they run in parallel."""


def _task(req: TripRequest, prefs: Preferences, budget: int) -> str:
    hubs = [HUBS[c] for c in hubs_for(req.destination, req.hubs)]
    hub_lines = "\n".join(
        f"- {h.city}: long-haul from {h.longhaul_airport}; positioning flights from {req.origin} arrive at "
        f"{', '.join(h.arrival_airports)}"
        for h in hubs
    )
    end = req.end_airport
    open_jaw = end != req.destination
    trip_line = (
        f"Fly {req.origin} -> {req.destination}, leaving between {req.depart_earliest} and {req.depart_latest}; "
        f"come home {end} -> {req.origin}, between {req.return_earliest} and {req.return_latest}."
    )
    fix = (
        f"\n3. {end} fix (open-jaw only): a one-way {end} -> {req.destination} on the return date, plus a "
        f"{req.origin} <-> {req.destination} return coming home that day or the next."
        if open_jaw
        else ""
    )
    hub_long = f"one ticket {{hub}} -> {req.destination} out and {end} -> {{hub}} back" + (
        f", or a {{hub}} <-> {req.destination} return plus the fix above" if open_jaw else ""
    )
    return f"""Trip: {trip_line}
Search budget: {budget} live searches.

Itineraries that count (anything else you search can't be used):
1. Through ticket: one booking {req.origin} -> {req.destination} out and {end} -> {req.origin} back.
2. Hub: a positioning return {req.origin} <-> an arrival airport of the hub, plus the long-haul as {hub_long}.
   Positioning flies out on the long-haul's departure day or the day before (a planned night in the hub), and back
   on the day the long-haul lands or the day after.{fix}

Hubs:
{hub_lines}

How itineraries are scored (GBP, higher is better): utility = -(fares + extras) - value_of_hour x travel hours
- value_of_night_hour x hours waiting between 00:00 and 06:00 - penalties + bonuses. Extras are hotel nights for
planned hub stays and airport transfers (e.g. Stansted to Heathrow). Hard limits remove an itinerary entirely.
Preferences: {prefs.model_dump_json()}"""


def _ticket_view(t: Ticket) -> dict:
    return {
        "price_gbp": t.price,
        "journeys": [
            {
                "legs": [
                    [leg.carrier, leg.origin, leg.destination, leg.depart.isoformat(), leg.arrive.isoformat()]
                    for leg in legs
                ],
                "flying_hours": round(sum(leg.duration_min for leg in legs) / 60, 2),
            }
            for legs in t.journeys
        ],
    }


class _SearchedOnly:
    """A provider that answers only with searches already made: assembling costs no budget."""

    def __init__(self, live: BudgetedProvider):
        self.live, self.name = live, live.name

    async def search(self, slices: list[Slice], max_results: int = 5) -> list[Ticket]:
        return self.live.memoised(slices) or []


async def _ranked(req: TripRequest, prefs: Preferences, live: BudgetedProvider, top_k: int):
    built = await candidates(_SearchedOnly(live), req, prefs)
    return rank([score(it, prefs) for it in built], prefs, top_k=top_k)


async def llm_plan(
    req: TripRequest,
    prefs: Preferences,
    live: BudgetedProvider,
    cache: CachedFareProvider,
    llm: LLM,
    top_k: int = 5,
    max_turns: int | None = None,
) -> PlanResult:
    max_turns = max_turns or 3 * live.budget + 10
    messages: list[dict] = [{"role": "user", "content": [{"type": "text", "text": _task(req, prefs, live.budget)}]}]
    usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "turns": 0}
    notes: list[str] = []
    cache_lookups = 0

    async def run_tool(block: dict) -> str:
        nonlocal cache_lookups
        name, args = block.get("name"), block.get("input") or {}
        try:
            if name == "search_route":
                a = SearchRouteArgs.model_validate(args)
                try:
                    tickets = await live.search(a.slices(), max_results=RESULTS_PER_SEARCH)
                except BudgetExhausted:
                    return json.dumps({"error": "search budget used up", "remaining_budget": 0})
                return json.dumps({"remaining_budget": live.remaining, "tickets": [_ticket_view(t) for t in tickets]})
            if name == "cached_price":
                cache_lookups += 1
                if cache_lookups > MAX_CACHE_LOOKUPS:
                    return json.dumps({"error": f"cache lookup limit of {MAX_CACHE_LOOKUPS} reached"})
                a = CachedPriceArgs.model_validate(args)
                price = await cache.lowest_price(a.origin.upper(), a.destination.upper(), a.date, a.return_date)
                return json.dumps({"cached_lowest_gbp": price})
            if name == "best_so_far":
                best = await _ranked(req, prefs, live, 3)
                return json.dumps(
                    {
                        "remaining_budget": live.remaining,
                        "best": [
                            {
                                "utility": s.utility,
                                "structure": s.itinerary.structure,
                                "hub": s.itinerary.hub,
                                "total_cost_gbp": s.itinerary.total_cost,
                                "travel_hours": [round(j.travel_minutes / 60, 2) for j in s.itinerary.journeys],
                                "flags": s.flags,
                            }
                            for s in best
                        ],
                    }
                )
            return json.dumps({"error": f"unknown tool {name!r}"})
        except ValidationError as e:
            return json.dumps({"error": f"bad arguments: {e.errors(include_url=False)}"})

    for _ in range(max_turns):
        result: TurnResult | None = None
        async for item in llm.stream_turn(SYSTEM, TOOLS, messages):
            if isinstance(item, TurnResult):
                result = item
        if result is None:
            notes.append("the LLM returned no turn")
            break
        usage["turns"] += 1
        for k in ("input_tokens", "cached_tokens", "output_tokens"):
            usage[k] += int((result.usage or {}).get(k, 0))
        messages.append({"role": "assistant", "content": result.content})
        calls = [b for b in result.content if b.get("type") == "tool_use"]
        if result.stop_reason != "tool_use" or not calls:
            break
        outputs = await asyncio.gather(*(run_tool(b) for b in calls))
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": b["id"], "content": out}
                    for b, out in zip(calls, outputs, strict=True)
                ],
            }
        )
    else:
        notes.append(f"stopped after {max_turns} LLM turns")

    return PlanResult(
        request=req,
        preferences=prefs,
        ranked=await _ranked(req, prefs, live, top_k),
        pruned=[],
        searches_used=live.used,
        search_budget=live.budget,
        date_pairs=[],
        notes=notes,
        llm_usage=usage,
    )
