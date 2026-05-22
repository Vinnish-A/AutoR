"""Polish stage for anchored write-agent manuscripts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from autor.write_agent import llm
from autor.write_agent.config import from_autor_config
from autor.write_agent.integrate import replace_section
from autor.write_agent.models import SectionKernel, WriteAgentState
from autor.write_agent.patterns import (
    evaluate_pattern_contract,
    load_section_contracts,
    save_pattern_report,
    scan_negative_patterns,
)
from autor.write_agent.prompts import POLISH_PASS, POLISH_SYSTEM
from autor.write_agent.workspace_io import extract_citekeys, read_jsonl, read_text, update_state, write_text

PLACEHOLDER_RE = re.compile(r"(insert citation|citation needed|fill in|real numbers|待补充|补充引用)", re.IGNORECASE)


def _load_kernels(ws_dir: Path) -> dict[str, SectionKernel]:
    rows = read_jsonl(ws_dir / "sidecars" / "section-kernels.jsonl")
    return {row["section_id"]: SectionKernel(**row) for row in rows}


def _anchored_sections(text: str) -> dict[str, str]:
    pattern = re.compile(r"<!--\s*AUTOR:SECTION\s+([A-Za-z0-9_-]+)\s+START\s*-->(.*?)<!--\s*AUTOR:SECTION\s+\1\s+END\s*-->", re.DOTALL)
    return {match.group(1): match.group(2).strip() for match in pattern.finditer(text)}


def _result(
    workspace: str,
    status: str,
    *,
    failed_stage: str = "none",
    cause_class: str = "none",
    next_action: str = "continue",
    details: dict[str, Any] | None = None,
) -> WriteAgentState:
    return WriteAgentState(
        workspace=workspace,
        status=status,
        failed_stage=failed_stage,
        cause_class=cause_class,
        next_action=next_action,
        details=details or {},
    )


def run_polish(
    workspace: str,
    cfg: Any,
    *,
    sections: list[str] | None = None,
    round_no: int = 1,
    in_place: bool = True,
) -> WriteAgentState:
    ws_dir = cfg._root / "workspace" / workspace
    write_md = ws_dir / "write.md"
    if not write_md.exists():
        state = _result(
            workspace,
            "BLOCKED_BY_MISSING_INPUT",
            failed_stage="polish",
            cause_class="missing_input",
            next_action="rerun_write",
            details={"missing_files": ["write.md"]},
        )
        update_state(ws_dir, **state.to_dict())
        return state
    kernels = _load_kernels(ws_dir)
    contracts = load_section_contracts(ws_dir)
    if not kernels or not contracts:
        state = _result(
            workspace,
            "BLOCKED_BY_MISSING_INPUT",
            failed_stage="polish",
            cause_class="missing_input",
            next_action="run_build",
            details={"missing_files": ["section-kernels.jsonl", "section-pattern-contracts.jsonl"]},
        )
        update_state(ws_dir, **state.to_dict())
        return state
    sections_by_id = _anchored_sections(read_text(write_md))
    selected = set(sections or sections_by_id.keys())
    if not sections_by_id:
        state = _result(
            workspace,
            "BLOCKED_BY_MISSING_INPUT",
            failed_stage="polish",
            cause_class="missing_input",
            next_action="rerun_write",
            details={"missing_files": ["write.md section anchors"]},
        )
        update_state(ws_dir, **state.to_dict())
        return state

    wa_cfg = from_autor_config(cfg)
    round_dir = ws_dir / "qa" / f"round-{round_no}"
    round_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = ws_dir / "qa" / "write-agent"
    qa_dir.mkdir(parents=True, exist_ok=True)
    report_lines = ["# WriteAgent Polish Report", ""]
    pattern_results = []
    polished_sections: list[str] = []

    for section_id, source_text in sections_by_id.items():
        if section_id not in selected:
            continue
        kernel = kernels.get(section_id)
        contract = contracts.get(section_id)
        if not kernel or not contract:
            continue
        if PLACEHOLDER_RE.search(source_text):
            state = _result(
                workspace,
                "REWRITE_REQUIRED_STYLE",
                failed_stage="polish",
                cause_class="needs_rewrite_not_polish",
                next_action="rerun_write",
                details={"section_id": section_id},
            )
            update_state(ws_dir, **state.to_dict())
            return state
        source_keys = set(extract_citekeys(source_text))
        prompt = POLISH_PASS.format(
            section_id=section_id,
            title=kernel.title,
            controlling_claim=kernel.controlling_claim,
            source_text=source_text,
        )
        try:
            polished = llm.complete_text(prompt, wa_cfg, system=POLISH_SYSTEM, model=wa_cfg.model)
        except Exception as e:
            state = _result(
                workspace,
                "WRITE_AGENT_API_FAILED",
                failed_stage="polish",
                cause_class="api_failure",
                next_action="stop",
                details={"section_id": section_id, "error": str(e)},
            )
            update_state(ws_dir, **state.to_dict())
            return state
        polished = polished.strip() + "\n"
        polished_keys = set(extract_citekeys(polished))
        added = sorted(polished_keys - source_keys)
        removed = sorted(source_keys - polished_keys)
        if added or removed:
            state = _result(
                workspace,
                "REWRITE_REQUIRED_STYLE",
                failed_stage="polish",
                cause_class="citation_drift",
                next_action="rerun_write",
                details={"section_id": section_id, "added_citekeys": added, "removed_citekeys": removed},
            )
            update_state(ws_dir, **state.to_dict())
            return state
        pattern_result = evaluate_pattern_contract(polished, contract, wa_cfg)
        pattern_result.candidate_id = f"{section_id}.polished.md"
        pattern_results.append(pattern_result)
        if pattern_result.hard_fail:
            state = _result(
                workspace,
                "REWRITE_REQUIRED_STYLE",
                failed_stage="polish",
                cause_class="pattern_gate_failed",
                next_action="rerun_write",
                details={"section_id": section_id, "pattern_result": pattern_result.to_dict()},
            )
            update_state(ws_dir, **state.to_dict())
            save_pattern_report(ws_dir, pattern_results)
            return state
        hard_flags = [flag for flag in scan_negative_patterns(polished, {"patterns": []}) if flag.get("severity") == "hard"]
        if hard_flags:
            state = _result(
                workspace,
                "REWRITE_REQUIRED_STYLE",
                failed_stage="polish",
                cause_class="pattern_gate_failed",
                next_action="rerun_write",
                details={"section_id": section_id, "anti_ai_flags": hard_flags},
            )
            update_state(ws_dir, **state.to_dict())
            return state
        write_text(round_dir / f"{section_id}.polished.md", polished)
        if in_place:
            replace_section(ws_dir, section_id, kernel.title, polished)
        polished_sections.append(section_id)
        report_lines.append(f"- {section_id}: PASS")

    save_pattern_report(ws_dir, pattern_results)
    write_text(qa_dir / "polish-report.md", "\n".join(report_lines) + "\n")
    state = _result(
        workspace,
        "WRITE_READY_FOR_EXTERNAL_CRITIC",
        next_action="critic_context",
        details={"polished_sections": polished_sections, "round": round_no, "in_place": in_place},
    )
    update_state(ws_dir, **state.to_dict())
    return state
