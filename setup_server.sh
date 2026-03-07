#!/usr/bin/env bash

# set UV_VENV_CLEAR=1
export UV_VENV_CLEAR=1

# If invoked with `sh setup_server.sh`, re-run under bash to support pipefail and arrays.
if [ -z "${BASH_VERSION:-}" ]; then
  if command -v bash >/dev/null 2>&1; then
    exec bash "$0" "$@"
  fi
  echo "This script requires bash. Please install bash and run again."
  exit 1
fi

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

log() {
  printf "\n[setup] %s\n" "$1"
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ensure_python() {
  if has_cmd python3; then
    log "python3 is already installed"
    return
  fi

  if has_cmd python; then
    log "python is already installed"
    return
  fi

  case "$(uname -s)" in
    Linux*)
      log "python not found, installing with apt (requires sudo)"
      sudo apt-get update
      sudo apt-get install -y python3 python3-venv python3-pip
      ;;
    Darwin*)
      if has_cmd brew; then
        log "python not found, installing with Homebrew"
        brew install python
      else
        echo "Homebrew is required to auto-install Python on macOS."
        echo "Install Homebrew first: https://brew.sh"
        exit 1
      fi
      ;;
    MINGW*|MSYS*|CYGWIN*)
      if has_cmd winget; then
        log "python not found, installing with winget"
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
      elif has_cmd choco; then
        log "python not found, installing with choco"
        choco install python -y
      else
        echo "Could not find winget or choco to install Python automatically on Windows."
        echo "Install Python 3.11+ and re-run this script."
        exit 1
      fi
      ;;
    *)
      echo "Unsupported OS for automatic Python installation."
      echo "Please install Python 3.11+ manually and re-run this script."
      exit 1
      ;;
  esac
}

ensure_uv() {
  if has_cmd uv; then
    log "uv is already installed"
    return
  fi

  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      if has_cmd powershell.exe; then
        log "installing uv via PowerShell installer"
        powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
        # Refresh PATH for current shell session (Git Bash)
        export PATH="$HOME/.local/bin:$PATH"
      else
        echo "PowerShell was not found; cannot install uv automatically on Windows."
        exit 1
      fi
      ;;
    *)
      log "installing uv via shell installer"
      curl -LsSf https://astral.sh/uv/install.sh | sh
      export PATH="$HOME/.local/bin:$PATH"
      ;;
  esac

  if ! has_cmd uv; then
    echo "uv installation appears incomplete."
    echo "Open a new terminal and run this script again."
    exit 1
  fi
}

bootstrap_env() {
  if [[ ! -f ".env" && -f ".env.example" ]]; then
    log "creating .env from .env.example"
    cp .env.example .env
  fi

  log "creating virtual environment via uv"
  uv venv

  log "syncing dependencies"
  uv sync
}

start_server() {
  log "starting FastAPI server on http://127.0.0.1:8000"
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
}

ensure_python
ensure_uv
bootstrap_env
start_server
