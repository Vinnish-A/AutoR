"""Workspace path and sidecar helpers for write-agent."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from autor import workspace as ws_mod

STATE_FILE = "write-agent-state.json"


def validate_workspace_name(name: str) -> None:
    if not ws_mod.validate_workspace_name(name):
        raise ValueError(f"非法工作区名称: {name}")


def workspace_dir(root: Path, workspace: str) -> Path:
    validate_workspace_name(workspace)
    return root / "workspace" / workspace


def sidecars_dir(ws_dir: Path) -> Path:
    return ws_dir / "sidecars"


def variants_dir(ws_dir: Path) -> Path:
    return ws_dir / "variants"


def qa_dir(ws_dir: Path, round_no: int) -> Path:
    return ws_dir / "qa" / f"round-{round_no}"


def ensure_write_agent_dirs(ws_dir: Path) -> None:
    sidecars_dir(ws_dir).mkdir(parents=True, exist_ok=True)
    variants_dir(ws_dir).mkdir(parents=True, exist_ok=True)
    (ws_dir / "qa").mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(_jsonable(row), ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def state_path(ws_dir: Path) -> Path:
    return sidecars_dir(ws_dir) / STATE_FILE


def read_state(ws_dir: Path) -> dict[str, Any]:
    return read_json(state_path(ws_dir), default={}) or {}


def write_state(ws_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    ensure_write_agent_dirs(ws_dir)
    write_json(state_path(ws_dir), state)
    return state


def update_state(ws_dir: Path, **updates: Any) -> dict[str, Any]:
    state = read_state(ws_dir)
    state.update({k: _jsonable(v) for k, v in updates.items()})
    return write_state(ws_dir, state)


def extract_citekeys(text: str) -> list[str]:
    keys = re.findall(r"@([A-Za-z0-9][A-Za-z0-9_.:/#-]*)", text)
    return list(dict.fromkeys(keys))


def parse_bibtex_keys(bib_text: str) -> set[str]:
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", bib_text))


def write_critic_context(ws_dir: Path, round_no: int, audit_assumption_label: str, critic_model_label: str) -> Path:
    target = sidecars_dir(ws_dir) / "critic-context.md"
    workspace = ws_dir.name
    text = f"""The manuscript under review was drafted by a {audit_assumption_label} through AutoR WriteAgent.

Treat it as a high-quality but potentially over-smoothed LLM-written review. Use {critic_model_label}. Do not rewrite. Do not patch. Produce a gate decision and a revision ticket.

Input files:
- workspace/{workspace}/write.md
- workspace/{workspace}/review-plan.md
- workspace/{workspace}/evidence-ledger.md
- workspace/{workspace}/reference-map.json
- workspace/{workspace}/references.bib
- workspace/{workspace}/table-figure-plan.md
- workspace/{workspace}/sidecars/claim-license-ledger.tsv
- workspace/{workspace}/sidecars/anti-ai-report.md
- workspace/{workspace}/sidecars/human-move-report.md

Output:
- workspace/{workspace}/qa/round-{round_no}/critic-ticket.md
"""
    write_text(target, text)
    return target
