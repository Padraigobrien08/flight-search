"""Check NETWORK.md's stated intentions against the exhaustive optimum: `uv run python -m app.sim.claims [--seeds N]`.

Each claim was written before any fare model existed; this prints whether the
simulator actually behaves that way, across seeds. A claim that fails is a
finding about the network, not something to tune away.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import date, timedelta

from app.engine.utility import score, violations
from app.models import Preferences, ScoredItinerary, TripRequest
from app.sim.exhaustive import candidates
from app.sim.simulator import FareSimulator

OUT = date(2027, 5, 22)


def trip(back: date, return_from: str | None = "LPB", hubs: list[str] | None = None) -> TripRequest:
    return TripRequest(
        origin="EDI",
        destination="LIM",
        return_from=return_from,
        depart_earliest=OUT,
        depart_latest=OUT,
        return_earliest=back,
        return_latest=back,
        hubs=hubs,
    )


def label(s: ScoredItinerary | None) -> str:
    if s is None:
        return "none"
    it = s.itinerary
    return it.hub if it.structure != "through" else "through"


async def ranked(sim: FareSimulator, req: TripRequest, prefs: Preferences) -> list[ScoredItinerary]:
    out = [score(it, prefs) for it in await candidates(sim, req, prefs) if not violations(it, prefs)]
    return sorted(out, key=lambda s: s.utility, reverse=True)


def share(counter: Counter, n: int) -> str:
    return ", ".join(f"{k} {v}/{n}" for k, v in counter.most_common())


async def report(seeds: int) -> str:
    sims = [FareSimulator(seed=s) for s in range(seeds)]
    back = date(2027, 6, 6)
    lines = [
        f"Optimum = highest-utility feasible itinerary in the exhaustive space; {seeds} seeds. Out Sat 22 May 2027.",
        "",
    ]

    lines += [
        "## 1. Madrid's value depends on preferences",
        "",
        "| Stopover bonus £ | Lima return: optimum hub | Open-jaw: optimum hub |",
        "| --- | --- | --- |",
    ]
    for bonus in (0, 80, 150):
        prefs = Preferences(stopover_bonus=bonus)
        cells = []
        for rf in (None, "LPB"):
            c = Counter([label((await ranked(sim, trip(back, rf), prefs) or [None])[0]) for sim in sims])
            cells.append(share(c, seeds))
        lines.append(f"| {bonus} | {cells[0]} | {cells[1]} |")

    lines += [
        "",
        "## 2. London is the cheapest complete price, not the best journey (Lima return, default preferences)",
        "",
    ]
    fares, allin, best = Counter(), Counter(), Counter()
    for sim in sims:
        r = await ranked(sim, trip(back, None), Preferences())
        fares[label(min(r, key=lambda s: s.itinerary.fare_total))] += 1
        allin[label(min(r, key=lambda s: s.itinerary.total_cost))] += 1
        best[label(r[0])] += 1
    lines += [
        f"- Cheapest by fares: {share(fares, seeds)}",
        f"- Cheapest all-in (fares + hotel nights + airport transfers): {share(allin, seeds)}",
        f"- Optimum: {share(best, seeds)}",
    ]

    lines += [
        "",
        "## 4. The best open-jaw hub depends on the return date (default preferences)",
        "",
        "| Return date | Optimum hub |",
        "| --- | --- |",
    ]
    for k in range(7):
        day = date(2027, 6, 1) + timedelta(days=k)
        c = Counter([label((await ranked(sim, trip(day), Preferences()) or [None])[0]) for sim in sims])
        lines.append(f"| {day:%a %d %b} | {share(c, seeds)} |")

    lines += ["", "## 5. Lisbon only works with the La Paz fix (open-jaw, Lisbon as the only hub)", ""]
    structures = Counter()
    for sim in sims:
        for it in await candidates(sim, trip(back, hubs=["LIS"]), Preferences()):
            if it.hub == "LIS":
                via_lima = any(leg.destination == "LIM" for leg in it.journeys[1].legs)
                structures["with fix" if via_lima else "without fix"] += 1
    lines.append(f"- Lisbon candidates: {dict(structures)}")

    lines += ["", "## 7. Amsterdam and Paris are rarely best", ""]
    c = Counter()
    for bonus in (0, 80, 150):
        for rf in (None, "LPB"):
            for sim in sims:
                c[label((await ranked(sim, trip(back, rf), Preferences(stopover_bonus=bonus)) or [None])[0])] += 1
    total = sum(c.values())
    lines.append(f"- Optimum hub over 3 bonuses x 2 trip shapes x {seeds} seeds: {share(c, total)}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=20)
    print(asyncio.run(report(p.parse_args().seeds)))


if __name__ == "__main__":
    main()
