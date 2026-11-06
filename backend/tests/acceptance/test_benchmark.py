import json
import subprocess
import sys
from pathlib import Path

KEYS = {"planner", "trip", "budget", "seed", "searches_used", "best_utility", "optimum_utility", "regret", "wall_ms"}


def _stable(records):
    return [{k: v for k, v in r.items() if k != "wall_ms"} for r in records]


def test_run_benchmark():
    from app.bench import BENCHMARK_TRIPS, run_benchmark

    assert len(BENCHMARK_TRIPS) >= 10
    args = dict(planners=["heuristic"], budgets=[5, 15], seeds=[0], trips=BENCHMARK_TRIPS[:2])
    recs = run_benchmark(**args)
    assert len(recs) == 4
    for r in recs:
        assert KEYS <= set(r)
        assert r["regret"] >= -1e-6
        assert r["searches_used"] <= r["budget"]
    assert _stable(run_benchmark(**args)) == _stable(recs)


def test_cli_report(tmp_path: Path):
    backend = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "app.bench",
            "--planners",
            "heuristic",
            "--budgets",
            "5",
            "15",
            "--seeds",
            "0",
            "--trips",
            "2",
            "--out",
            str(tmp_path),
        ],
        cwd=backend,
        check=True,
        timeout=300,
    )
    records = json.loads((tmp_path / "bench.json").read_text())
    assert records and KEYS <= set(records[0])
    md = (tmp_path / "bench.md").read_text().lower()
    assert "regret" in md and "heuristic" in md
    assert (tmp_path / "regret.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
