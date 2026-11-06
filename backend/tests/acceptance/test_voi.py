import statistics


def _beats_heuristic(planner: str) -> None:
    from app.bench import BENCHMARK_TRIPS, run_benchmark

    recs = run_benchmark(planners=["heuristic", planner], budgets=[10, 20], seeds=[0, 1, 2], trips=BENCHMARK_TRIPS)
    for budget in (10, 20):

        def mean(p, b=budget):
            return statistics.mean(r["regret"] for r in recs if r["planner"] == p and r["budget"] == b)

        assert mean(planner) < mean("heuristic"), f"{planner} does not beat heuristic at budget {budget}"


def test_voi_gp_beats_heuristic():
    _beats_heuristic("voi-gp")


def test_voi_hier_beats_heuristic():
    _beats_heuristic("voi-hier")
