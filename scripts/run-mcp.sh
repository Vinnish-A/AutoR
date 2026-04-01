#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${AUTOR_VENV:-$ROOT_DIR/.venv}"
CONFIG_FILE="${AUTOR_CONFIG:-$ROOT_DIR/config.yaml}"

if [[ ! -x "$VENV_DIR/bin/autor-mcp" ]]; then
  echo "未找到 autor-mcp: $VENV_DIR/bin/autor-mcp" >&2
  exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "未找到 autor 配置: $CONFIG_FILE" >&2
  exit 1
fi

export AUTOR_ROOT="${AUTOR_ROOT:-$ROOT_DIR}"
export AUTOR_CONFIG="$CONFIG_FILE"

cd "$ROOT_DIR"
exec "$VENV_DIR/bin/autor-mcp" "$@"