# Session report: F11-api-plan-rerank (2026-11-07)

## Tests
- Unit tests: 108 passed, 0 failed (102 before; `tests/test_api_plans.py` adds 6).
- Backend acceptance: all 13 tests for F1-F8, F10 and F11 pass (`test_api.py::test_plan_and_rerank` is new).
- Features passing: 10/22.
- What the new tests check:
  - a rerank with the plan's own preferences reproduces the plan exactly;
  - an expensive hotel night (£600, no stopover bonus) puts a through ticket on top, with the stays repriced at £600
    a night;
  - a rerank never touches the fare source (search and cache are patched to raise);
  - partial preferences merge over the plan's own;
  - an unknown `plan_id` returns 404, bad preferences 422;
  - the store evicts the least recently used plan.

## Metrics
Not run: no planner or simulator behaviour changed. The heuristic's results are unchanged; the F6 equivalence tests
and the F1-F8 acceptance tests still pass after the `reprice()` refactor.

| Request (simulator, seed 0, open-jaw) | Searches | Candidates | Plan time | Rerank time |
| --- | --- | --- | --- | --- |
| 4 x 4-day window, budget 20 | 16 | 31 | 101 ms | 4-5 ms |
| 7 x 7-day window, budget 30 | 16 | 31 | 125 ms | 5 ms |

The acceptance test's own check (stopover bonus 0 -> 400 puts a stopover first) is weak on this data: the heuristic's
top result is already a stopover at bonus 0, because it only builds hub itineraries with planned nights. The hotel
test above is the one that shows reranking reorders.

## UI
The API changed, so I started the stack (`FAKE_LLM=1 scripts/dev.sh`) and ran every frontend spec
(`pnpm exec playwright test`):

| Spec | Result | Why |
| --- | --- | --- |
| form.spec.ts (F16) | fail | not built yet: `run-search` doesn't exist |
| rerank.spec.ts (F17) | fail | not built yet: timed out waiting for `run-search` |
| race-trace.spec.ts (F18) | fail | not built yet |
| how-it-works.spec.ts (F19) | fail | not built yet |

e2e check (`node scripts/e2e.mjs reports/screens`): the legacy chat still runs end to end on desktop and mobile. The
script exited with code 2 because of one console warning, a React hydration mismatch: an inline
`caret-color: transparent` style on the file input and the textarea is on the client but not in the server HTML.
Nothing in the app source sets that style, and this feature changed no frontend code. I haven't found where it comes
from.

ui-evaluator verdict, verbatim:

> VERDICT: FAIL
>
> - [severity: high] desktop-results.png / mobile-results.png: The stop counts are wrong. In card #5, Out reads "EDI → MAD → LIM · … · non-stop · 1 night in Madrid": a 2-ticket journey with an overnight in Madrid is labelled non-stop. Card #4 Out "EDI → STN → MAD → LIM" and Back "LPB → BOG → LHR → EDI" each pass through two intermediate airports but say "1 stop". Card #5 Back "LPB → BOG → MAD → EDI" has the same problem. The stops field can't be trusted.
> - [severity: high] desktop-results.png / mobile-results.png: The narration under the cards says "Madrid with a night each way is the best value.", but the Madrid itinerary is ranked #5, the last and most expensive card shown (£1,114, +£60). The summary contradicts the ranking it sits under.
> - [severity: medium] desktop-results.png: The "vs cheapest" figures disagree with each other. #4 is £1,068 at "+£13 vs cheapest", which implies a cheapest of £1,055. #5 is £1,114 at "+£60 vs cheapest", which implies £1,054.
> - [severity: medium] desktop-results.png / mobile-results.png: Warnings are weak. "2 tickets" is a neutral grey pill, and nothing says "self-transfer" or warns about a missed-connection or baggage re-check. "lands between 00:00 and 06:00" is also a plain grey pill that doesn't say which leg or airport it applies to (on #4 only the outbound lands at night, 05:30).
> - [severity: medium] desktop-results.png / mobile-results.png: Both screenshots are scrolled to cards #4–#5, and the top card is clipped under the header (only a partial "lands between 00:00 and 06:00" pill shows). Cards #1–#3, including the cheapest one, aren't captured, so I can't check correctness for the top-ranked results.
> - [severity: medium] desktop-empty.png / mobile-empty.png: The suggestion chips are cut off mid-word at the container edge ("I'd happily pay £15", "…home from La Paz the week of 6 June" on desktop, "…May 2027, hom" on mobile), with no fade or scroll cue.
> - [severity: low] mobile-results.png / desktop-results.png: The red "1 Issue" dev badge sits on top of the textarea's bottom-left on mobile. The textarea also shows a heavy dark double-border focus ring that looks like a browser default rather than styled focus.
> - [severity: low] desktop-results.png / mobile-results.png: Pluralisation is raw: "2 hotel night(s)", "2 airport transfer(s)". Alignment is inconsistent: on desktop the cards are indented (x≈258) from the header and input (x≈232). On mobile the cards are inset about 42px against the input's 16px, which squeezes each journey line onto 3–4 wrapped lines ("14h45 / travelling · non-stop · 1 / night in Madrid").
>
> You said this is the unchanged legacy chat page, but the verdict stands: the high-severity problems are in data coming from the backend (stop counts, vs-cheapest figures, narration), not just in the old UI. Hotel and transfer costs are labelled as estimates ("est.", "~£90"), so they aren't a finding.

My reading of the high-severity findings, checked against the code:
- **"Non-stop · 1 night in Madrid".** This matches the data model: `Journey.stops` deliberately leaves out planned
  hub nights (`app/models.py`). The numbers are right, but the label misleads, because a night in Madrid on separate
  tickets reads as "non-stop". F16's cards should show stops and planned nights distinctly, e.g. "1 night in Madrid,
  then non-stop".
- **The narration contradicting the ranking.** The text comes from the scripted fake LLM, which always says "Madrid
  with a night each way is the best value". The finding is still worth acting on for F15: the F7 grounding check
  only covers numbers, so a wrong claim with no number in it ("best value") passes.
- **"vs cheapest" off by £1.** Most likely the legacy UI rounds the total and the difference separately; I haven't
  verified this. F16 should show rounded figures that agree with each other.
- **The other findings** (weak self-transfer warning, clipped chips, layout, pluralisation) are about the legacy
  chat UI, which F16 replaces. I'm listing them as inputs for F16.

None of these come from F11's code: the e2e stack runs the legacy chat on fixture fares, and F11 added endpoints the
chat doesn't call.

## What changed
- `app/api/plans.py`:
  - `POST /api/plan` runs the planner and returns the full `PlanResult`, plus a `plan_id` and `stats` (searches,
    candidates, feasible count, elapsed ms). It keeps every itinerary the planner assembled in memory, for the 200
    most recent plans.
  - `POST /api/rerank` re-scores that plan's itineraries for new preferences. It does no searching and calls no LLM.
  - Preferences are partial in both. A rerank's missing fields default to the plan's own preferences.
- `app/engine/planner.py`: the hotel-and-transfer cost is now `reprice()`, so a rerank with a new hotel price reprices
  stays. `PlanResult.candidates` holds every assembled itinerary and is excluded from JSON. The `llm` planner fills
  it too.
- `fare_provider="simulator"`: `FareSimulator` serves both live fares and the cache, with a new `SIM_SEED` setting.
- `main.py`: the old `/api/plan` is replaced by the router. Nothing in the frontend called it.
- `.gitignore`: `reports/playwright/` (Playwright failure output).

## Open problems
- **Stored plans live in one process.** They disappear on restart and aren't shared between machines. That's fine
  for one Fly machine; a frontend holding an expired `plan_id` gets a 404 and must plan again.
- **Reranking only reorders what the planner found.** Search was guided by the preferences given at plan time. A big
  slider change (e.g. stopover bonus from 0 to 400) can only reorder those candidates, not search hubs the first
  plan pruned. The UI should say so, or offer "search again with these preferences".
- **The hydration warning is unexplained,** and it makes `e2e.mjs` exit 2 on every run. Worth a look before F16
  relies on that script.
