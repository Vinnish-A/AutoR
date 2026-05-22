from __future__ import annotations

import json
from argparse import Namespace

from autor import cli
from autor.config import _build_config


def test_write_agent_cli_preflight_outputs_json(tmp_path, monkeypatch):
    cfg = _build_config({}, tmp_path)
    cfg.ensure_dirs()
    messages: list[str] = []
    monkeypatch.setattr(cli, "ui", messages.append)

    cli.cmd_write_agent(Namespace(write_agent_action="preflight", workspace="empty-ws"), cfg)

    payload = json.loads(messages[-1])
    assert payload["status"] == "BLOCKED_BY_MISSING_INPUT"
    assert payload["failed_stage"] == "preflight"
