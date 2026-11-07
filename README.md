# Value-ranked flight search

Flight search ranked by what a journey is worth to *you*, not just its price. Ask for "Edinburgh to Lima in late May, home from La Paz", and it searches hubs, flexible dates and ticket structures nobody would try by hand, such as a night in Madrid on separate tickets or flying into one city and home from another. Then it ranks the options and explains the trade-offs.

Spec: [Value-ranked flight search — spec](https://claude.ai/artifact/MVm57LXnXuquYza1tEVbcG).

**The claim:** a statistical search planner beats an LLM agent at search, per search spent. The target product is a form-first demo of one trip (Edinburgh → Lima, home from La Paz) on a calibrated fare simulator, with a planner race, a search trace and live re-ranking. The roadmap is `features.json` (F1–F21), each feature with an acceptance test written before the code. What's here today is milestone 1: the heuristic planner and an early chat UI.

```
frontend/  Next.js chat UI, from the Vercel AI chatbot template, stripped to the chat
backend/   FastAPI: planner, scoring, fare providers, Claude agent, streaming /api/chat
```

The browser talks only to Next. Next proxies `/api/*` to FastAPI, which runs the agent and streams the AI SDK UI message protocol back to `useChat`.

## Run it

```bash
# backend
cd backend
cp .env.example .env          # add OPENAI_API_KEY
uv sync
uv run uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
cp .env.example .env.local
pnpm install
pnpm dev                      # http://localhost:3000
```

With `FARE_PROVIDER=fixture` (the default) everything runs offline on fares anchored to real Google Flights prices from 6 Nov 2026. Switch to `fli` (free, unofficial, prototype only) or `serpapi` (250 free searches/month) for live fares.

## How a search works

1. **Sample dates.** Searches the ends and the middle of each flexible window.
2. **Baseline.** Searches through tickets, including open-jaw when the trip ends somewhere else.
3. **Prune hubs.** Uses free cached fares (Travelpayouts) to work out the best possible score for each hub. Any hub that can't beat the baseline's *score* is never searched live.
4. **Search hubs.** For each surviving hub, searches the long-haul leg first, then positioning flights the day before and after it. A planned night in the hub replaces a same-day self-transfer.
5. **Score and rank.** Drops anything that breaks a hard limit or is worse in every way, then ranks by utility in pounds: fares + hotels + £/hour of travel + penalties for night waits, stops, tight connections and self-transfers, minus a bonus for stopovers you'd enjoy.

The LLM structures the request, records stated trade-offs with `set_preferences`, and explains the results. It never produces a price; every number comes from the tool output.

## Tests

```bash
cd backend && uv run pytest
```

The tests cover the engine, the planner on the Lima trip, the agent loop with a scripted LLM, and the streaming endpoint. The stream format was also checked against the AI SDK's own client parser (`readUIMessageStream`).

## Building it with Claude Code

The repo is set up so agent sessions can be judged by metrics and screenshots rather than by reading diffs:

| Piece | Role |
|---|---|
| `features.json` + `backend/tests/acceptance/` | Definition of done, written before the code. Sessions may only flip `passes`. |
| `.claude/hooks/protect_oracle.py` | Blocks any edit to the acceptance tests, and any `features.json` change other than `passes` |
| `.claude/hooks/stop_gate.py` | A session can't finish while unit tests fail or a feature claimed as passing fails its test |
| `.claude/hooks/session_start.py` | Puts features, recent commits and progress in context at start |
| Skills `next-feature`, `session-report`, `e2e-check` | Start-of-session routine, the report to review, the UI check with screenshots |
| Agent `ui-evaluator` | Grades screenshots in a fresh context with a rubric, so the UI isn't judged by the session that built it |

Start a session with `/next-feature`; read `reports/sessions/` and `PROGRESS.md` afterwards.

## Roadmap

See `features.json`: simulator (F1–F3), benchmark and parallel search (F4–F6), OpenAI layer, grounding check and the LLM-planner baseline (F7, F8, F10), two fare models written by hand (F9a Gaussian process, F9b hierarchical Bayesian), the demo API (F11–F15), the form-first UI (F16–F19), preference learning (F20) and deployment to Vercel and Fly.io (F21).
