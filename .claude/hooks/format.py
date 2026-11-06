#!/usr/bin/env python3
"""PostToolUse: format the file that was just edited. Never blocks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    event = json.load(sys.stdin)
    path = Path((event.get("tool_input") or {}).get("file_path", ""))
    if not path.is_file():
        return
    root = Path(event.get("cwd", ".")).resolve()
    while not (root / "features.json").exists() and root != root.parent:
        root = root.parent
    try:
        if path.suffix == ".py" and "backend" in path.parts:
            subprocess.run(["uv", "run", "ruff", "format", "-q", str(path)], cwd=root / "backend", timeout=60)
            subprocess.run(["uv", "run", "ruff", "check", "-q", "--fix", str(path)], cwd=root / "backend", timeout=60)
        elif path.suffix in {".ts", ".tsx"} and "frontend" in path.parts:
            subprocess.run(["pnpm", "exec", "biome", "format", "--write", str(path)], cwd=root / "frontend",
                           capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass


if __name__ == "__main__":
    main()
