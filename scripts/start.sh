#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${AUTOR_RUN_DIR:-$ROOT_DIR/.run}"
VENV_DIR="${AUTOR_VENV:-$ROOT_DIR/.venv}"
MINERU_PORT="${AUTOR_MINERU_PORT:-8000}"
AUTODOWNLOAD_PORT="${AUTOR_AUTODOWNLOAD_PORT:-8001}"
MINERU_PID_FILE="$RUN_DIR/mineru.pid"
MINERU_LOG_FILE="$RUN_DIR/mineru.log"
MINERU_MODULE="mineru.cli.fast_api"

mkdir -p "$RUN_DIR"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "autor virtual environment not found: $VENV_DIR" >&2
  exit 1
fi

export AUTOR_ROOT="${AUTOR_ROOT:-$ROOT_DIR}"

port_open() {
  local port="$1"
  "$VENV_DIR/bin/python" - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.5)
    ok = sock.connect_ex(("127.0.0.1", port)) == 0
raise SystemExit(0 if ok else 1)
PY
}

wait_for_port() {
  local port="$1"
  local name="$2"
  local retries="${3:-40}"
  local sleep_seconds="${4:-1}"

  for ((i = 0; i < retries; i += 1)); do
    if port_open "$port"; then
      echo "$name is ready: 127.0.0.1:$port"
      return 0
    fi
    sleep "$sleep_seconds"
  done

  echo "$name timed out while starting: 127.0.0.1:$port" >&2
  return 1
}

resolve_windows_shell() {
  if [[ -n "${AUTOR_WINDOWS_POWERSHELL:-}" ]]; then
    echo "$AUTOR_WINDOWS_POWERSHELL"
    return 0
  fi

  if command -v powershell.exe >/dev/null 2>&1; then
    command -v powershell.exe
    return 0
  fi

  if command -v pwsh.exe >/dev/null 2>&1; then
    command -v pwsh.exe
    return 0
  fi

  local candidates=(
    "/mnt/c/Program Files/PowerShell/7/pwsh.exe"
    "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

start_mineru() {
  if port_open "$MINERU_PORT"; then
    echo "MinerU is already running: 127.0.0.1:$MINERU_PORT"
    return 0
  fi

  if ! "$VENV_DIR/bin/python" -c "import $MINERU_MODULE" >/dev/null 2>&1; then
    echo "MinerU module not importable in $VENV_DIR: $MINERU_MODULE" >&2
    return 1
  fi

  echo "Starting local MinerU service..."
  nohup env \
    MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-modelscope}" \
    "$VENV_DIR/bin/python" \
    -m "$MINERU_MODULE" \
    --host 127.0.0.1 \
    --port "$MINERU_PORT" \
    >"$MINERU_LOG_FILE" 2>&1 &

  local pid=$!
  echo "$pid" >"$MINERU_PID_FILE"

  sleep 1
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "MinerU exited before becoming ready. Check $MINERU_LOG_FILE for details." >&2
    tail -n 20 "$MINERU_LOG_FILE" >&2 || true
    return 1
  fi

  wait_for_port "$MINERU_PORT" "MinerU"
}

start_autodownload() {
  if port_open "$AUTODOWNLOAD_PORT"; then
    echo "Records service is already running: 127.0.0.1:$AUTODOWNLOAD_PORT"
    return 0
  fi

  local windows_shell
  windows_shell="$(resolve_windows_shell)" || {
    echo "No usable Windows PowerShell was found. Set AUTOR_WINDOWS_POWERSHELL and retry." >&2
    return 1
  }

  local win_script
  win_script="$(wslpath -w "$ROOT_DIR/scripts/windows/start.ps1")"

  echo "Starting the Records service on Windows..."
  "$windows_shell" \
    -NoProfile \
    -ExecutionPolicy Bypass \
    -File "$win_script"

  wait_for_port "$AUTODOWNLOAD_PORT" "Records service"
}

echo "Using virtual environment: $VENV_DIR"
start_mineru
start_autodownload

cat <<EOF
Services are up.

- MinerU:        http://127.0.0.1:$MINERU_PORT
- Records API:   http://127.0.0.1:$AUTODOWNLOAD_PORT

Notes:
- MCP is not started as a background service; it uses stdio transport and should be launched by the client on demand.
- The recommended launcher for MCP clients is: scripts/run-mcp.sh
EOF
