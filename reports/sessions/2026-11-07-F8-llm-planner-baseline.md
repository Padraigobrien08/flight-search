# Session report: F8-llm-planner-baseline (2026-11-07)

## Tests
- Unit tests: 102 passed, 0 failed (95 before; `tests/test_llm_planner.py` adds 7, all with scripted LLMs).
- Acceptance: all 12 backend acceptance tests for F1-F8 and F10 pass.
- Features passing: 9/22.
- What the new tests check:
  - an LLM that searches everything the exhaustive search does gets within £1 of the true optimum. Assembly covers
    the candidate space; the small gap is the top-5-per-search cap below;
  - a sensible two-search Madrid plan finds the Madrid itinerary and spends exactly 2 searches;
  - the cache and best-so-far tools return real values, and token usage sums across turns;
  - over-budget searches, bad arguments and unknown tools become tool errors, not crashes;
  - six searches in one turn run concurrently (under half the serial time at 50 ms each);
  - a runaway LLM is stopped at `max_turns`;
  - the default LLM refuses to run without a key.

## Metrics
`uv run python -m app.bench --out ../reports/latest` (heuristic only).

**Against the previous report (F6):** the 288 records are identical except `wall_ms`. Each record gains
`llm_input_tokens`, `llm_output_tokens` and `llm_turns`, all 0 for code planners. Mean regret: realistic cache
£183 / 69 / 30 / 30, near-unbiased cache £188 / 36 / 30 / 30, both unchanged.

**The `llm` planner was not benchmarked against a real model.** `api.openai.com` isn't reachable from here and
there's no key. Its first real numbers need a run on your machine (command below).

## UI
Not run: nothing under `frontend/` or the API changed.

## What changed
- `app/engine/llm_planner.py`, `llm_plan(req, prefs, live, cache, llm)`. The LLM chooses searches; code builds and
  scores the itineraries.
  - Tools:
    - `search_route`: one booking of one or two slices, so a one-way, return, open-jaw or multi-city ticket,
      through the same `BudgetedProvider` (repeats are free);
    - `cached_price`: the same free cache the code planners get;
    - `best_so_far`: free, the top 3 itineraries its tickets allow so far.

    Tool calls in one turn run concurrently.
  - Its task prompt carries the same knowledge the code planners have: the trip, the hubs and their airports, which
    ticket structures count, the preferences and the utility formula, and the budget. It isn't told any search
    strategy.
  - When it stops, every itinerary in the candidate space buildable from its tickets is scored with the same
    utility. So the LLM never produces a price or score, and its regret is exact.
- `app/engine/space.py`: the candidate space, moved from `app/sim/exhaustive.py` so a planner doesn't import the
  simulator. No behaviour change.
- `run_benchmark(..., llm_factory=...)`: a zero-argument factory, called once per run so no state carries over.
  The default is the `baseline` role from settings.
- `python -m app.bench` runs code planners by default. `llm` runs only when named, because it makes real API calls.
- Small changes: `BenchTrip` exposes its request's fields (F8's test reads `trip.origin`), `PlanResult.llm_usage`,
  `BudgetedProvider.memoised()`.

To get the first real numbers (makes real API calls, inside the spend cap):

```bash
cd backend && OPENAI_API_KEY=... uv run python -m app.bench --planners heuristic llm --budgets 5 10 20 --seeds 0 --trips 2 --cache realistic --out ../reports/llm-trial
```

## Open problems
- **Cost is unknown until a real run.** It's one LLM conversation per (trip, seed, budget, cache). The full default
  grid is 12 x 3 x 4 x 2 = 288 conversations at `gpt-6-astra` prices, likely tens of dollars, more than the $20 cap.
  When the cap is hit mid-run the benchmark stops with `SpendCapReached`. Suggest a smaller grid for `llm` (one
  cache setting, budgets 5/10/20, a few trips) or a recorded replay, which F13 needs anyway.
- **Both planners see only the top 5 tickets per search.** The exhaustive optimum sees every ticket, so a few pounds
  of regret can be unreachable for any planner. This applies equally to all planners.
- **The prompt is a fairness surface.** It states the structures and hubs, which the heuristic's code knows too. It
  should be reviewed once real transcripts exist, to check the LLM isn't confused rather than outplayed. Transcripts
  aren't saved yet; F12/F13 (trace, race) are the natural place.
- **Not yet checked against a real model:** the reasoning carry-over between turns and real tool-call behaviour.
