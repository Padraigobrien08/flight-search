# Session report: F1-sim-determinism (2026-11-07)

## Tests
- Unit tests: 17 passed, 0 failed (13 before this session, plus 4 new in `backend/tests/test_sim.py`).
- Acceptance: `tests/acceptance/test_simulator.py::test_determinism` passes.
- Features passing: 1/22 (F1-sim-determinism).

## Metrics
Not run: `app.bench` doesn't exist yet (F4/F5).

## UI
Not run: nothing under `frontend/` or the API changed.

## What changed
- New `app/sim/` package: `FareSimulator(seed)` provides both `search()` (live) and `lowest_price()` (cache).
- Each random draw is seeded with sha256 of (seed, what is being priced). Results don't depend on call order or `PYTHONHASHSEED`, so planners can't influence each other's prices.
- Prices are the real one-way anchors × 0.8 for multi-slice tickets × lognormal noise (sd 0.08). The cache is the cheapest one-way level × lognormal noise (sd 0.06).
- The heuristic `plan()` runs on the simulator through `BudgetedProvider` (unit test).

## Open problems
- **Shortcut:** schedules and price anchors are reused from `app/providers/fixture.py`, including its private helpers `_templates` and `_legs`. F2 should move the network into `app/sim/` and add the hierarchical model (route × date × weekday × noise). For now there is no weekday or date effect, so `test_structure` will fail its Saturday-vs-Tuesday check.
- **Simulator assumption:** the cache is centred on the true price level with no staleness bias yet. F2 decides whether it is optimistic, like the old `FixtureCache` (×0.95).
- **Harness friction:** `protect_oracle.py` treats any `>` in a Bash command that mentions an acceptance path or `features.json` as a write. That includes `2>&1` and the `<...>` in a co-author email. I worked around it (no redirect; commit messages from files) and didn't change the hook.
