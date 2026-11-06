#!/usr/bin/env python3
"""Stop: a session can't finish while anything it claims is broken.

Runs the unit tests, every acceptance test whose feature has passes=true, and
the frontend type-check when frontend files changed. Exit 2 keeps Claude
working and feeds it the failures. If the gate already fired once this stop
(stop_hook_active), it lets the session end but warns the user instead of
looping forever.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path, timeout: int = 540) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"{' '.join(cmd)}: {e}"
    out = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode == 0, "\n".join(out[-25:])


def main() -> None:
    event = json.load(sys.stdin)
    root = Path(event.get("cwd", ".")).resolve()
    while not (root / "features.json").exists() and root != root.parent:
        root = root.parent
    backend, frontend = root / "backend", root / "frontend"

    failures: list[str] = []
    ok, out = run(["uv", "run", "pytest", "-q", "-x"], backend)
    if not ok:
        failures.append(f"Unit tests failing:\n{out}")

    features = json.loads((root / "features.json").read_text())["features"]
    # Frontend specs need a running stack; the session-report skill runs those.
    claimed = [f["acceptance"] for f in features if f.get("passes") and f["acceptance"].startswith("tests/")]
    if claimed:
        ok, out = run(["uv", "run", "pytest", "-q", *claimed], backend)
        if not ok:
            failures.append(f"Features marked passes=true are failing their acceptance tests:\n{out}")

    changed = subprocess.run(["git", "status", "--porcelain", "--", "frontend"], cwd=root,
                             capture_output=True, text=True).stdout.strip()
    if changed and (frontend / "node_modules").exists():
        ok, out = run(["pnpm", "exec", "tsc", "--noEmit"], frontend)
        if not ok:
            failures.append(f"Frontend type errors:\n{out}")

    if not failures:
        return
    report = "\n\n".join(failures)
    if event.get("stop_hook_active"):
        print(json.dumps({"systemMessage": f"Stop gate still failing after a retry:\n{report[:1500]}"}))
        return
    print(f"Stop gate: fix these before finishing (or set the feature back to passes=false and say why).\n\n{report}",
          file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
