import statistics


def test_voi_beats_heuristic():
    from app.bench import BENCHMARK_TRIPS, run_benchmark

    recs = run_benchmark(planners=["heuristic", "voi"], budgets=[10, 20], seeds=[0, 1, 2], trips=BENCHMARK_TRIPS)
    for budget in (10, 20):

        def mean(p, b=budget):
            return statistics.mean(r["regret"] for r in recs if r["planner"] == p and r["budget"] == b)

        assert mean("voi") < mean("heuristic"), f"voi does not beat heuristic at budget {budget}"
