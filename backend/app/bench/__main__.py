"""`uv run python -m app.bench --planners heuristic --budgets 5 10 20 30 --seeds 0 1 2 --out ../reports/latest`

Writes bench.json (every run), bench.md (the ablation table) and regret.png
(regret against budget, one line per planner, one panel per cache setting).
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from app.bench.report import write_report
from app.bench.run import PLANNERS, run_benchmark
from app.bench.trips import BENCHMARK_TRIPS
from app.sim import UNBIASED_CACHE, SimConfig

CACHES = {"realistic": SimConfig(), "unbiased": UNBIASED_CACHE}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.bench", description=__doc__.splitlines()[0])
    p.add_argument("--planners", nargs="+", default=sorted(PLANNERS), choices=sorted(PLANNERS))
    p.add_argument("--budgets", nargs="+", type=int, default=[5, 10, 20, 30])
    p.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    p.add_argument("--trips", type=int, default=len(BENCHMARK_TRIPS), help="use the first N benchmark trips")
    p.add_argument(
        "--cache",
        nargs="+",
        default=list(CACHES),
        choices=list(CACHES),
        help="cache settings to run; 'unbiased' is the robustness check",
    )
    p.add_argument("--out", type=Path, default=Path("../reports/latest"))
    args = p.parse_args(argv)

    trips = BENCHMARK_TRIPS[: args.trips]
    records: list[dict] = []
    for name in args.cache:
        print(f"running {name} cache: {len(args.planners)} planner(s) x {len(trips)} trips ...", file=sys.stderr)
        records += run_benchmark(args.planners, args.budgets, args.seeds, trips, CACHES[name], name)
    command = "uv run python -m app.bench " + " ".join(
        shlex.quote(a) for a in (argv if argv is not None else sys.argv[1:])
    )
    write_report(records, args.out, command)
    print(f"wrote {args.out / 'bench.json'}, bench.md, regret.png ({len(records)} runs)", file=sys.stderr)


if __name__ == "__main__":
    main()
