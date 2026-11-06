#!/usr/bin/env python3
"""PreToolUse: the session doing the work may not edit what judges it.

Blocks (exit 2):
- any edit to backend/tests/acceptance/, frontend/tests/acceptance/ or the Playwright config
- any edit to features.json that changes anything other than `passes` values
- shell commands that write to either
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ORACLE_DIRS = ("backend/tests/acceptance", "frontend/tests/acceptance", "frontend/playwright.config.ts")
FEATURES = "features.json"


def block(reason: str) -> None:
    print(f"Blocked by protect_oracle hook: {reason}. "
          "These files define done; only Padraig changes them. If a test looks wrong, stop and say so.",
          file=sys.stderr)
    sys.exit(2)


def rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root))
    except ValueError:
        return path


def strip_passes(text: str) -> str:
    return re.sub(r'"passes"\s*:\s*(true|false)', '"passes": X', text)


def main() -> None:
    event = json.load(sys.stdin)
    root = Path(event.get("cwd", ".")).resolve()
    tool, inp = event.get("tool_name", ""), event.get("tool_input", {}) or {}

    if tool == "Bash":
        cmd = inp.get("command", "")
        writes = re.search(r"(>|\btee\b|\bsed\s+-i|\brm\b|\bmv\b|\bcp\b|\btruncate\b|\bgit\s+(checkout|restore)\b)", cmd)
        if writes and (any(d in cmd for d in ORACLE_DIRS) or "acceptance/" in cmd or FEATURES in cmd):
            block(f"shell command writes to acceptance tests or {FEATURES}")
        return

    path = rel(inp.get("file_path") or inp.get("notebook_path") or "", root)
    if path.startswith(ORACLE_DIRS):
        block(f"{path} is a locked acceptance test")

    if path == FEATURES:
        current = (root / FEATURES).read_text() if (root / FEATURES).exists() else ""
        if tool == "Write":
            proposed = inp.get("content", "")
        elif tool == "Edit":
            old, new = inp.get("old_string", ""), inp.get("new_string", "")
            proposed = current.replace(old, new) if inp.get("replace_all") else current.replace(old, new, 1)
        elif tool == "MultiEdit":
            proposed = current
            for e in inp.get("edits", []):
                proposed = proposed.replace(e.get("old_string", ""), e.get("new_string", ""), 1)
        else:
            block(f"{tool} on {FEATURES}")
            return
        if strip_passes(proposed) != strip_passes(current):
            block("features.json may only change `passes` values")


if __name__ == "__main__":
    main()
