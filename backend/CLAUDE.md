# Backend

- `app/engine/` is the search: `planner.py` (strategy), `utility.py` (scoring, limits, Pareto), `journeys.py` (assembling legs across tickets).
- `app/providers/` are fare sources behind two protocols in `base.py`: live (costs budget) and cached (free, stale).
- `app/agent/` is the loop: `agent.py` (UI messages in, stream out), `tools.py` (the only place tools touch the engine), `llm.py` (swap in fakes for tests).
- New planners must have the signature of `plan()` and return `PlanResult`, so the benchmark can run them side by side.
- Tests use `tests/fakes.py::ScriptedLLM` for the loop; never call the real API in tests.
- Utility values are in pounds and higher is better. Regret = optimum utility - found utility, always >= 0.
