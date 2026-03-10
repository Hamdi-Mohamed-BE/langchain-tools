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

detect_local_ip() {
  if command -v ip >/dev/null 2>&1; then
    ip route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i=="src") {print $(i+1); exit}}'
    return
  fi

  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}'
    return
  fi
}

prompt_server_host() {
  local default_host="$1"
  local input_host=""

  if [ -n "${SERVER_HOST:-}" ]; then
    return
  fi

  if [ -t 0 ]; then
    read -r -p "[run] Enter server host IP (default: ${default_host}): " input_host
  fi

  if [ -n "$input_host" ]; then
    SERVER_HOST="$input_host"
  else
    SERVER_HOST="$default_host"
  fi
}

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Run: bash setup_server.sh"
  exit 1
fi

if [ ! -f ".venv/bin/python" ] && [ ! -f ".venv/Scripts/python.exe" ]; then
  echo "Virtual environment not found. Run: bash setup_server.sh"
  exit 1
fi

SERVER_HOST="${SERVER_HOST:-}"
DETECTED_HOST="$(detect_local_ip || true)"

if [ -z "$DETECTED_HOST" ]; then
  DETECTED_HOST="127.0.0.1"
  echo "[run] Could not detect LAN IP; defaulting to $DETECTED_HOST"
fi

prompt_server_host "$DETECTED_HOST"

echo "[run] Starting FastAPI server on http://$SERVER_HOST:8000"
uv run uvicorn app.main:app --host "$SERVER_HOST" --port 8000 --reload
