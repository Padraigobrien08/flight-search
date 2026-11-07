# Session report: F4-benchmark-run (2026-11-07)

## Tests
- Unit tests: 45 passed, 0 failed (41 before; `tests/test_bench.py` adds 4: unique trips, unknown planner, a planner
  that finds nothing, a planner that beats the optimum).
- Acceptance: F1-F4 pass (`test_determinism`, `test_structure`, `test_ground_truth`, `test_run_benchmark`).
  `test_cli_report` (F5) fails: `app.bench` has no CLI yet, as expected.
- Features passing: 4/22.

## Metrics
First full benchmark: heuristic only (the only planner so far), 12 trips x budgets 5/10/20/30 x seeds 0-2 = 144 runs per
cache setting. No previous report to compare with. Run from a scratch script; the one-command version
(`python -m app.bench`, with bench.md and regret.png) is F5.

Mean regret £, all 12 trips:

| Cache | b=5 | b=10 | b=20 | b=30 |
| --- | --- | --- | --- | --- |
| realistic (default) | 183 | 69 | 30 | 30 |
| near-unbiased (`UNBIASED_CACHE`) | 188 | 36 | 30 | 30 |

- Every run found an itinerary (0 misses); none had negative regret.
- 18 of 144 realistic runs reached the optimum.
- Mean searches used: 4.9 / 9.2 / 15.6 / 15.6. The heuristic stops by itself at about 16 searches, so budgets 20 and 30
  are the same run.
- At budget 10 the realistic cache's optimism costs the heuristic £33 of regret on average (69 against 36). It makes no
  difference at the other budgets.
- Wall time: about 27 s per cache setting for all 144 runs. Most of it is the 36 exhaustive optima.

Mean regret £ by trip (realistic cache):

| Trip | b=5 | b=10 | b=20 | b=30 |
| --- | --- | --- | --- | --- |
| oj-spec-dates | 33 | 27 | 2 | 2 |
| rt-spec-dates | 21 | 0 | 0 | 0 |
| oj-flex3 | 248 | 108 | 19 | 19 |
| rt-flex3 | 67 | 19 | 19 | 19 |
| oj-flex7 | 248 | 105 | 82 | 82 |
| oj-early-may | 247 | 75 | 61 | 61 |
| oj-late-june | 247 | 104 | 100 | 100 |
| oj-stopover-lover | 365 | 108 | 19 | 19 |
| oj-no-stopovers | 34 | 34 | 19 | 19 |
| oj-time-poor | 416 | 176 | 19 | 19 |
| oj-budget-traveller | 187 | 68 | 15 | 15 |
| rt-one-week | 81 | 7 | 7 | 7 |

Regret is highest on the wide or moved windows (flex7, early May, late June), where three sampled date pairs miss the
good dates. It is near zero on fixed-date Lima returns.

## UI
Not run: nothing under `frontend/` or the API changed.

## What changed
- `app/bench/trips.py`: `BENCHMARK_TRIPS`, 12 Lima variants. Each has a name, a request, a preference profile and a
  one-line reason. The first two are one-day windows, because both acceptance tests use `BENCHMARK_TRIPS[:2]`.
- `app/bench/run.py`: `run_benchmark()` (sync) and `run_benchmark_async()`. Records carry the nine required keys,
  plus `sim`, `found`, `best_id` and `optimum_id`. A `PLANNERS` registry is ready for F8's `llm`.

## Open problems
- **Decision taken without asking:** a run that finds nothing is recorded with `found: false` and null regret. It is
  not dropped and not given a made-up penalty, so F5's table must show the miss count next to mean regret. None
  happened in this run.
- **Decision taken without asking:** negative regret raises `RegretBelowZero` rather than being reported, because it
  means the exhaustive space is incomplete.
- **The heuristic's ceiling.** It never uses more than about 16 searches, so its regret at budgets 20 and 30 is the
  same. That is a property of the baseline, not the benchmark; it makes the fare models' job at budget 20 clear-cut.
- **Seeds.** Three seeds per cell, as the spec says. Per-trip means move by tens of pounds between seeds, so small
  differences between planners will need more seeds or a paired comparison.
