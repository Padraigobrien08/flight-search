# Value-ranked flight search

Portfolio piece. The claim it must prove: **a statistical search planner beats an LLM agent at search, per
search spent.** The LLM is used only where language helps: parsing stated preferences, narrating trade-offs,
and as the (strongest possible) baseline planner. Every change should make that claim more measurable.

Spec: https://claude.ai/artifact/MVm57LXnXuquYza1tEVbcG

## The product
A hosted demo of one trip done properly: Edinburgh -> Lima, home from La Paz. Form-first: dates, flexibility,
search budget, preference sliders and one free-text preference box. Fares come from a simulator calibrated to
real prices (known optimum, exact regret). Panels: trade-off cards, search trace, planner race (recorded
replay + rate-limited live run), slider re-ranking. Plus a /how-it-works page, README and a Substack post.

## Commands
- Backend tests: `cd backend && uv run pytest -q` (unit) · one feature: `uv run pytest -q <acceptance id>`
- Run both apps: `scripts/dev.sh` (`FAKE_LLM=1` for no API key)
- Frontend acceptance specs: stack running, then `cd frontend && pnpm exec playwright test`
- Frontend checks: `cd frontend && pnpm exec tsc --noEmit`, `pnpm build`

## How work is organised
- `features.json` is the definition of done. Take the first `passes: false`, skipping milestone 4 (Padraig writes
  the fare models). One feature per session. Flip `passes` only after its acceptance test passes.
- `backend/tests/acceptance/`, `frontend/tests/acceptance/` and `frontend/playwright.config.ts` are locked by hooks.
  If a test seems wrong, stop and say so.
- End every session with the `session-report` skill. Padraig reviews reports and screenshots, not diffs.
- Commit on a branch; never push to `main`.

## Invariants
- The LLM never produces a price, time or score. Numbers come from planner output and pass the grounding check.
- Planners are deterministic code with the signature of `plan()`. The only LLM-driven search is the `llm` baseline,
  which gets the strongest model, the same cached-fare tool and the same budget. Don't weaken it.
- Every live search goes through `BudgetedProvider`; memoised repeats cost nothing.
- LLM calls go through `app/llm/` (OpenAI, model chosen per role, spend guard). Nothing else imports a vendor SDK.
- The frontend is a thin view: no scoring or ranking in TypeScript; sliders call `/api/rerank`.
- UI elements the specs use are addressed by `data-testid`; keep them stable.

## Gotchas
- Provider times are local to each airport; only compare times at the same airport.
- The `fixture` provider is legacy (MAD, LON, PAR only); the simulator replaces it.
- `fli` breaks Google's terms: never in tests, CI or the hosted demo.
- The Anthropic-based chat loop (`app/agent/`, `/api/chat`) predates the form-first design; F10 moves the LLM
  layer to OpenAI and F11–F15 replace the chat endpoint with plain API calls.
