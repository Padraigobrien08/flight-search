---
name: next-feature
description: Start-of-session routine for building this repo. Use at the start of any coding session, or when asked to "work on the next feature" or continue the build.
---

# Next feature

One feature per session. The order matters because each step guards the next.

1. **Get bearings.** Read the SessionStart summary, `PROGRESS.md`, and `git log --oneline -10`. Confirm the branch is not `main`.
2. **Check the baseline still holds.** Run `cd backend && uv run pytest -q` and every acceptance test for features already marked `passes: true`. If anything is red, fixing it *is* this session's feature.
3. **Pick the feature.** First `passes: false` in `features.json`, skipping milestone 4 (Padraig writes the fare model). Read its acceptance test before any code: the test fixes the interface.
4. **Plan briefly.** State the files you'll touch and how you'll know it works. If the acceptance test seems wrong or underspecified, stop and say so; never edit it.
5. **Build it.** Small commits. Run the acceptance test often: `uv run pytest -q <acceptance id>`.
6. **Flip `passes` to true** only when the acceptance test and unit tests pass. Change nothing else in `features.json`.
7. **Finish with the `session-report` skill.**

Keep invariants from `CLAUDE.md`: no numbers from the LLM, deterministic planner, all searches through `BudgetedProvider`.
