# Session report: F7-grounding-check (2026-11-07)

## Tests
- Unit tests: 95 passed, 0 failed (73 before; `tests/test_grounding.py` adds 22).
- Acceptance: F1-F7 and F10 pass (`test_orchestration.py::test_grounding` is new).
- Features passing: 8/22.
- The strongest test is built from a real `PlanResult` (simulator, seed 0, open-jaw Lima, budget 20). Sentences
  using its numbers in several formats must pass: `£1,059.50`, `£1,060`, `15h25`, `15.4 hours`, minutes, "£149 more".
  The same sentences with £5 or 0.5 h added must be caught.

## Metrics
Not run: no planner, simulator or LLM behaviour changed. The unsupported-number rate per answer needs F15, which
calls the check on real narrations.

## UI
Not run: nothing under `frontend/` or the API changed.

## What changed
- `app/agent/grounding.py`: `unsupported_numbers(text, tool_outputs)`, plus `claims()` and `supported_values()`.
- A claim is a number with a unit:
  - currency: `£1,060`, `£1.2k`, `900 GBP`;
  - duration: `12 hours`, `12-hour`, `15h25`, `4 hours 15 minutes`, `4h 15m`, `45 min`.

  Numbers without a unit (dates, ranks, "2 stops", "1 night", "option 1 of 5") are not claims, so they're ignored.
- Supporting values are typed by their JSON key. Money claims match money fields (`price`, `total_cost`,
  `vs_cheapest`, `utility`, the `breakdown` terms...). Duration claims match hours or minutes fields, with minutes
  converted. So `searches_used: 16` can't support "16 hours", and `travel_hours: 16` can't support "£16". Strings and
  non-JSON outputs are read with the same claim parser.
- Tolerances: £1 and 0.1 h, as the spec says. `£1.2k` is checked to its written precision (±£50).

## Open problems
- **Times of day and scores aren't checked.** CLAUDE.md says the LLM never produces a price, time or score. F7 covers
  prices and durations only, so "departs 23:45" or "scores 1,503" pass unchecked. Departure times are in the planner
  JSON as datetimes, so a times-of-day check is a small addition, worth doing before F15 if you want the invariant
  enforced in full.
- **Derived numbers are flagged.** A difference the planner didn't report ("saves 6 hours", or "£412 more" when only
  totals are in the output) is unsupported by design. F15's explain endpoint should hand the LLM the comparisons it
  will need (`vs_cheapest`, travel hours per journey), or its retry rate will be high.
- **Key typing is a substring list** (`MONEY_KEYS`, `HOUR_KEYS`, `MINUTE_KEYS`). A new planner field with an unusual
  name won't count as support until it's added.
- **`m` alone isn't treated as minutes** (only in `4h 15m`), so "15m" isn't a claim. That avoids misreading "5m
  people".
