---
name: session-report
description: End-of-session report for Padraig, who reviews metrics and screenshots instead of diffs. Use when finishing a feature or a session, or when asked for a report or status.
---

# Session report

Produce `reports/sessions/<YYYY-MM-DD>-<feature id>.md` and commit it with the work.

1. **Tests.** Unit test count and pass/fail; list of features passing (`features.json`).
2. **Metrics.** If `app.bench` exists, run
   `cd backend && uv run python -m app.bench --planners <every implemented planner> --budgets 5 10 20 30 --seeds 0 1 2 --out ../reports/latest`
   and include the ablation table from `reports/latest/bench.md` plus `reports/latest/regret.png`.
   Compare with the previous report's table: state each change in mean regret, searches and wall time. Never round a regression away.
3. **UI.** If anything under `frontend/` or the API changed: start the stack (`FAKE_LLM=1 scripts/dev.sh`), run
   `cd frontend && pnpm exec playwright test` and report pass/fail per spec (all specs, not only the current feature).
   Then run the `e2e-check` skill for screenshots, ask the `ui-evaluator` agent to grade them, and paste its verdict verbatim.
4. **What changed**, in at most five lines, and **open problems** (anything flaky, any shortcut taken, any assumption in the simulator).
5. Append a 3–6 line entry to `PROGRESS.md` and commit: `git commit -m "<feature id>: <what moved>"`.

Report facts only. A metric you didn't run is "not run", not estimated.
