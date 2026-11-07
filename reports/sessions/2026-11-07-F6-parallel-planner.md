# Session report: F6-parallel-planner (2026-11-07)

## Tests
- Unit tests: 64 passed, 0 failed (48 before; `tests/test_parallel_planner.py` adds 16).
- Acceptance: F1-F6 pass, including `test_orchestration.py::test_parallel_planner`.
- Features passing: 6/22.
- The equivalence tests compare the new planner with a frozen copy of the pre-F6 serial planner
  (`tests/serial_planner.py`, test-only). The two `PlanResult`s must be identical: rankings, pruning notes, searches
  used and notes. Coverage:
  - all 12 benchmark trips at budgets 1, 2, 3, 4, 5, 7, 10 and 20, so the budget runs out in every phase;
  - a hub whose long-haul search comes back empty (MAD, LHR or BCN) at budgets 5-12. Six of those cases need the
    second long-haul wave; I checked by counting the waves;
  - concurrent identical searches costing one search.

## Metrics
Acceptance scenario (open-jaw, 3-day window, budget 20, 50 ms simulated latency per search):

| Planner | Wall time | Searches | Waves |
| --- | --- | --- | --- |
| serial (pre-F6) | 870 ms | 16 | 16 |
| concurrent (F6) | 214 ms | 16 | 3 (3, 8, 5 searches) |

Benchmark: `uv run python -m app.bench --planners heuristic --budgets 5 10 20 30 --seeds 0 1 2 --out ../reports/latest`.

**Against the previous report (F5):** all 288 records are identical except `wall_ms`. Mean regret, searches used and
runs at the optimum are unchanged at every budget (realistic cache £183 / 69 / 30 / 30, near-unbiased cache
£188 / 36 / 30 / 30). Mean wall time per run was 59.0 ms before and 59.6 ms now. The benchmark simulator has no
latency, so concurrency can't save time there; most of the time is scoring.

## UI
Not run: nothing under `frontend/` or the API changed.

## What changed
- `app/engine/planner.py`: `plan()` searches in three concurrent waves:
  1. through tickets;
  2. the open-jaw fix plus every chosen hub's long-haul search;
  3. positioning.

  A replay of the serial loop's budget rules decides which searches run. It covers memo hits, the budget running out
  mid-phase (the same partial results and note), and an empty long-haul freeing budget for the next hub (a further
  long-haul wave).
- `app/providers/base.py`: `BudgetedProvider` shares searches already in flight, so concurrent repeats are free, like
  memoised ones. Added `key()`, `is_free()`, `known_keys()` and `exhausted()`.
- `SimConfig.latency_s`: simulated wait per live search. The cache stays instant.

## Open problems
- **The replay is the complex part.** `plan()` is now about twice as long, because it re-derives the serial loop's
  decisions instead of making them inline. The equivalence tests guard it. If the heuristic's search strategy ever
  changes on purpose, `tests/serial_planner.py` must be re-frozen in the same commit, and that commit labelled as a
  baseline change.
- **The cache is still read one call at a time.** Its calls are free and instant in the simulator. A real cache API
  (Travelpayouts) has latency, so those calls are worth gathering too once one is wired in.
- **Hook friction.** `protect_oracle.py` blocked two more harmless commands (`2>/dev/null` and `sed -i` in a command
  that also listed an acceptance path). Your fix still hasn't reached the remote.
