"""Record race runs for replay: `uv run python -m app.race [--planners heuristic llm] [--placeholder]`.

Writes data/race/recordings.json for the demo trip at budgets 5/10/20/30. Recording the
`llm` planner makes real API calls (the baseline model, inside the spend cap) and needs
OPENAI_API_KEY; --placeholder uses the scripted stand-in instead and labels its runs so.
Runs for planners not named are kept.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.race.core import PLACEHOLDER_NOTE, RACE_BUDGETS, RACE_TRIP, RECORDINGS, load_recordings, optimum, run_planner
from app.race.standin import ScriptedStandIn


async def record(planners: list[str], budgets: list[int], seed: int, placeholder: bool, out: Path) -> dict:
    data = load_recordings(out)
    if data.get("trip") != RACE_TRIP.name or data.get("seed") != seed:
        data = {"trip": RACE_TRIP.name, "seed": seed, "runs": {}}
    data["optimum_utility"] = await optimum(RACE_TRIP, seed)
    data["trip_request"] = RACE_TRIP.request.model_dump(mode="json")
    for name in planners:
        factory, source, note = None, "recorded", None
        if name == "llm":
            if placeholder:
                factory, source, note = (lambda: ScriptedStandIn(RACE_TRIP.request)), "placeholder", PLACEHOLDER_NOTE
            else:
                from app.bench.run import default_llm_factory

                factory = default_llm_factory()
        runs = {}
        for b in budgets:
            run = await run_planner(name, RACE_TRIP, b, seed, data["optimum_utility"], factory, source, note)
            runs[str(b)] = run.model_dump(mode="json") | {"recorded_at": datetime.now(UTC).date().isoformat()}
            print(f"{name} budget {b}: {len(run.steps)} steps, final regret {run.steps[-1].regret}", file=sys.stderr)
        data["runs"][name] = runs
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1) + "\n")
    return data


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.race", description=__doc__.splitlines()[0])
    p.add_argument("--planners", nargs="+", default=["heuristic", "llm"])
    p.add_argument("--budgets", nargs="+", type=int, default=list(RACE_BUDGETS))
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--placeholder", action="store_true", help="record `llm` with the scripted stand-in (labelled)")
    p.add_argument("--out", type=Path, default=RECORDINGS)
    a = p.parse_args(argv)
    asyncio.run(record(a.planners, a.budgets, a.seed, a.placeholder, a.out))
    print(f"wrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
