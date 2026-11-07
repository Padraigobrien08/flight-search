"""Turn benchmark records into bench.json, bench.md (the ablation table) and regret.png.

Mean regret is over runs that found an itinerary; misses are counted in the
same cell, never dropped silently.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Reference palette (dataviz skill, light mode). A planner keeps its slot in every report.
PLANNER_COLORS = {"heuristic": "#2a78d6", "llm": "#eb6834", "voi-gp": "#1baf7a", "voi-hier": "#eda100"}
SPARE_COLORS = ["#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
SIM_TITLES = {"realistic": "Realistic cache", "unbiased": "Near-unbiased cache"}


def _color(planner: str, planners: list[str]) -> str:
    if planner in PLANNER_COLORS:
        return PLANNER_COLORS[planner]
    spare = [p for p in planners if p not in PLANNER_COLORS]
    return SPARE_COLORS[spare.index(planner) % len(SPARE_COLORS)]


def _ordered(values) -> list:
    return list(dict.fromkeys(values))


def _cells(records: list[dict], *keys: str) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        out[tuple(r[k] for k in keys)].append(r)
    return out


def _regret_cell(runs: list[dict]) -> str:
    found = [r["regret"] for r in runs if r["found"]]
    miss = len(runs) - len(found)
    if not found:
        return f"no itinerary ({miss}/{len(runs)})"
    text = f"{statistics.mean(found):.0f}"
    return text + (f" ({miss} missed)" if miss else "")


def mean_regret(records: list[dict]) -> dict[tuple[str, str, int], float | None]:
    """(sim, planner, budget) -> mean regret over runs that found an itinerary."""
    out = {}
    for key, runs in _cells(records, "sim", "planner", "budget").items():
        found = [r["regret"] for r in runs if r["found"]]
        out[key] = statistics.mean(found) if found else None
    return out


def markdown(records: list[dict], command: str) -> str:
    sims = _ordered(r["sim"] for r in records)
    planners = _ordered(r["planner"] for r in records)
    budgets = sorted({r["budget"] for r in records})
    trips = _ordered(r["trip"] for r in records)
    seeds = sorted({r["seed"] for r in records})
    head = "| Planner | " + " | ".join(f"Budget {b}" for b in budgets) + " |"
    rule = "| --- |" + " --- |" * len(budgets)

    lines = [
        "# Benchmark",
        "",
        f"{len(planners)} planner(s) x {len(trips)} trips x {len(seeds)} seeds ({', '.join(map(str, seeds))}) x "
        f"budgets {', '.join(map(str, budgets))}. Regret = optimum utility - best found, in £; lower is better, 0 is the "
        "exhaustive optimum. Means are over runs that found an itinerary; misses are shown in the cell.",
        "",
        f"Command: `{command}`",
        "",
        "![Regret against search budget](regret.png)",
    ]
    for sim in sims:
        rs = [r for r in records if r["sim"] == sim]
        by = _cells(rs, "planner", "budget")
        lines += ["", f"## Mean regret (£), {SIM_TITLES.get(sim, sim).lower()}", "", head, rule]
        for p in planners:
            lines.append(f"| {p} | " + " | ".join(_regret_cell(by[(p, b)]) for b in budgets) + " |")

    rs = [r for r in records if r["sim"] == sims[0]]
    by = _cells(rs, "planner", "budget")
    suffix = f", {SIM_TITLES.get(sims[0], sims[0]).lower()}"
    lines += ["", f"## Searches used, mean{suffix}", "", head, rule]
    for p in planners:
        lines.append(
            f"| {p} | "
            + " | ".join(f"{statistics.mean(r['searches_used'] for r in by[(p, b)]):.1f}" for b in budgets)
            + " |"
        )
    lines += ["", f"## Runs that reached the optimum{suffix}", "", head, rule]
    for p in planners:
        cells = [by[(p, b)] for b in budgets]
        lines.append(
            f"| {p} | "
            + " | ".join(f"{sum(r['found'] and r['regret'] < 0.01 for r in c)}/{len(c)}" for c in cells)
            + " |"
        )
    lines += ["", f"## Wall time per run, mean ms{suffix}", "", head, rule]
    for p in planners:
        lines.append(
            f"| {p} | " + " | ".join(f"{statistics.mean(r['wall_ms'] for r in by[(p, b)]):.0f}" for b in budgets) + " |"
        )

    by_trip = _cells(rs, "planner", "trip", "budget")
    for p in planners:
        lines += ["", f"## Mean regret (£) by trip: {p}{suffix}", "", "| Trip | " + head[len("| Planner | ") :], rule]
        for t in trips:
            lines.append(f"| {t} | " + " | ".join(_regret_cell(by_trip[(p, t, b)]) for b in budgets) + " |")
    return "\n".join(lines) + "\n"


DPI = 150
LABEL_GAP_PX = 12 * DPI / 72  # one 12 pt line between end labels (they are 9 pt)


def _spread(ys_px: list[float], gap: float) -> list[float]:
    """Space label positions at least `gap` apart, keeping their order.

    Labels that would collide form a cluster, spaced evenly and centred on its
    members' own positions; a label that collides with nothing stays put.
    """

    def positions(cluster: list[int]) -> list[float]:
        centre = sum(ys_px[i] for i in cluster) / len(cluster)
        start = centre - gap * (len(cluster) - 1) / 2
        return [start + k * gap for k in range(len(cluster))]

    clusters: list[list[int]] = []
    for i in sorted(range(len(ys_px)), key=lambda i: ys_px[i]):
        clusters.append([i])
        while len(clusters) > 1 and positions(clusters[-1])[0] - positions(clusters[-2])[-1] < gap - 1e-9:
            clusters[-2:] = [clusters[-2] + clusters[-1]]
    out = [0.0] * len(ys_px)
    for cluster in clusters:
        for i, y in zip(cluster, positions(cluster), strict=True):
            out[i] = y
    return out


def chart(records: list[dict], path: Path) -> None:
    sims = _ordered(r["sim"] for r in records)
    planners = _ordered(r["planner"] for r in records)
    budgets = sorted({r["budget"] for r in records})
    means = mean_regret(records)
    n_trips = len({r["trip"] for r in records})
    n_seeds = len({r["seed"] for r in records})
    legend = len(planners) > 1

    width, height = 5.2 * len(sims) + 1.2, 4.4
    fig, axes = plt.subplots(1, len(sims), figsize=(width, height), sharey=True, squeeze=False, dpi=DPI)
    fig.patch.set_facecolor(SURFACE)
    fig.subplots_adjust(
        left=0.8 / width,
        right=1 - 0.2 / width,
        top=1 - 1.05 / height,
        bottom=(0.95 if legend else 0.7) / height,
        wspace=0.12,
    )
    top = max([v for v in means.values() if v is not None] or [1.0])
    for ax, sim in zip(axes[0], sims, strict=True):
        ax.set_facecolor(SURFACE)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.grid(axis="y", color=GRID, linewidth=1, linestyle="-")
        ax.set_axisbelow(True)
        ax.tick_params(colors=INK_2, labelsize=9, length=0)
        ax.set_xticks(budgets)
        ax.set_xlim(min(budgets) - 1, max(budgets) + (max(budgets) - min(budgets)) * 0.32 + 1)
        ax.set_ylim(0, top * 1.12)
        ax.set_xlabel("Search budget (live searches)", color=INK_2, fontsize=9)
        ax.set_title(SIM_TITLES.get(sim, sim), color=INK, fontsize=10, loc="left")
        ends: list[tuple[str, float, float]] = []
        for p in planners:
            pts = [(b, means.get((sim, p, b))) for b in budgets]
            pts = [(b, v) for b, v in pts if v is not None]
            if not pts:
                continue
            xs, ys = zip(*pts, strict=True)
            color = _color(p, planners)
            ax.plot(xs, ys, color=color, linewidth=2, solid_capstyle="round", zorder=2)
            ax.scatter(xs, ys, s=48, color=color, edgecolors=SURFACE, linewidths=2, zorder=3)
            ends.append((p, xs[-1], ys[-1]))
        # Direct labels at the line ends, nudged apart so converging lines stay readable.
        px = [ax.transData.transform((x, y))[1] for _, x, y in ends]
        for (p, x, y), orig, new in zip(ends, px, _spread(px, LABEL_GAP_PX), strict=True):
            ax.annotate(
                f"{p}  £{y:.0f}",
                (x, y),
                xytext=(8, (new - orig) * 72 / DPI),
                textcoords="offset points",
                va="center",
                fontsize=9,
                color=INK,
            )
    axes[0][0].set_ylabel("Mean regret (£)", color=INK_2, fontsize=9)
    fig.text(0.2 / width, 1 - 0.3 / height, "Regret against search budget", color=INK, fontsize=12, fontweight="bold")
    fig.text(
        0.2 / width,
        1 - 0.55 / height,
        f"Mean over {n_trips} trips x {n_seeds} seeds; lower is better, 0 is the exhaustive optimum",
        color=INK_2,
        fontsize=9,
    )
    if legend:
        handles = [plt.Line2D([], [], color=_color(p, planners), linewidth=2, marker="o") for p in planners]
        fig.legend(
            handles,
            planners,
            loc="lower left",
            bbox_to_anchor=(0.8 / width, 0.02),
            ncol=len(planners),
            frameon=False,
            fontsize=9,
            labelcolor=INK,
        )
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def write_report(records: list[dict], out: Path, command: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "bench.json").write_text(json.dumps(records, indent=1) + "\n")
    (out / "bench.md").write_text(markdown(records, command))
    chart(records, out / "regret.png")
