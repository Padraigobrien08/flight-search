# Progress log

Newest last. Each session appends 3–6 lines: feature, what changed, metric deltas, open problems.

## 2026-11-06 — scaffold
- Milestone 1 heuristic planner, fixture fares, Claude loop with three tools, AI SDK stream, chat UI.
- 13 unit tests pass. Stream validated with the AI SDK client parser.
- Harness added: features.json (F1–F9), locked acceptance tests, hooks, skills, ui-evaluator agent.
- Next: F1 simulator.

## 2026-11-06 — scope settled
- Product is now form-first for the Lima scenario; LLM only for preference parsing, narration and the baseline planner.
- LLM vendor: OpenAI, model per role. Hosting: Vercel + Fly.io. Simulator instead of real snapshots.
- features.json extended to F21 with acceptance tests written first (backend pytest + frontend Playwright specs).
- Next: F1 simulator.
