"""Heuristic planner (spec milestone 1).

1. Sample a few date pairs from the flexible window.
2. Search through tickets: the baseline every other option must beat.
3. Bound each hub with free cached prices; prune hubs that can't win.
4. For surviving hubs, search the long-haul leg then positioning around it,
   preferring a planned night in the hub over a same-day self-transfer.
5. For open-jaw trips, also try "return to the destination + a one-way back".
6. Score, apply hard limits, keep the Pareto front, rank.

Every live search goes through BudgetedProvider. The spec's later milestones
replace step 3 with a fare model that chooses searches by value of
information; this module is the baseline that model has to beat.
"""

from __future__ import annotations

import itertools
from datetime import date, timedelta

from app.engine.hubs import HUBS, hubs_for
from app.engine.journeys import build_journey
from app.engine.utility import rank, score
from app.models import (
    Itinerary,
    Leg,
    PlanResult,
    Preferences,
    PruneNote,
    Slice,
    Ticket,
    TripRequest,
)
from app.providers.base import BudgetedProvider, BudgetExhausted, CachedFareProvider

AIRPORT_CHANGE_COST = 20.0  # e.g. Stansted -> Heathrow by coach
# A multi-city ticket (hub -> destination, end city -> hub) prices like a return: about 0.8 x two one-ways.
MULTI_CITY_DISCOUNT = 0.8


async def longhaul_bound(
    cache: CachedFareProvider, req: TripRequest, hub_airport: str, d: date, r: date
) -> float | None:
    """Cached best case for the hub's long-haul ticket, or None when the cache can't price it.

    On an open-jaw the cache only has one-ways for each direction, but the live search books both on one
    multi-city ticket, so the sum gets the same discount the ticket would.
    """
    if req.end_airport == req.destination:
        return await cache.lowest_price(hub_airport, req.destination, d, r)
    a = await cache.lowest_price(hub_airport, req.destination, d)
    b = await cache.lowest_price(req.end_airport, hub_airport, r)
    return MULTI_CITY_DISCOUNT * (a + b) if a and b else None


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def sample_date_pairs(req: TripRequest, limit: int = 3) -> list[tuple[date, date]]:
    """Ends and middle of the window, keeping trip length roughly constant."""
    deps, rets = _days(req.depart_earliest, req.depart_latest), _days(req.return_earliest, req.return_latest)
    if len(deps) * len(rets) <= limit:
        return [(d, r) for d, r in itertools.product(deps, rets) if r > d]
    picks = []
    for frac in (0.0, 0.5, 1.0)[:limit]:
        d = deps[round(frac * (len(deps) - 1))]
        r = rets[round(frac * (len(rets) - 1))]
        if r > d and (d, r) not in picks:
            picks.append((d, r))
    return picks


def _through_slices(req: TripRequest, d: date, r: date) -> list[Slice]:
    return [
        Slice(origin=req.origin, destination=req.destination, date=d),
        Slice(origin=req.end_airport, destination=req.origin, date=r),
    ]


def _single_ticket_itinerary(t: Ticket, idx: int) -> Itinerary | None:
    journeys = []
    for legs in t.journeys:
        j = build_journey(legs, [0] * len(legs))
        if j is None:
            return None
        journeys.append(j)
    return Itinerary(id=f"through-{idx}", structure="through", tickets=[t], journeys=journeys)


def assemble(
    tickets: list[Ticket],
    out_parts: list[tuple[int, int]],
    ret_parts: list[tuple[int, int]],
    hub: str | None,
    prefs: Preferences,
    ident: str,
) -> Itinerary | None:
    """Join journeys from several tickets. parts = [(ticket index, journey index), ...] in travel order."""
    journeys = []
    for parts in (out_parts, ret_parts):
        legs: list[Leg] = []
        owner: list[int] = []
        for ti, ji in parts:
            legs.extend(tickets[ti].journeys[ji])
            owner.extend([ti] * len(tickets[ti].journeys[ji]))
        j = build_journey(legs, owner)
        if j is None:
            return None
        journeys.append(j)
    stays = sum(1 for j in journeys for c in j.connections if c.hub_night)
    nights = sum(c.nights for j in journeys for c in j.connections)
    changes = sum(1 for j in journeys for c in j.connections if "->" in c.airport)
    structure = "stopover" if stays else "split"
    extra = nights * prefs.hotel_cost_per_night + changes * AIRPORT_CHANGE_COST
    note_bits = []
    if nights:
        note_bits.append(f"{nights} hotel night(s) at ~£{prefs.hotel_cost_per_night:g}")
    if changes:
        note_bits.append(f"{changes} airport transfer(s) at ~£{AIRPORT_CHANGE_COST:g}")
    return Itinerary(
        id=ident,
        structure=structure,
        hub=hub,
        tickets=tickets,
        journeys=journeys,
        extra_cost=extra,
        extra_cost_note=", ".join(note_bits) or None,
    )


async def plan(
    req: TripRequest, prefs: Preferences, live: BudgetedProvider, cache: CachedFareProvider, top_k: int = 5
) -> PlanResult:
    notes: list[str] = []
    pruned: list[PruneNote] = []
    candidates: list[Itinerary] = []
    pairs = sample_date_pairs(req)
    open_jaw = req.end_airport != req.destination

    try:
        # 2. Through tickets: the baseline.
        through_by_pair: dict[tuple[date, date], list[Ticket]] = {}
        for d, r in pairs:
            tickets = await live.search(_through_slices(req, d, r))
            through_by_pair[(d, r)] = tickets
            for t in tickets:
                it = _single_ticket_itinerary(t, len(candidates))
                if it:
                    candidates.append(it)
        if not candidates:
            notes.append("No through tickets found for the sampled dates.")
        baseline_scored = [score(c, prefs) for c in candidates]
        baseline_u = max((s.utility for s in baseline_scored), default=-float("inf"))
        # A hub routing can't be much faster than the fastest through routing.
        fastest_hours = min((sum(j.travel_minutes for j in c.journeys) / 60 for c in candidates), default=0.0)
        best_pair = min(through_by_pair, key=lambda p: min((t.price for t in through_by_pair[p]), default=1e9))

        # 5. Open-jaw alternative: return to the destination, plus a one-way from the end city.
        if open_jaw:
            d, r = best_pair
            back = await live.search([Slice(origin=req.end_airport, destination=req.destination, date=r)])
            ret = await live.search(
                [
                    Slice(origin=req.origin, destination=req.destination, date=d),
                    Slice(origin=req.destination, destination=req.origin, date=r + timedelta(days=1)),
                ]
            )
            for (i, b), (k, t) in itertools.product(enumerate(back[:2]), enumerate(ret[:3])):
                it = assemble([t, b], [(0, 0)], [(1, 0), (0, 1)], req.destination, prefs, f"fix-{i}-{k}")
                if it:
                    candidates.append(it)

        # 3. Bound hubs with cached prices and prune.
        d, r = best_pair
        bounded: list[tuple[float, str]] = []
        for code in hubs_for(req.destination, req.hubs):
            hub = HUBS[code]
            pos = [p for p in [await cache.lowest_price(req.origin, a, d, r) for a in hub.arrival_airports] if p]
            long = await longhaul_bound(cache, req, hub.longhaul_airport, d, r)
            if not pos or long is None:
                bounded.append((float("inf"), code))  # unknown: search last
                continue
            # Optimistic utility: cached fares, no stops, the hub nights worth their bonus,
            # and only 80% of the fastest through routing's travel time.
            price_bound = min(pos) + long + 2 * prefs.hotel_cost_per_night
            u_bound = -price_bound + 2 * prefs.stopover_bonus - prefs.value_of_hour * 0.8 * fastest_hours
            if u_bound < baseline_u:
                pruned.append(
                    PruneNote(
                        hub=code,
                        bound=round(price_bound, 2),
                        reason=f"best case score {u_bound:.0f} can't beat {baseline_u:.0f} "
                        f"(cached fares + hotels ≈ £{price_bound:.0f})",
                    )
                )
            else:
                bounded.append((-u_bound, code))
        bounded.sort()

        # 4. Search surviving hubs, best bound first.
        for bound, code in bounded:
            if live.remaining < 2:
                pruned.append(
                    PruneNote(hub=code, reason="search budget used up", bound=None if bound == float("inf") else bound)
                )
                continue
            hub = HUBS[code]
            long_slices = [
                Slice(origin=hub.longhaul_airport, destination=req.destination, date=d),
                Slice(origin=req.end_airport, destination=hub.longhaul_airport, date=r),
            ]
            longs = await live.search(long_slices)
            if not longs:
                pruned.append(PruneNote(hub=code, reason="no long-haul fares found"))
                continue
            lead = longs[0]
            out_day = lead.journeys[0][0].depart.date()
            back_day = lead.journeys[1][-1].arrive.date()
            arrive_airport = hub.arrival_airports[0]
            if len(hub.arrival_airports) > 1:  # pick the cheapest arrival airport from the cache
                prices = [(await cache.lowest_price(req.origin, a, d, r) or 1e9, a) for a in hub.arrival_airports]
                arrive_airport = min(prices)[1]
            options = [(out_day - timedelta(days=1), back_day + timedelta(days=1))]  # planned nights
            if prefs.allow_same_day_self_transfer:
                options.append((out_day, back_day))
            for pos_out, pos_back in options:
                if live.remaining < 1:
                    break
                pos = await live.search(
                    [
                        Slice(origin=req.origin, destination=arrive_airport, date=pos_out),
                        Slice(origin=arrive_airport, destination=req.origin, date=pos_back),
                    ]
                )
                for (i, lt), (k, pt) in itertools.product(enumerate(longs[:3]), enumerate(pos[:2])):
                    it = assemble(
                        [pt, lt],
                        [(0, 0), (1, 0)],
                        [(1, 1), (0, 1)],
                        code,
                        prefs,
                        f"{code.lower()}-{pos_out:%m%d}-{i}-{k}",
                    )
                    if it:
                        candidates.append(it)
    except BudgetExhausted as e:
        notes.append(str(e))

    scored = [score(c, prefs) for c in candidates]
    ranked = rank(scored, prefs, top_k=top_k)
    return PlanResult(
        request=req,
        preferences=prefs,
        ranked=ranked,
        pruned=pruned,
        searches_used=live.used,
        search_budget=live.budget,
        date_pairs=pairs,
        notes=notes,
    )
