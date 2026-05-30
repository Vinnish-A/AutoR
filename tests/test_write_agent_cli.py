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


def test_write_agent_cli_polish_outputs_json(tmp_path, monkeypatch):
    cfg = _build_config({}, tmp_path)
    cfg.ensure_dirs()
    (tmp_path / "workspace" / "empty-ws").mkdir()
    messages: list[str] = []
    monkeypatch.setattr(cli, "ui", messages.append)

    cli.cmd_write_agent(
        Namespace(
            write_agent_action="polish",
            workspace="empty-ws",
            section=None,
            round_no=1,
            no_in_place=False,
        ),
        cfg,
    )

    payload = json.loads(messages[-1])
    assert payload["status"] == "BLOCKED_BY_MISSING_INPUT"
    assert payload["failed_stage"] == "polish"


def test_write_agent_cli_orchestrate_outputs_strategy_report(tmp_path, monkeypatch):
    cfg = _build_config({}, tmp_path)
    cfg.ensure_dirs()
    ws_dir = tmp_path / "workspace" / "orch-ws"
    ws_dir.mkdir(parents=True)
    (ws_dir / "references.bib").write_text("@article{Smith2024,\n title={Direct evidence}\n}\n", encoding="utf-8")
    (ws_dir / "reference-map.json").write_text(
        json.dumps({"references": [{"citekey": "Smith2024", "bibliographic_validity": "citable", "citation_policy": "must_cite"}]}),
        encoding="utf-8",
    )
    (ws_dir / "review-plan.md").write_text("# S1 Direct evidence\n\nSmith shows direct evidence [@Smith2024].\n", encoding="utf-8")
    (ws_dir / "evidence-ledger.md").write_text("S1 [@Smith2024]\n", encoding="utf-8")
    (ws_dir / "table-figure-plan.md").write_text("S1 T1 F1\n", encoding="utf-8")
    messages: list[str] = []
    monkeypatch.setattr(cli, "ui", messages.append)

    cli.cmd_write_agent(
        Namespace(write_agent_action="orchestrate", workspace="orch-ws", rounds=1, clean=False, execute=False),
        cfg,
    )

    payload = json.loads(messages[-1])
    assert payload["strategy_comparison"]["recommended"] == "contract_first"
    assert payload["next_action"] == "run_write_sections"
    assert "section_depth" in payload["completion"]
    assert (ws_dir / "qa" / "orchestrator" / "orchestrator-status.json").exists()


def test_write_agent_cli_audit_reports_depth_gap(tmp_path, monkeypatch):
    cfg = _build_config({}, tmp_path)
    cfg.ensure_dirs()
    ws_dir = tmp_path / "workspace" / "audit-ws"
    ws_dir.mkdir(parents=True)
    (ws_dir / "references.bib").write_text("@article{Smith2024,\n title={Direct evidence}\n}\n", encoding="utf-8")
    (ws_dir / "reference-map.json").write_text(
        json.dumps({"references": [{"citekey": "Smith2024", "bibliographic_validity": "citable", "citation_policy": "must_cite"}]}),
        encoding="utf-8",
    )
    (ws_dir / "review-plan.md").write_text("# S1 Direct evidence\n\nTarget 30000 words. Smith [@Smith2024].\n", encoding="utf-8")
    (ws_dir / "evidence-ledger.md").write_text("S1 [@Smith2024]\n", encoding="utf-8")
    (ws_dir / "table-figure-plan.md").write_text("S1 T1 F1\n", encoding="utf-8")
    from autor.write_agent.runner import build

    build("audit-ws", cfg)
    (ws_dir / "write.md").write_text("### S1: Direct evidence\n\nShort [@Smith2024].\n", encoding="utf-8")
    messages: list[str] = []
    monkeypatch.setattr(cli, "ui", messages.append)

    cli.cmd_write_agent(Namespace(write_agent_action="audit", workspace="audit-ws"), cfg)

    payload = json.loads(messages[-1])
    assert payload["cause_class"] == "depth_gap"
    assert payload["next_action"] == "run_section_depth_repair"
    assert payload["under_length_sections"] == ["S1"]
