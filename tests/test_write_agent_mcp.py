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


def test_write_agent_mcp_polish_missing_write_returns_status(tmp_path):
    cfg = _build_config({}, tmp_path)
    cfg.ensure_dirs()
    (tmp_path / "workspace" / "empty-ws").mkdir()

    old_cfg = mcp_server._cfg
    try:
        mcp_server._cfg = cfg
        payload = json.loads(mcp_server.write_agent_polish("empty-ws"))
    finally:
        mcp_server._cfg = old_cfg

    assert payload["status"] == "BLOCKED_BY_MISSING_INPUT"
    assert payload["failed_stage"] == "polish"


def test_write_agent_mcp_clean_preserves_references(tmp_path):
    cfg = _build_config({}, tmp_path)
    cfg.ensure_dirs()
    ws_dir = tmp_path / "workspace" / "clean-ws"
    (ws_dir / "qa").mkdir(parents=True)
    (ws_dir / "references.bib").write_text("@article{Smith2024,title={A}}\n", encoding="utf-8")
    (ws_dir / "write.md").write_text("draft", encoding="utf-8")

    old_cfg = mcp_server._cfg
    try:
        mcp_server._cfg = cfg
        payload = json.loads(mcp_server.write_agent_clean("clean-ws"))
    finally:
        mcp_server._cfg = old_cfg

    assert payload["status"] == "CLEANED"
    assert (ws_dir / "references.bib").exists()
    assert not (ws_dir / "write.md").exists()


def test_write_agent_mcp_audit_missing_write_returns_status(tmp_path):
    cfg = _build_config({}, tmp_path)
    cfg.ensure_dirs()
    (tmp_path / "workspace" / "empty-ws").mkdir()

    old_cfg = mcp_server._cfg
    try:
        mcp_server._cfg = cfg
        payload = json.loads(mcp_server.write_agent_audit("empty-ws"))
    finally:
        mcp_server._cfg = old_cfg

    assert payload["status"] == "IN_PROGRESS"
    assert payload["next_action"] == "run_write_sections"
