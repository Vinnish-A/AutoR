#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${AUTOR_RUN_DIR:-$ROOT_DIR/.run}"
VENV_DIR="${AUTOR_VENV:-$ROOT_DIR/.venv}"
MINERU_PORT="${AUTOR_MINERU_PORT:-8000}"
AUTODOWNLOAD_PORT="${AUTOR_AUTODOWNLOAD_PORT:-8001}"
MINERU_PID_FILE="$RUN_DIR/mineru.pid"
MINERU_LOG_FILE="$RUN_DIR/mineru.log"

mkdir -p "$RUN_DIR"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "未找到 autor 虚拟环境: $VENV_DIR" >&2
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
      echo "$name 已就绪: 127.0.0.1:$port"
      return 0
    fi
    sleep "$sleep_seconds"
  done

  echo "$name 启动超时: 127.0.0.1:$port" >&2
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
    echo "MinerU 已在运行: 127.0.0.1:$MINERU_PORT"
    return 0
  fi

  echo "启动 MinerU 本地服务..."
  nohup env \
    MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-modelscope}" \
    "$VENV_DIR/bin/mineru-api" \
    --host 127.0.0.1 \
    --port "$MINERU_PORT" \
    >"$MINERU_LOG_FILE" 2>&1 &

  local pid=$!
  echo "$pid" >"$MINERU_PID_FILE"
  wait_for_port "$MINERU_PORT" "MinerU"
}

start_autodownload() {
  if port_open "$AUTODOWNLOAD_PORT"; then
    echo "AutoDownload 已在运行: 127.0.0.1:$AUTODOWNLOAD_PORT"
    return 0
  fi

  local windows_shell
  windows_shell="$(resolve_windows_shell)" || {
    echo "未找到可用的 Windows PowerShell，可设置 AUTOR_WINDOWS_POWERSHELL 后重试。" >&2
    return 1
  }

  local win_script
  win_script="$(wslpath -w "$ROOT_DIR/scripts/windows/start.ps1")"

  echo "启动 Windows 侧 AutoDownload..."
  "$windows_shell" \
    -NoProfile \
    -ExecutionPolicy Bypass \
    -File "$win_script"

  wait_for_port "$AUTODOWNLOAD_PORT" "AutoDownload"
}

echo "使用虚拟环境: $VENV_DIR"
start_mineru
start_autodownload

cat <<EOF
服务已启动。

- MinerU:        http://127.0.0.1:$MINERU_PORT
- AutoDownload:  http://127.0.0.1:$AUTODOWNLOAD_PORT

说明:
- MCP 不作为后台服务启动；它使用 stdio 传输，应由客户端按需拉起。
- 供 MCP 客户端调用的启动命令见: scripts/run-mcp.sh
EOF