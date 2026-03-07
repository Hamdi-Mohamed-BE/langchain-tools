#!/usr/bin/env bash

# If invoked with `sh run_server.sh`, re-run under bash.
if [ -z "${BASH_VERSION:-}" ]; then
  if command -v bash >/dev/null 2>&1; then
    exec bash "$0" "$@"
  fi
  echo "This script requires bash."
  exit 1
fi

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Run: bash setup_server.sh"
  exit 1
fi

if [ ! -f ".venv/bin/python" ] && [ ! -f ".venv/Scripts/python.exe" ]; then
  echo "Virtual environment not found. Run: bash setup_server.sh"
  exit 1
fi

echo "[run] Starting FastAPI server on http://127.0.0.1:8000"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
