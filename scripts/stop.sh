#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${AUTOR_RUN_DIR:-$ROOT_DIR/.run}"
VENV_DIR="${AUTOR_VENV:-$ROOT_DIR/.venv}"
MINERU_PORT="${AUTOR_MINERU_PORT:-8000}"
AUTODOWNLOAD_PORT="${AUTOR_AUTODOWNLOAD_PORT:-8001}"
MINERU_PID_FILE="$RUN_DIR/mineru.pid"

port_open() {
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    return 1
  fi

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

stop_mineru() {
  local stopped=0

  if [[ -f "$MINERU_PID_FILE" ]]; then
    local pid
    pid="$(cat "$MINERU_PID_FILE")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "Stopping MinerU (PID $pid)..."
      kill "$pid"
      stopped=1
    fi
    rm -f "$MINERU_PID_FILE"
  fi

  if port_open "$MINERU_PORT"; then
    echo "Cleaning up a leftover MinerU process..."
    pkill -f "mineru-api --host 127.0.0.1 --port $MINERU_PORT" || true
    pkill -f "mineru.cli.fast_api --host 127.0.0.1 --port $MINERU_PORT" || true
    stopped=1
  fi

  if [[ "$stopped" -eq 0 ]]; then
    echo "MinerU is not running."
  fi
}

stop_autodownload() {
  local windows_shell
  windows_shell="$(resolve_windows_shell)" || {
    echo "No usable Windows PowerShell was found. Skipping the Records shutdown step." >&2
    return 0
  }

  local win_script
  win_script="$(wslpath -w "$ROOT_DIR/scripts/windows/stop.ps1")"

  echo "Stopping the Records service on Windows..."
  "$windows_shell" \
    -NoProfile \
    -ExecutionPolicy Bypass \
    -File "$win_script"

  if port_open "$AUTODOWNLOAD_PORT"; then
    echo "The Records service port is still listening: 127.0.0.1:$AUTODOWNLOAD_PORT" >&2
    return 1
  fi

  echo "The Records service has stopped."
}

stop_mineru
stop_autodownload

echo "Note: MCP uses stdio transport and is not managed by stop.sh."
