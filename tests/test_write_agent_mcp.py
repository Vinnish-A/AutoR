from __future__ import annotations

import json

from autor import mcp_server
from autor.config import _build_config


def test_write_agent_mcp_preflight_returns_status(tmp_path):
    cfg = _build_config({}, tmp_path)
    cfg.ensure_dirs()

    old_cfg = mcp_server._cfg
    try:
        mcp_server._cfg = cfg
        payload = json.loads(mcp_server.write_agent_preflight("empty-ws"))
    finally:
        mcp_server._cfg = old_cfg

    assert payload["status"] == "BLOCKED_BY_MISSING_INPUT"
