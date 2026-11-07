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

## 2026-11-07 — F1-sim-determinism
- `app/sim/FareSimulator(seed)`: live `search()` + cached `lowest_price()`; sha256-keyed draws, independent of call order.
- Prices = fixture anchors x 0.8 multi-slice x lognormal noise; cache = cheapest level x noise. No weekday/date effect yet.
- 17 unit tests pass (+4); F1 acceptance green. Heuristic plan() runs on the sim within budget.
- Open: network still borrowed from fixture.py private helpers; protect_oracle hook flags `2>&1` and `<email>` as writes.
- Next: F2 hierarchical price model.
