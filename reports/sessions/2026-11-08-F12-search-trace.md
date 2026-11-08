# Session report: F12-search-trace (2026-11-08)

## Tests
- Unit tests: 124 passed, 0 failed (108 before; `tests/test_trace.py` adds 16).
- Backend acceptance: all 14 tests for F1-F8 and F10-F12 pass (`test_api.py::test_trace` is new).
- Features passing: 11/22.
- What the new tests check:
  - one search event per budgeted search, numbered 1..n, each with a reason and slices: all 12 benchmark trips at
    budgets 1, 3, 5, 10 and 20, so including budgets that run out mid-phase;
  - every pruning note appears in the trace as a `prune` event;
  - every hub gets a `cache_bound` event, and all of them come before any hub search;
  - concurrent duplicate and memoised searches leave no event;
  - the `llm` planner traces its searches and its cache lookups;
  - the API returns the trace, and a rerank keeps it.

## Metrics
`uv run python -m app.bench --out ../reports/latest` (heuristic only).

**Against the previous report (F11):** the 288 records are identical except `wall_ms`. The trace changes nothing
the planner decides. Mean regret: realistic cache £183 / 69 / 30 / 30, near-unbiased cache £188 / 36 / 30 / 30.

An example trace (open-jaw, 3-day window, budget 12, seed 0):

| # | Kind | Hub | What happened |
| --- | --- | --- | --- |
| 1-3 | search | | through tickets for the three sampled date pairs |
| | cache_bound x6 | MAD, LON, PAR, AMS, BCN | cached positioning + long-haul + 2 hotel nights, best-case score against -1689 to beat |
| | cache_bound | LIS | no cached price: searched last if budget allows |
| 4-5 | search | | open-jaw fix: LPB to LIM one-way, plus an EDI-LIM return |
| 6-8 | search | LON, BCN, MAD | long-haul from each hub, back from LPB |
| | prune x3 | PAR, AMS, LIS | search budget used up |
| 9-11 | search | LON, BCN, MAD | positioning, a night in the hub each way |

## UI
The API response changed (it gained `trace`), so I ran the stack (`FAKE_LLM=1 scripts/dev.sh`) and every frontend
spec:

| Spec | Result | Why |
| --- | --- | --- |
| form.spec.ts (F16) | fail | not built yet |
| rerank.spec.ts (F17) | fail | not built yet |
| race-trace.spec.ts (F18) | fail | not built yet |
| how-it-works.spec.ts (F19) | fail | not built yet |

e2e check: the screenshots are unchanged from F11, and so is the same hydration-mismatch console warning. The legacy
chat doesn't read the new field.

ui-evaluator verdict, verbatim:

> VERDICT: FAIL
>
> - [severity: high] desktop-results.png / mobile-results.png: Card #5's outbound route is "EDI → MAD → LIM", which includes an overnight in Madrid, yet the card calls it "non-stop · 1 night in Madrid". A user reading the stops count will be misled. The convention is also inconsistent. Card #4's outbound is "EDI → STN → MAD → LIM", with two intermediate airports, and it says "1 stop". So the stops count silently leaves out the stopover city.
> - [severity: medium] desktop-results.png / mobile-results.png: The self-transfer risk isn't stated. Cards #4 (Ryanair + Iberia) and #5 (easyJet + Air Europa) only show a neutral grey "2 tickets" pill. Nothing says "self-transfer" or explains the missed-connection risk.
> - [severity: medium] desktop-results.png / mobile-results.png: The night-arrival warning "lands between 00:00 and 06:00" doesn't say which journey it means. On #4 it applies to the outbound (LIM 05:30); on #5 it applies to both. It is also styled exactly like the neutral "2 tickets" pill, with no warning colour or icon, so it doesn't read as a warning.
> - [severity: medium] desktop-results.png / mobile-results.png: The narration says "Madrid with a night each way is the best value." The Madrid card is #5, the most expensive one visible (£1,114, +£60). Cards #1–#3 are scrolled out of view in both screenshots, so the cards can't be checked against the narration, and as shown they contradict it.
> - [severity: low] desktop-results.png: The "vs cheapest" differences don't agree with each other. "£1,068 / +£13" implies the cheapest is £1,055, while "£1,114 / +£60" implies £1,054. One of the figures is rounded differently.
> - [severity: low] desktop-empty.png / mobile-empty.png: The suggestion chips are hard-clipped at the container edge with no fade or scroll cue: "I'd happily pay £15" on desktop and "...21–24 May 2027, hom" on mobile.
> - [severity: low] desktop-results.png: The edges don't line up. The cards run from about x=258 to 907, but the composer runs from about x=232 to 968 and the header from x=232. The sticky header has no border or background break, so scrolled card content (the top "lands between..." pill) is cut off abruptly underneath it.
> - [severity: low] mobile-results.png / desktop-results.png: The red "1 Issue" dev badge (the hydration mismatch on the caret-color style) overlaps the composer textarea on mobile. The cost breakdown uses unpolished templated text: "2 hotel night(s)", "2 airport transfer(s)". The costs themselves are labelled as estimates ("est.", "~£90").

These are the same findings as at F11, about the unchanged legacy chat. My reading is the same as in the F11 report:
- "Non-stop · 1 night in Madrid" follows the model, in which planned nights aren't stops, but the label misleads.
- The narration is the scripted fake LLM's fixed text.
- The £1 difference is probably the UI rounding separately; not verified.

All of them are inputs for F16. The evaluator calls this a high-severity issue, and F16's cards should fix it by
showing planned nights and stops separately and stating the self-transfer risk.

## What changed
- `app/models.py`: `TraceEvent` (kind `cache_bound` / `prune` / `search`, hub, slices, reason, searches_used,
  bound) and `PlanResult.trace`.
- `app/providers/base.py`: `BudgetedProvider` writes a `search` event at the moment a search is charged, so events
  are numbered 1..n even with concurrent waves. Memo hits and in-flight repeats leave none. `search()` takes optional
  `reason` and `hub`.
- `app/engine/planner.py`: every search carries a plain-English reason. Each hub gets a `cache_bound` event and each
  pruning decision a `prune` event, in the order the planner makes them.
- `app/engine/llm_planner.py`: the LLM's searches are traced as "LLM search_route (call id)", and its `cached_price`
  lookups as `cache_bound` events.
- `tests/test_parallel_planner.py`: the F6 equivalence tests compare everything except the trace, because the
  frozen serial planner predates it.

## Open problems
- **Prunes are logged in decision order, not exactly when they happen.** "Search budget used up" prunes are decided
  by the budget replay after the long-haul wave, so they appear just before the positioning searches. That's a
  faithful order of decisions, but not a timestamped log.
- **The trace is in every response.** It's returned with each `/api/plan` and `/api/rerank` response, a few KB for
  a budget-30 plan. If the race (F13) returns traces for many runs, it may want a summary instead.
- **The `llm` planner's trace has no prune events,** because it never explicitly decides to drop a hub. Its
  reasoning lives in the conversation, which isn't stored yet.
