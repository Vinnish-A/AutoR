#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${AUTOR_VENV:-$ROOT_DIR/.venv}"
CONFIG_FILE="${AUTOR_CONFIG:-$ROOT_DIR/config.yaml}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "autor virtual environment not found: $VENV_DIR" >&2
  exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "autor config not found: $CONFIG_FILE" >&2
  exit 1
fi

export AUTOR_ROOT="${AUTOR_ROOT:-$ROOT_DIR}"
export AUTOR_CONFIG="$CONFIG_FILE"

cd "$ROOT_DIR"
# Call the module through the environment's Python to avoid stale console-script shebangs
# after the repo or virtualenv is relocated.
exec "$VENV_DIR/bin/python" -m autor.mcp_server "$@"
