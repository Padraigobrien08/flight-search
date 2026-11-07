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

## 2026-11-07 — F2-sim-structure
- NETWORK.md first (seven stated reasons), then `network.py` (32 services, sourced anchors) and `prices.py` (SimConfig).
- Calibrated: £763/£911/£920 against the spec's £762/£911/£915; anchors within 3%; 3-day shift median £15.
- Cache = lowest of 4 stale observations: 6-7% optimistic on legacy long-haul, 25% on BCN; UNBIASED_CACHE about 0%.
- 22 unit tests pass; F1 and F2 acceptance green.
- Baseline change (Padraig: fix it): open-jaw bound now gets the 0.8 multi-city discount (was 12-15% high).
  Budget-10 mean best utility -1503 -> -1522 (2/10 seeds search a different hub first); budgets 20/30 unchanged. 25 tests.

## 2026-11-07 — F3-ground-truth
- `app/sim/exhaustive.py`: candidate space that contains everything plan() builds; optimum = best feasible utility.
- 41 unit tests pass; 16 check plan() stays inside the space and never beats the optimum (3 seeds x 5 cases).
- NETWORK.md claims 1, 2 (on fares), 4, 5, 7 hold against the optimum (`python -m app.sim.claims`).
- Heuristic regret preview, open-jaw Lima: £254 / 107 / 68 / 68 at budgets 5 / 10 / 20 / 30; it plateaus at 16 searches.
- Next: F4 benchmark (compute each optimum once per trip x seed x preferences).

## 2026-11-07 — F4-benchmark-run
- `app/bench/`: BENCHMARK_TRIPS (12 Lima variants) and run_benchmark; optimum computed once per trip x seed.
- Heuristic, 12 trips x 3 seeds: mean regret £183 / 69 / 30 / 30 at budgets 5 / 10 / 20 / 30; it plateaus at ~16 searches.
- Unbiased cache: £188 / 36 / 30 / 30 (the realistic cache's optimism costs £33 at budget 10). 0 misses, no negative regret.
- 45 unit tests pass; F1-F4 acceptance green. Next: F5 CLI report (bench.json, bench.md, regret.png).

## 2026-11-07 — F5-benchmark-report
- `python -m app.bench` writes bench.json, bench.md (ablation tables, misses in cell) and regret.png (panel per cache).
- reports/latest: heuristic £183 / 69 / 30 / 30 realistic, £188 / 36 / 30 / 30 unbiased; identical to F4; 56 s for both.
- Chart: reference palette, fixed colour per planner, direct end labels spread apart; checked with a 4-planner layout render.
- 48 unit tests pass; F1-F5 acceptance green. matplotlib added. Next: F6 parallel planner.

## 2026-11-07 — F6-parallel-planner
- plan() searches in 3 concurrent waves; it replays the serial budget rules so PlanResult is unchanged.
- BudgetedProvider shares in-flight searches; SimConfig.latency_s added.
- Acceptance scenario: 870 ms serial -> 214 ms concurrent, 16 searches. Benchmark records identical to F5 except wall_ms.
- 64 unit tests pass (16 equivalence tests against a frozen serial planner); F1-F6 acceptance green.
- Next: F10 OpenAI layer (milestone 3 runs F10, F7, F8 in features.json order).

## 2026-11-07 — F10-openai-layer
- app/llm/: Responses API adapter, per-role models, SpendGuard (monthly, ledger, fails closed on unpriced models).
- Reasoning items carried through history (encrypted, store=False) so the llm baseline isn't weakened.
- Defaults: gpt-6-astra for all roles (only near-official price found; openai.com blocked here), $20/month cap.
- 73 unit tests pass; F1-F6 + F10 acceptance green. Anthropic SDK removed.
- Open: Padraig to confirm models and prices; F8 needs BenchTrip.origin etc. Next: F7 grounding check.

## 2026-11-07 — F7-grounding-check
- app/agent/grounding.py: unsupported_numbers; claims are numbers with a currency or duration unit.
- Support is typed by JSON key (money vs hours/minutes), so counts can't vouch for prices or durations.
- 95 unit tests pass (22 new, incl. sentences built from a real PlanResult); F1-F7 + F10 acceptance green.
- Open: times of day and scores are not checked yet; derived differences are flagged by design. Next: F8 llm baseline.

## 2026-11-07 — F8-llm-planner-baseline
- app/engine/llm_planner.py: LLM picks searches (search_route, cached_price, best_so_far); code assembles and scores.
- Candidate space moved to app/engine/space.py; run_benchmark takes llm_factory; CLI runs `llm` only when named.
- 102 unit tests pass; F1-F8 + F10 acceptance green. Heuristic benchmark records unchanged.
- Not yet run against a real model (no key, api.openai.com blocked here). Full llm grid likely exceeds the $20 cap.
- Next: F11 /api/plan + /api/rerank (F9a/F9b are Padraig's).
- Next: F3 exhaustive optimum, which also checks NETWORK.md #1 and #4.
