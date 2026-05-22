"""Preflight validation for approved planning packages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from autor.write_agent.models import WriteAgentState
from autor.write_agent.workspace_io import (
    ensure_write_agent_dirs,
    extract_citekeys,
    parse_bibtex_keys,
    read_text,
    update_state,
    workspace_dir,
)

REQUIRED_FILES = [
    "references.bib",
    "reference-map.json",
    "review-plan.md",
    "evidence-ledger.md",
    "table-figure-plan.md",
]

INVALID_VALIDITY = {
    "not_citable",
    "unresolved",
    "duplicate-only",
    "blocked-without-metadata",
    "needs_metadata_fix",
}


def _walk_records(obj: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if any(k in obj for k in ("citekey", "citation_key", "key")):
            records.append(obj)
        for val in obj.values():
            records.extend(_walk_records(val))
    elif isinstance(obj, list):
        for val in obj:
            records.extend(_walk_records(val))
    return records


def load_reference_policy(refmap_path: Path) -> tuple[set[str], set[str], dict[str, dict[str, Any]]]:
    refmap = json.loads(read_text(refmap_path))
    known: set[str] = set()
    blocked: set[str] = set()
    records_by_key: dict[str, dict[str, Any]] = {}
    for record in _walk_records(refmap):
        key = str(record.get("citekey") or record.get("citation_key") or record.get("key") or "").strip()
        if not key:
            continue
        known.add(key)
        records_by_key[key] = record
        validity = str(record.get("bibliographic_validity") or record.get("validity") or "").lower()
        policy = str(record.get("citation_policy") or record.get("policy") or "").lower()
        status = str(record.get("status") or record.get("state") or "").lower()
        role = str(record.get("role") or record.get("evidence_role") or "").lower()
        if (
            validity in INVALID_VALIDITY
            or policy == "do_not_cite"
            or status in INVALID_VALIDITY
            or role in {"do_not_cite", "not_citable", "unresolved"}
        ):
            blocked.add(key)
    return known, blocked, records_by_key


def infer_main_sections(review_plan: str) -> list[str]:
    ids: list[str] = []
    for line in review_plan.splitlines():
        if not line.lstrip().startswith("#"):
            continue
        match = re.search(r"\b(S\d+[A-Za-z0-9_-]*)\b", line)
        if match:
            ids.append(match.group(1))
    if not ids:
        ids = re.findall(r"\b(S\d+[A-Za-z0-9_-]*)\b", review_plan)
    return list(dict.fromkeys(ids))


def run_preflight(root: Path, workspace: str) -> WriteAgentState:
    ws_dir = workspace_dir(root, workspace)
    ensure_write_agent_dirs(ws_dir)
    missing = [name for name in REQUIRED_FILES if not (ws_dir / name).exists()]
    if missing:
        state = WriteAgentState(
            workspace=workspace,
            status="BLOCKED_BY_MISSING_INPUT",
            failed_stage="preflight",
            cause_class="missing_input",
            next_action="return_orchestrator",
            details={"missing_files": missing, "plan_conflicts": []},
        )
        update_state(ws_dir, **state.to_dict())
        return state

    bib_keys = parse_bibtex_keys(read_text(ws_dir / "references.bib"))
    refmap_keys, blocked_keys, _records = load_reference_policy(ws_dir / "reference-map.json")
    plan_conflicts: list[str] = []
    if refmap_keys:
        missing_from_bib = sorted(refmap_keys - bib_keys)
        if missing_from_bib:
            plan_conflicts.append("reference-map citekeys missing from references.bib: " + ", ".join(missing_from_bib))

    for name in ("review-plan.md", "evidence-ledger.md", "table-figure-plan.md"):
        unknown = sorted(set(extract_citekeys(read_text(ws_dir / name))) - bib_keys)
        if unknown:
            plan_conflicts.append(f"{name} cites keys absent from references.bib: " + ", ".join(unknown))

    review_plan = read_text(ws_dir / "review-plan.md")
    main_sections = infer_main_sections(review_plan)
    status = "PREFLIGHT_PASSED" if not plan_conflicts else "BLOCKED_BY_PLAN_GAP"
    state = WriteAgentState(
        workspace=workspace,
        status=status,
        failed_stage="none" if not plan_conflicts else "preflight",
        cause_class="none" if not plan_conflicts else "plan_gap",
        next_action="continue" if not plan_conflicts else "return_orchestrator",
        details={
            "missing_files": [],
            "plan_conflicts": plan_conflicts,
            "citekey_count": len(bib_keys),
            "main_sections": main_sections,
            "blocked_citekeys": sorted(blocked_keys),
        },
    )
    update_state(ws_dir, **state.to_dict())
    return state
