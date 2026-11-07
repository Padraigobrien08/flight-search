"""The candidate space: every itinerary that can be built for a trip from a set of searches.

Shared by the exhaustive optimum (app/sim/exhaustive.py, which searches all of it with no
budget) and the `llm` planner (which assembles it from only the searches it chose), so
regret stays exact: nothing a planner can build lies outside it. It contains
everything the heuristic `plan()` can build, and more:

- every date pair in the window (return after departure);
- through tickets: origin -> destination out, end city -> origin back, one booking;
- the La Paz fix (open-jaw only): end city -> destination one-way on the return date,
  plus an origin <-> destination return coming home that day or the next;
- every hub and every arrival airport, with the long-haul either as one ticket from the
  end city (hub -> destination, end -> hub) or, on an open-jaw, as a hub return plus the fix;
- positioning out on the long-haul's departure day or the day before, and back on the day
  the long-haul lands or the day after (0 or 1 planned nights each way).

A planner that builds candidates outside this space (more hub nights, other hubs)
must extend it first, or its regret can go negative (run_benchmark raises).
"""

from __future__ import annotations

import itertools
from datetime import date, timedelta

from app.engine.hubs import HUBS, hubs_for
from app.engine.planner import assemble, single_ticket_itinerary
from app.models import Itinerary, Preferences, Slice, Ticket, TripRequest
from app.providers.base import LiveFareProvider

ALL = 10**6  # max_results: every ticket the provider has
DAY = timedelta(days=1)


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


class _Searcher:
    """Memoised, unbudgeted searches; counts distinct searches for the record."""

    def __init__(self, live: LiveFareProvider):
        self.live = live
        self.memo: dict[tuple, list[Ticket]] = {}

    async def __call__(self, *legs: tuple[str, str, date]) -> list[Ticket]:
        key = tuple((o, d, day.isoformat()) for o, d, day in legs)
        if key not in self.memo:
            slices = [Slice(origin=o, destination=d, date=day) for o, d, day in legs]
            self.memo[key] = await self.live.search(slices, max_results=ALL)
        return self.memo[key]


async def candidates(live: LiveFareProvider, req: TripRequest, prefs: Preferences) -> list[Itinerary]:
    """Every itinerary in the candidate space (see module docstring), before hard limits."""
    search = _Searcher(live)
    home, dest, end = req.origin, req.destination, req.end_airport
    open_jaw = end != dest
    out: list[Itinerary] = []

    def add(it: Itinerary | None) -> None:
        if it is not None:
            out.append(it)

    pairs = [
        (d, r)
        for d, r in itertools.product(
            _days(req.depart_earliest, req.depart_latest), _days(req.return_earliest, req.return_latest)
        )
        if r > d
    ]
    for d, r in pairs:
        tag = f"{d:%m%d}-{r:%m%d}"
        for i, t in enumerate(await search((home, dest, d), (end, home, r))):
            it = single_ticket_itinerary(t, i)
            add(it.model_copy(update={"id": f"through-{tag}-{i}"}) if it else None)

        fixes = await search((end, dest, r)) if open_jaw else []
        homes = [r, r + DAY]
        if open_jaw:
            for r2 in homes:
                rets = await search((home, dest, d), (dest, home, r2))
                for (i, b), (k, t) in itertools.product(enumerate(fixes), enumerate(rets)):
                    add(assemble([t, b], [(0, 0)], [(1, 0), (0, 1)], dest, prefs, f"fix-{tag}-{r2:%m%d}-{i}-{k}"))

        for code in hubs_for(dest, req.hubs):
            hub = HUBS[code]
            # Long-haul options: (tickets, out parts, return parts) with position 0 reserved for positioning.
            longs: list[tuple[list[Ticket], list[tuple[int, int]], list[tuple[int, int]], str]] = []
            for k, lt in enumerate(await search((hub.longhaul_airport, dest, d), (end, hub.longhaul_airport, r))):
                longs.append(([lt], [(1, 0)], [(1, 1)], f"{k}"))
            if open_jaw:
                for r2 in homes:
                    for k, lt in enumerate(
                        await search((hub.longhaul_airport, dest, d), (dest, hub.longhaul_airport, r2))
                    ):
                        for i, b in enumerate(fixes):
                            longs.append(([lt, b], [(1, 0)], [(2, 0), (1, 1)], f"fix{r2:%m%d}-{k}-{i}"))
            if not longs:
                continue
            back_days = sorted({t[0].journeys[1][-1].arrive.date() for t, *_ in longs})
            pos_backs = sorted({b + extra for b in back_days for extra in (timedelta(0), DAY)})
            for airport in hub.arrival_airports:
                for pos_out, pos_back in itertools.product((d - DAY, d), pos_backs):
                    for j, pt in enumerate(await search((home, airport, pos_out), (airport, home, pos_back))):
                        for tickets, o_parts, r_parts, lid in longs:
                            add(
                                assemble(
                                    [pt, *tickets],
                                    [(0, 0), *o_parts],
                                    [*r_parts, (0, 1)],
                                    code,
                                    prefs,
                                    f"{code.lower()}-{airport}-{pos_out:%m%d}-{pos_back:%m%d}-{lid}-{j}",
                                )
                            )
    return out
