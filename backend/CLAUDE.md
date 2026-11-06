# Backend

- `app/engine/` is the search: `planner.py` (strategy), `utility.py` (scoring, limits, Pareto), `journeys.py` (assembling legs across tickets).
- `app/providers/` are fare sources behind two protocols in `base.py`: live (costs budget) and cached (free, stale). The simulator (F1) implements both.
- `app/llm/` (from F10) is the only place that talks to OpenAI: adapter, per-role routing (`parse`, `narrate`, `baseline`), spend guard. The internal message format stays content blocks (text / tool_use / tool_result).
- Planners share `plan()`'s signature and return `PlanResult`, so the benchmark and the race can run them side by side.
- Tests inject fake LLMs; never call a real API in tests. Utility is in pounds, higher is better; regret = optimum - found, always >= 0.
- JSON responses can't carry inf/NaN: use null for "no itinerary yet".
