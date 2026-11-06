#!/usr/bin/env bash
# Start backend (:8000) and frontend (:3000). FAKE_LLM=1 uses the scripted LLM (no API key needed).
set -euo pipefail
cd "$(dirname "$0")/.."
trap 'kill 0' EXIT
if [[ "${FAKE_LLM:-0}" == "1" ]]; then
  (cd backend && PYTHONPATH=. uv run python scripts/serve_fake.py) &
else
  (cd backend && uv run uvicorn app.main:app --port 8000) &
fi
(cd frontend && pnpm dev) &
wait
