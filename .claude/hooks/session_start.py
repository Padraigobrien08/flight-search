#!/usr/bin/env python3
"""SessionStart: put the project state in front of Claude before it does anything.

Plain stdout from a SessionStart hook is added to Claude's context.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    event = json.load(sys.stdin)
    root = Path(event.get("cwd", ".")).resolve()
    while not (root / "features.json").exists() and root != root.parent:
        root = root.parent
    if not (root / "features.json").exists():
        return
    features = json.loads((root / "features.json").read_text())["features"]
    done = [f["id"] for f in features if f.get("passes")]
    todo = [f for f in features if not f.get("passes")]
    nxt = next((f for f in todo if "Padraig" not in f.get("milestone", "")), None)
    log = subprocess.run(["git", "log", "--oneline", "-5"], cwd=root, capture_output=True, text=True).stdout.strip()
    progress = (root / "PROGRESS.md").read_text().strip().splitlines() if (root / "PROGRESS.md").exists() else []

    print("## Project state (from SessionStart hook)")
    print(f"Features passing: {len(done)}/{len(features)} {done}")
    if nxt:
        print(f"Next feature for an agent: {nxt['id']} — {nxt['description']}\n  acceptance: {nxt['acceptance']}")
    print("Recent commits:\n" + log)
    if progress:
        print("Latest progress notes:\n" + "\n".join(progress[-15:]))


if __name__ == "__main__":
    main()
