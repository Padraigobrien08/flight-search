# Session report: F3-ground-truth (2026-11-07)

## Tests
- Unit tests: 41 passed, 0 failed (25 before; `tests/test_exhaustive.py` adds 16).
- Acceptance: `test_determinism` (F1), `test_structure` (F2) and `test_ground_truth` (F3) pass.
- Features passing: 3/22 (F1, F2, F3).
- `tests/test_exhaustive.py` is stricter than the acceptance test. For 3 seeds x 5 cases (open-jaw, Lima return,
  stopover bonus £300, same-day self-transfers allowed, a 4 x 4-day window) and budgets 5/15/40, every itinerary
  `plan()` ranks is in the exhaustive space, and none beats the optimum.

## Metrics
Not run: `app.bench` doesn't exist yet (F4/F5). Preview instead: the heuristic's regret on one trip. This is not the
benchmark: one trip, 10 seeds, default preferences, open-jaw Lima, out 21-24 May, back 5-8 Jun 2027.

| Budget | Mean regret £ | Max regret £ | Seeds at optimum | Mean searches used |
| --- | --- | --- | --- | --- |
| 5 | 254 | 347 | 0/10 | 5.0 |
| 10 | 107 | 234 | 0/10 | 9.0 |
| 20 | 68 | 143 | 0/10 | 16.0 |
| 30 | 68 | 143 | 0/10 | 16.0 |

The heuristic stops at 16 searches whatever the budget. Its fixed plan (3 date pairs, best pair only for hubs) runs
out of things to try, so £68 is its floor on this trip.

Exhaustive search takes about 0.7 s for a 4 x 4-day window (16 date pairs).

## UI
Not run: nothing under `frontend/` or the API changed.

## What changed
- `app/sim/exhaustive.py`: `candidates()` enumerates the space; `exhaustive_best()` returns the highest-utility
  feasible itinerary in it, with no Pareto filter, since a dominated option can still score higher.
- The space contains everything `plan()` builds, and more. That includes every arrival airport, the hub long-haul as
  a hub return plus the La Paz fix, and 0 or 1 planned nights each way. The docstring defines it; a planner that
  builds outside it has to extend it first.
- `app/sim/claims.py`: checks NETWORK.md's intentions against the optimum (below).
- `planner.py`: `_single_ticket_itinerary` renamed to `single_ticket_itinerary`, now shared. No behaviour change.

## NETWORK.md claims against the optimum (`uv run python -m app.sim.claims`, 20 seeds)

| # | Claim | Result |
| --- | --- | --- |
| 1 | Madrid's value depends on preferences | Holds. Madrid is optimal in 12/20 (Lima return) and 5/20 (open-jaw) seeds at a £0 stopover bonus, and 17/20 and 14/20 at £150. At £0, through tickets take 7/20 and 10/20. |
| 2 | London is the cheapest complete price, not the best journey | Holds on fares: cheapest by fares in 20/20, optimal in 1/20. All-in it isn't the cheapest: its two hotel nights and the airport change make a through ticket cheapest in 17/20. |
| 4 | The best open-jaw hub depends on the return date | Holds. Madrid is optimal in 17-18/20 seeds on Mon, Thu and Sat returns (its Santa Cruz link flies) and 10-12/20 on other days, where London takes 6-8/20. |
| 5 | Lisbon only works with the La Paz fix | Holds: all 160 Lisbon candidates use it. |
| 7 | Amsterdam and Paris are rarely best | Holds: Amsterdam is optimal in 1/120 cases, Paris in 0/120. |

Claim 3 (the Barcelona cache trap) was checked in F2. Claim 6 (through tickets span the price range) holds by
construction.

## Open problems
- **The space is a modelling choice.** It caps planned stays at one night each way and uses only the six hubs. A
  planner allowed two nights in Madrid could beat the "optimum". The docstring says so; F4 could assert regret >= 0
  on every run to catch it.
- **Benchmark cost.** One optimum per (trip, seed, preferences) at about 0.7 s for 16 date pairs. A 7 x 7 window will
  be about 2 s, so F4 should compute each optimum once and reuse it across planners and budgets.
- **Barcelona is optimal more than intended** (9/120). It's the cache trap (#3), but with a non-stop and a cheap
  positioning flight it is sometimes the real answer. That's fine for a trap (it shouldn't be hopeless), but it is
  noted.
