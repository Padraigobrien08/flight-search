"""Check the simulator against the spec's real fares: `uv run python -m app.sim.calibrate [--seeds N]`.

Prints a markdown report: anchors vs simulated medians across seeds, the spec's
complete prices, date sensitivity, cache bias per route and La Paz premiums.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
from datetime import date, timedelta

from app.models import Slice
from app.sim.network import SERVICES
from app.sim.prices import UNBIASED_CACHE, SimConfig
from app.sim.simulator import FareSimulator

OUT, BACK = date(2027, 5, 22), date(2027, 6, 6)


async def cheapest(sim: FareSimulator, legs: list[tuple[str, str, date]]) -> float | None:
    tickets = await sim.search([Slice(origin=o, destination=d, date=day) for o, d, day in legs])
    return tickets[0].price if tickets else None


def med(xs: list[float | None]) -> float:
    return statistics.median([x for x in xs if x is not None])


async def report(seeds: int) -> str:
    sims = [FareSimulator(seed=s) for s in range(seeds)]
    lines = [f"Medians across seeds 0-{seeds - 1}. Dates: out Sat 22 May, back Sun 6 Jun 2027 unless stated.", ""]

    lines += [
        "## Anchors",
        "",
        "| Service | Source | Anchor £ | Simulated £ | Ratio |",
        "| --- | --- | --- | --- | --- |",
    ]
    for svc in SERVICES:
        a = svc.anchor
        vals = []
        for sim in sims:
            if a.fare == "return" and svc.back is not None:
                f = sim.model.fare(svc, svc.out.origin, svc.out.destination, a.seen_out)
                b = sim.model.fare(svc, svc.back.origin, svc.back.destination, a.seen_back)
                vals.append(sim.config.return_discount * (f + b))
            else:
                vals.append(sim.model.fare(svc, svc.out.origin, svc.out.destination, a.seen_out))
        m = med(vals)
        lines.append(f"| {svc.name} | {a.source} | {a.gbp:.0f} | {m:.0f} | {m / a.gbp:.3f} |")

    lines += ["", "## Spec prices", "", "| Spec | Real £ | Simulated £ |", "| --- | --- | --- |"]
    checks = {
        "London split: EDI-STN + LHR-LIM": (
            762,
            [[("EDI", "STN", OUT), ("STN", "EDI", BACK)], [("LHR", "LIM", OUT), ("LIM", "LHR", BACK)]],
        ),
        "Madrid split: EDI-MAD + MAD-LIM": (
            911,
            [[("EDI", "MAD", OUT), ("MAD", "EDI", BACK)], [("MAD", "LIM", OUT), ("LIM", "MAD", BACK)]],
        ),
        "Cheapest through EDI-LIM (Air Canada)": (915, [[("EDI", "LIM", OUT), ("LIM", "EDI", BACK)]]),
    }
    for label, (real, tickets) in checks.items():
        totals = []
        for sim in sims:
            parts = [await cheapest(sim, t) for t in tickets]
            totals.append(None if None in parts else sum(parts))
        lines.append(f"| {label} | {real} | {med(totals):.0f} |")

    lines += ["", "## Date sensitivity, LHR-LIM return", ""]
    shifts = []
    for sim in sims:
        base = await cheapest(sim, [("LHR", "LIM", OUT), ("LIM", "LHR", BACK)])
        moved = [
            await cheapest(sim, [("LHR", "LIM", OUT + timedelta(k)), ("LIM", "LHR", BACK + timedelta(k))])
            for k in (-3, -2, -1, 1, 2, 3)
        ]
        shifts.append(max(abs(m - base) for m in moved))
    over = sum(s >= 15 for s in shifts)
    lines.append(
        f"Largest change from moving both dates by up to 3 days: median £{statistics.median(shifts):.0f}; "
        f"£15 or more in {over}/{seeds} seeds (spec: under £15, from one observation)."
    )

    for title, cfg in (("realistic (default)", SimConfig()), ("near-unbiased (UNBIASED_CACHE)", UNBIASED_CACHE)):
        lines += [
            "",
            f"## Cache bias, {title}",
            "",
            "| Route | Median cache / true lowest | Spread (p10-p90) |",
            "| --- | --- | --- |",
        ]
        csims = [FareSimulator(seed=s, config=cfg) for s in range(seeds)]
        for o, d in [
            ("MAD", "LIM"),
            ("LHR", "LIM"),
            ("CDG", "LIM"),
            ("AMS", "LIM"),
            ("LIS", "LIM"),
            ("BCN", "LIM"),
            ("EDI", "MAD"),
            ("EDI", "STN"),
        ]:
            ratios = []
            for sim in csims:
                for k in range(0, 21, 4):
                    day = OUT + timedelta(k)
                    truth = await cheapest(sim, [(o, d, day)])
                    cached = await sim.lowest_price(o, d, day)
                    if truth and cached:
                        ratios.append(cached / truth)
            q = statistics.quantiles(ratios, n=10)
            lines.append(f"| {o}-{d} | {statistics.median(ratios):.3f} | {q[0]:.2f}-{q[-1]:.2f} |")

    lines += [
        "",
        "## La Paz premium (open-jaw minus Lima return, same hub long-haul)",
        "",
        "| Hub | Back Sun 6 Jun £ | Back Sat 5 Jun £ |",
        "| --- | --- | --- |",
    ]
    for hub in ["MAD", "LHR", "CDG", "AMS", "LIS", "BCN"]:
        cells = []
        for back in (BACK, date(2027, 6, 5)):
            prem = []
            for sim in sims:
                oj = await cheapest(sim, [(hub, "LIM", OUT), ("LPB", hub, back)])
                rt = await cheapest(sim, [(hub, "LIM", OUT), ("LIM", hub, back)])
                prem.append(oj - rt if oj and rt else None)
            cells.append(f"{med(prem):.0f}" if any(p is not None for p in prem) else "no La Paz link")
        lines.append(f"| {hub} | {cells[0]} | {cells[1]} |")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=50)
    print(asyncio.run(report(p.parse_args().seeds)))


if __name__ == "__main__":
    main()
