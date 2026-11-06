import json
import time

from app.models import Preferences

from ._trips import lima_trip


async def test_parallel_planner():
    from app.sim import FareSimulator, SimConfig

    from app.engine.planner import plan
    from app.providers.base import BudgetedProvider

    latency = 0.05
    sim = FareSimulator(seed=0, config=SimConfig(latency_s=latency))
    t0 = time.perf_counter()
    res = await plan(lima_trip(flex_days=3), Preferences(), BudgetedProvider(sim, 20), sim)
    elapsed = time.perf_counter() - t0
    assert res.searches_used >= 6
    assert elapsed < 0.5 * res.searches_used * latency


def test_grounding():
    from app.agent.grounding import unsupported_numbers

    outputs = [
        json.dumps(
            {
                "ranked": [
                    {"total_cost_gbp": 1059.5, "vs_cheapest_shown_gbp": 149.0, "journeys": [{"travel_hours": 15.1}]}
                ]
            }
        )
    ]
    assert unsupported_numbers("Madrid costs £1,060, £149 more, and takes 15.1 hours.", outputs) == []
    bad = unsupported_numbers("Madrid costs £980 and takes 12 hours.", outputs)
    assert "£980" in bad
    assert any("12" in b for b in bad)
    # Dates, ranks and small counts are not claims about prices or durations.
    assert unsupported_numbers("Leave on 22 May; option 1 of 5 has 2 stops.", outputs) == []


def test_llm_planner_baseline():
    from app.bench import BENCHMARK_TRIPS, run_benchmark

    from app.agent.llm import TurnResult

    trip = BENCHMARK_TRIPS[0]

    class FakeSearcher:
        def __init__(self):
            self.turns = 0

        async def stream_turn(self, system, tools, messages):
            assert "search_route" in [t["name"] for t in tools]
            self.turns += 1
            if self.turns <= 3:
                yield TurnResult(
                    content=[
                        {
                            "type": "tool_use",
                            "id": f"t{self.turns}",
                            "name": "search_route",
                            "input": {
                                "origin": trip.origin,
                                "destination": trip.destination,
                                "date": trip.depart_earliest.isoformat(),
                                "return_date": trip.return_earliest.isoformat(),
                            },
                        }
                    ],
                    stop_reason="tool_use",
                )
            else:
                yield TurnResult(content=[{"type": "text", "text": "done"}], stop_reason="end_turn")

    recs = run_benchmark(planners=["llm"], budgets=[5], seeds=[0], trips=[trip], llm_factory=FakeSearcher)
    assert recs[0]["planner"] == "llm"
    # Repeated identical searches are memoised and must not spend budget twice.
    assert recs[0]["searches_used"] == 1
