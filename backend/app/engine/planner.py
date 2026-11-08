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

import asyncio
import itertools
from datetime import date, timedelta
from typing import Any

from app.engine.hubs import HUBS, hubs_for
from app.engine.journeys import build_journey
from app.engine.utility import rank, score
from app.models import (
    Itinerary,
    Journey,
    Leg,
    PlanResult,
    Preferences,
    PruneNote,
    Slice,
    Ticket,
    TraceEvent,
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


def single_ticket_itinerary(t: Ticket, idx: int) -> Itinerary | None:
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
    structure = "stopover" if stays else "split"
    extra, note = _extras(journeys, prefs)
    return Itinerary(
        id=ident,
        structure=structure,
        hub=hub,
        tickets=tickets,
        journeys=journeys,
        extra_cost=extra,
        extra_cost_note=note,
    )


def _extras(journeys: list[Journey], prefs: Preferences) -> tuple[float, str | None]:
    """Hotel nights for planned hub stays and airport transfers, priced with these preferences."""
    nights = sum(c.nights for j in journeys for c in j.connections)
    changes = sum(1 for j in journeys for c in j.connections if "->" in c.airport)
    extra = nights * prefs.hotel_cost_per_night + changes * AIRPORT_CHANGE_COST
    note_bits = []
    if nights:
        note_bits.append(f"{nights} hotel night(s) at ~£{prefs.hotel_cost_per_night:g}")
    if changes:
        note_bits.append(f"{changes} airport transfer(s) at ~£{AIRPORT_CHANGE_COST:g}")
    return extra, ", ".join(note_bits) or None


def reprice(it: Itinerary, prefs: Preferences) -> Itinerary:
    """The same itinerary with its extras (hotel nights, transfers) priced for other preferences."""
    if it.structure == "through":
        return it
    extra, note = _extras(it.journeys, prefs)
    return it.model_copy(update={"extra_cost": extra, "extra_cost_note": note})


# A search to make: its slices, why (for the trace) and the hub it serves, if any.
Planned = tuple[list[Slice], str, str | None]


async def _run(live: BudgetedProvider, searches: list[Planned]) -> list[list[Ticket]]:
    return list(await asyncio.gather(*(live.search(s, reason=why, hub=hub) for s, why, hub in searches)))


async def _search_prefix(live: BudgetedProvider, searches: list[Planned]) -> tuple[list[list[Ticket]], bool]:
    """Run, concurrently, the leading searches a serial loop would get through before the budget ran out.

    Returns their results in order and whether the budget stopped the loop early (the serial
    version would have raised BudgetExhausted at that point).
    """
    remaining, seen, fit = live.remaining, set(), []
    for planned in searches:
        k = live.key(planned[0])
        cost = 0 if live.is_free(planned[0]) or k in seen else 1
        if cost and remaining < 1:
            return await _run(live, fit), True
        remaining -= cost
        seen.add(k)
        fit.append(planned)
    return await _run(live, fit), False


async def plan(
    req: TripRequest, prefs: Preferences, live: BudgetedProvider, cache: CachedFareProvider, top_k: int = 5
) -> PlanResult:
    """The heuristic, with independent searches run concurrently in three waves.

    Wave 1: through tickets for every sampled date pair. Wave 2: the open-jaw fix and every
    chosen hub's long-haul search (both depend only on wave 1). Wave 3: positioning around
    each long-haul. Which searches run is decided by replaying the serial loop's budget rules
    exactly, so the result is the same as searching one at a time, only faster.
    """
    notes: list[str] = []
    pruned: list[PruneNote] = []
    candidates: list[Itinerary] = []
    pairs = sample_date_pairs(req)
    open_jaw = req.end_airport != req.destination
    trace_start = len(live.trace)

    def note(**event: Any) -> None:  # planner decisions go in the same ordered log as the searches
        live.trace.append(TraceEvent(**event))

    try:
        # 2. Through tickets: the baseline. (Wave 1.)
        results, stopped = await _search_prefix(
            live,
            [
                (_through_slices(req, d, r), f"through ticket, out {d:%a %d %b}, back {r:%a %d %b}", None)
                for d, r in pairs
            ],
        )
        through_by_pair: dict[tuple[date, date], list[Ticket]] = {}
        for (d, r), tickets in zip(pairs, results, strict=False):
            through_by_pair[(d, r)] = tickets
            for t in tickets:
                it = single_ticket_itinerary(t, len(candidates))
                if it:
                    candidates.append(it)
        if stopped:
            raise live.exhausted()
        if not candidates:
            notes.append("No through tickets found for the sampled dates.")
        baseline_scored = [score(c, prefs) for c in candidates]
        baseline_u = max((s.utility for s in baseline_scored), default=-float("inf"))
        # A hub routing can't be much faster than the fastest through routing.
        fastest_hours = min((sum(j.travel_minutes for j in c.journeys) / 60 for c in candidates), default=0.0)
        best_pair = min(through_by_pair, key=lambda p: min((t.price for t in through_by_pair[p]), default=1e9))
        d, r = best_pair

        # 5. Open-jaw alternative: return to the destination, plus a one-way from the end city.
        fix_slices: list[list[Slice]] = []
        fix_searches: list[Planned] = []
        if open_jaw:
            fix_slices = [
                [Slice(origin=req.end_airport, destination=req.destination, date=r)],
                [
                    Slice(origin=req.origin, destination=req.destination, date=d),
                    Slice(origin=req.destination, destination=req.origin, date=r + timedelta(days=1)),
                ],
            ]
            fix_searches = [
                (fix_slices[0], f"open-jaw fix: one-way {req.end_airport} to {req.destination} on {r:%a %d %b}", None),
                (
                    fix_slices[1],
                    f"{req.origin}-{req.destination} return to pair with the fix, home {r + timedelta(days=1):%a %d %b}",
                    None,
                ),
            ]
        # The serial planner searched the fix before bounding hubs; if the fix doesn't fit, it stopped there.
        budget_left, seen = live.remaining, set()
        for slices in fix_slices:
            cost = 0 if live.is_free(slices) or live.key(slices) in seen else 1
            if cost and budget_left < 1:
                await _search_prefix(live, fix_searches)
                raise live.exhausted()
            budget_left -= cost
            seen.add(live.key(slices))

        # 3. Bound hubs with cached prices and prune. (Free: no budget.)
        bounded: list[tuple[float, str]] = []
        for code in hubs_for(req.destination, req.hubs):
            hub = HUBS[code]
            pos = [p for p in [await cache.lowest_price(req.origin, a, d, r) for a in hub.arrival_airports] if p]
            long = await longhaul_bound(cache, req, hub.longhaul_airport, d, r)
            if not pos or long is None:
                bounded.append((float("inf"), code))  # unknown: search last
                note(
                    kind="cache_bound", hub=code, reason="no cached price for this hub: searched last if budget allows"
                )
                continue
            # Optimistic utility: cached fares, no stops, the hub nights worth their bonus,
            # and only 80% of the fastest through routing's travel time.
            price_bound = min(pos) + long + 2 * prefs.hotel_cost_per_night
            u_bound = -price_bound + 2 * prefs.stopover_bonus - prefs.value_of_hour * 0.8 * fastest_hours
            note(
                kind="cache_bound",
                hub=code,
                bound=round(price_bound, 2),
                reason=f"cached positioning £{min(pos):.0f} + long-haul £{long:.0f} + 2 hotel nights; "
                f"best-case score {u_bound:.0f} vs {baseline_u:.0f} to beat",
            )
            if u_bound < baseline_u:
                pruned.append(
                    PruneNote(
                        hub=code,
                        bound=round(price_bound, 2),
                        reason=f"best case score {u_bound:.0f} can't beat {baseline_u:.0f} "
                        f"(cached fares + hotels ≈ £{price_bound:.0f})",
                    )
                )
                note(kind="prune", hub=code, bound=round(price_bound, 2), reason=pruned[-1].reason)
            else:
                bounded.append((-u_bound, code))
        bounded.sort()

        # The cheapest arrival airport per hub, from the cache.
        arrive: dict[str, str] = {}
        for _, code in bounded:
            hub = HUBS[code]
            arrive[code] = hub.arrival_airports[0]
            if len(hub.arrival_airports) > 1:
                prices = [(await cache.lowest_price(req.origin, a, d, r) or 1e9, a) for a in hub.arrival_airports]
                arrive[code] = min(prices)[1]

        def long_slices(code: str) -> list[Slice]:
            return [
                Slice(origin=HUBS[code].longhaul_airport, destination=req.destination, date=d),
                Slice(origin=req.end_airport, destination=HUBS[code].longhaul_airport, date=r),
            ]

        def positioning(code: str, lead: Ticket) -> list[tuple[date, list[Slice]]]:
            out_day = lead.journeys[0][0].depart.date()
            back_day = lead.journeys[1][-1].arrive.date()
            options = [(out_day - timedelta(days=1), back_day + timedelta(days=1))]  # planned nights
            if prefs.allow_same_day_self_transfer:
                options.append((out_day, back_day))
            a = arrive[code]
            return [
                (
                    po,
                    [
                        Slice(origin=req.origin, destination=a, date=po),
                        Slice(origin=a, destination=req.origin, date=pb),
                    ],
                )
                for po, pb in options
            ]

        # 4. Search surviving hubs, best bound first, replaying the serial loop's budget rules.
        # Searches that cost nothing in the serial hub loop: everything it had already done, the fix included.
        free = live.known_keys() | seen

        def replay(longs: dict[str, list[Ticket]]) -> list[tuple]:
            """The serial hub loop's decisions, given the long-haul results known so far.

            An unknown long-haul is assumed to return fares and its positioning to cost a search each.
            """
            remaining, spent = budget_left, set(seen)
            steps: list[tuple] = []
            for bound, code in bounded:
                if remaining < 2:
                    steps.append(("skip", code, bound))
                    continue
                k = live.key(long_slices(code))
                remaining -= 0 if k in free or k in spent else 1
                spent.add(k)
                if code not in longs:
                    n = 2 if prefs.allow_same_day_self_transfer else 1
                    remaining -= min(n, max(remaining, 0))
                    steps.append(("unknown", code))
                    continue
                if not longs[code]:
                    steps.append(("no-long", code))
                    continue
                chosen = []
                for po, slices in positioning(code, longs[code][0]):
                    if remaining < 1:
                        break
                    k = live.key(slices)
                    remaining -= 0 if k in free or k in spent else 1
                    spent.add(k)
                    chosen.append((po, slices))
                steps.append(("hub", code, chosen))
            return steps

        # Wave 2: the fix and the long-hauls together; repeat only if an empty long-haul freed budget.
        longs: dict[str, list[Ticket]] = {}
        fix_results: list[list[Ticket]] | None = None
        while True:
            need = [s[1] for s in replay(longs) if s[0] == "unknown"]
            batch = (fix_searches if fix_results is None else []) + [
                (
                    long_slices(c),
                    f"long-haul {HUBS[c].longhaul_airport}-{req.destination}, back from {req.end_airport}",
                    c,
                )
                for c in need
            ]
            if not batch:
                break
            got = await _run(live, batch)
            if fix_results is None:
                fix_results, got = got[: len(fix_slices)], got[len(fix_slices) :]
            longs.update(zip(need, got, strict=True))
            if not need:
                break
        steps = replay(longs)

        if open_jaw and fix_results:
            back, ret = fix_results
            for (i, b), (k, t) in itertools.product(enumerate(back[:2]), enumerate(ret[:3])):
                it = assemble([t, b], [(0, 0)], [(1, 0), (0, 1)], req.destination, prefs, f"fix-{i}-{k}")
                if it:
                    candidates.append(it)

        for step in steps:  # the hub loop's pruning decisions, now final
            if step[0] == "skip":
                note(kind="prune", hub=step[1], reason="search budget used up")
            elif step[0] == "no-long":
                note(kind="prune", hub=step[1], reason="no long-haul fares found")

        # Wave 3: every positioning search at once.
        wanted: list[Planned] = [
            (
                slices,
                f"positioning {req.origin}-{slices[0].destination}, out {slices[0].date:%a %d %b}, "
                f"back {slices[1].date:%a %d %b}"
                + (" (a night in the hub each way)" if pos_out < d else " (same-day connections)"),
                s[1],
            )
            for s in steps
            if s[0] == "hub"
            for pos_out, slices in s[2]
        ]
        pos_results = dict(zip((live.key(w[0]) for w in wanted), await _run(live, wanted), strict=True))

        for step in steps:
            if step[0] == "skip":
                _, code, bound = step
                pruned.append(
                    PruneNote(hub=code, reason="search budget used up", bound=None if bound == float("inf") else bound)
                )
            elif step[0] == "no-long":
                pruned.append(PruneNote(hub=step[1], reason="no long-haul fares found"))
            else:
                _, code, chosen = step
                for pos_out, slices in chosen:
                    pos = pos_results[live.key(slices)]
                    for (i, lt), (k, pt) in itertools.product(enumerate(longs[code][:3]), enumerate(pos[:2])):
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
        trace=live.trace[trace_start:],
        candidates=candidates,
    )
