# Session report: F14-parse-preferences (2026-11-08)

## Tests
- Unit tests: 143 passed, 0 failed (132 before; `tests/test_preferences_parse.py` adds 11).
- Backend acceptance: all 16 tests for F1-F8 and F10-F14 pass (`test_api.py::test_parse_preferences` is new).
- Features passing: 13/22.
- What the new tests check:
  - the cleaning rules: unknown keys dropped, wrong types dropped (including `true` where a number belongs, and
    NaN), clamping at both ends, `max_stops` rounded to a whole number, `null` treated as "not mentioned", and the
    result always a valid `Preferences` update;
  - JSON found inside code fences or chatty replies, and arrays rejected;
  - OpenAI gets strict structured output (`text.format` = `json_schema`, strict, every field nullable) plus the
    current settings, and the shared LLM object isn't changed;
  - the endpoint uses the `parse` model;
  - empty text never calls the LLM; over-long text and bad `current` values return 422; a reached spend cap returns
    503;
  - every default lies inside its bounds.

## Metrics
Not run: no planner or simulator code changed. The spec measures parsing by accuracy on a small labelled set, which
needs a real model. There's no key here, and no labelled set exists yet (see open problems).

## UI
The API changed (two new endpoints), so I ran the stack and every frontend spec:

| Spec | Result | Why |
| --- | --- | --- |
| form.spec.ts (F16) | fail | not built yet |
| rerank.spec.ts (F17) | fail | not built yet |
| race-trace.spec.ts (F18) | fail | not built yet |
| how-it-works.spec.ts (F19) | fail | not built yet |

e2e check: exit 2 on the same hydration warning as before. The screenshots are unchanged, apart from minor wrapping
of the empty-state text.

ui-evaluator verdict, verbatim:

> VERDICT: FAIL
>
> - [severity: high] desktop-results.png: The stop counts are wrong. #5 Out "EDI → MAD → LIM" says "non-stop · 1 night in Madrid", but it is two flights with an overnight in Madrid. #4 Out "EDI → STN → MAD → LIM" has two intermediate airports but says "1 stop". #4 Back "LPB → BOG → LHR → EDI" and #5 Back "LPB → BOG → MAD → EDI" also say "1 stop". mobile-results.png repeats the #5 errors.
> - [severity: high] desktop-results.png / mobile-results.png: The narration "Madrid with a night each way is the best value." contradicts the cards directly above it. Madrid is ranked #5, the lowest card shown, at "+£60 vs cheapest", below #4 London at +£13.
> - [severity: medium] desktop-results.png: The warnings are not clear enough. Both cards need "2 tickets" (separate bookings), but the only sign of that risk is a neutral grey pill, with no "self-transfer" wording. The night-arrival warning is a plain grey pill, "lands between 00:00 and 06:00", styled like a tag rather than a warning, and it doesn't say which leg. On #4 only the outbound (05:30) lands in that window; the return lands at 17:25.
> - [severity: medium] mobile-results.png: On #5 the price "£1,114" drops to its own line at an odd left offset (about x=110). It lines up with neither "#5" nor "+£60 vs cheapest" (about x=59), so the price no longer stands out first. The fixed "Out"/"Back" label column squeezes the journey text into 4-line wraps that split dates across lines ("→ Mon / 24 May", "→ Wed 9 / Jun").
> - [severity: medium] desktop-empty.png / mobile-empty.png: Suggestion chips are cut off mid-text at the container edge ("I'd happily pay £15", "home from La Paz" cut to "hom") with no fade or scroll cue. A user can't tell there is more to read, or another chip.
> - [severity: medium] desktop-results.png: The screenshot starts mid-list. Cards #1–#3, including the cheapest that the "+£X vs cheapest" figures refer to, are scrolled out of view, so the top of the ranking can't be checked. The previous card's "lands between 00:00 and 06:00" pill is clipped under the sticky header, which has no divider or shadow.
> - [severity: low] desktop-results.png: The price differences don't agree on the cheapest total. £1,068 − £13 gives £1,055, but £1,114 − £60 gives £1,054. A careful user will see the £1 mismatch.
> - [severity: low] desktop-results.png / mobile-results.png: Polish problems:
>   - The cost lines use "(s)" plurals ("2 hotel night(s)", "2 airport transfer(s)").
>   - In the results state the composer has a heavy grey double border, which looks like a default focus outline. In the empty state it has a thin one.
>   - The card column (about x=258–907) doesn't line up with the header or composer (about x=232–968).
>   - The red "1 Issue" dev badge (the hydration warning) covers the bottom-left corner of both desktop shots.

These are the same legacy-chat findings as at F11-F13, with my reading unchanged. They're inputs for F16, which
replaces this page.

## What changed
- `app/agent/preferences.py`: `parse_preferences(text, llm, current)`.
  - The prompt is built from the `Preferences` fields' own descriptions, defaults and bounds.
  - The reply is untrusted: unknown fields and wrong types are dropped, numbers are clamped to `PREFERENCE_BOUNDS`,
    and anything that isn't a JSON object changes nothing. Clamped and ignored fields are reported back.
  - The model never sees fares or itineraries; it only maps the person's words onto weights.
- `app/llm/openai_llm.py`: `with_json_schema()` returns a copy that asks for strict structured output. The parser
  uses it when the LLM offers it. The test fakes, which don't have it, get plain JSON instead.
- `app/models.py`: `PREFERENCE_BOUNDS`, the one table of valid ranges, e.g. value of an hour £0-200, stopover bonus
  -£500 to £500, max stops 0-4.
- `app/api/preferences.py`:
  - `POST /api/preferences/parse` returns `{preferences_update, clamped, ignored, note}`. A reached spend cap
    returns 503 "The sliders still work"; text is limited to 1,000 characters.
  - `GET /api/preferences/bounds` serves the same ranges, so F16's sliders and the parser can't disagree.

## Open problems
- **The bounds are my choice.** The spec only gives starting weights; the ranges above are judgement. The stopover
  bonus allows negative values (a hub night as a cost beyond the hotel). Worth a look, since F16's sliders will use
  them.
- **Accuracy isn't measured yet.** The spec's measure is "parse accuracy on a small labelled set". A dozen labelled
  sentences plus an eval script would take little time once a key is available. Not built, because it can't run
  here.
- **Relative statements depend on `current`.** "A bit more than now" only works if the frontend sends the sliders'
  current values; F16 should.
- **The strict schema is unconfirmed against the live API.** The nullable union types and the integer type for
  `max_stops` follow the Responses API's documented strict JSON-schema rules, but haven't been tried against a real
  model.
