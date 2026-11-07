import json

from app.bench.__main__ import main
from app.bench.report import _spread, markdown


def rec(planner="heuristic", budget=5, seed=0, regret=10.0, sim="realistic", trip="t1"):
    return {
        "planner": planner,
        "trip": trip,
        "budget": budget,
        "seed": seed,
        "sim": sim,
        "searches_used": budget,
        "found": regret is not None,
        "best_utility": None if regret is None else -100 - regret,
        "optimum_utility": -100.0,
        "regret": regret,
        "wall_ms": 1.0,
    }


def test_misses_are_shown_in_the_cell_not_dropped():
    md = markdown([rec(regret=10), rec(seed=1, regret=None), rec(budget=10, regret=None)], "cmd")
    assert "| heuristic | 10 (1 missed) | no itinerary (1/1) |" in md


def test_end_labels_are_spread_to_the_gap_and_keep_their_order():
    out = _spread([100.0, 101.0, 102.0, 300.0], gap=20)
    assert all(b - a >= 20 - 1e-9 for a, b in zip(out[:3], out[1:3], strict=False))
    assert out == sorted(out)
    assert out[3] == 300.0
    assert _spread([5.0, 50.0], gap=20) == [5.0, 50.0]


def test_cli_writes_all_three_files(tmp_path):
    main(["--budgets", "5", "--seeds", "0", "--trips", "1", "--cache", "realistic", "--out", str(tmp_path)])
    records = json.loads((tmp_path / "bench.json").read_text())
    assert len(records) == 1 and records[0]["sim"] == "realistic"
    assert "--trips 1" in (tmp_path / "bench.md").read_text()
    assert (tmp_path / "regret.png").read_bytes()[:4] == b"\x89PNG"
