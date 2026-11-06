# Value-ranked flight search

Portfolio piece. The claim it must prove: a small agentic loop plus a statistically modelled search
planner finds better itineraries per search than an LLM choosing searches itself. Every change should
make that claim more measurable, not just add features.

Spec: https://claude.ai/artifact/MVm57LXnXuquYza1tEVbcG

## Commands
- Backend tests: `cd backend && uv run pytest -q` (unit) · one feature: `uv run pytest -q <acceptance id from features.json>`
- Run both apps: `scripts/dev.sh` (backend :8000 with fixture fares, frontend :3000)
- UI check without an API key: the `e2e-check` skill (scripted LLM, real UI, screenshots)
- Frontend: `cd frontend && pnpm exec tsc --noEmit`, `pnpm build`

## How work is organised
- `features.json` is the definition of done. Take the next feature with `passes: false` (skip milestone 4, which is Padraig's).
  Only flip `passes` after its acceptance test passes. One feature per session.
- `backend/tests/acceptance/` is locked: hooks block edits. If a test seems wrong, stop and say so.
- End every session with the `session-report` skill. Padraig reviews reports and screenshots, not diffs.
- Commit on a branch with a message saying which feature moved. Never push to `main`.

## Invariants
- The LLM never produces a price, time or score. Numbers come from tool output; `modelView` is what the LLM sees.
- The search planner is deterministic code, not an LLM. The only LLM-driven search is the `llm` baseline planner.
- Every live search goes through `BudgetedProvider`; memoised repeats cost nothing.
- The frontend is a thin view. No business logic in TypeScript.
- `/api/chat` speaks the AI SDK UI message stream v1. The client parses chunks with strict schemas:
  extra fields break it. Check stream changes with the e2e check, not by eye.

## Gotchas
- Times from providers are local to each airport; only compare times at the same airport.
- The `fixture` provider only covers MAD, LON, PAR hubs. The simulator (F1–F3) replaces it for benchmarks.
- `fli` breaks Google's terms: prototype only, never in tests or CI.
