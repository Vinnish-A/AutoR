"""Polish stage for anchored write-agent manuscripts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from autor.write_agent import llm
from autor.write_agent.config import from_autor_config
from autor.write_agent.contracts import load_writing_contracts
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


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\S+\b", text))


def _load_kernels(ws_dir: Path) -> dict[str, SectionKernel]:
    rows = read_jsonl(ws_dir / "sidecars" / "section-kernels.jsonl")
    return {row["section_id"]: SectionKernel(**row) for row in rows}


def _anchored_sections(text: str) -> dict[str, str]:
    pattern = re.compile(r"<!--\s*AUTOR:SECTION\s+([A-Za-z0-9_-]+)\s+START\s*-->(.*?)<!--\s*AUTOR:SECTION\s+\1\s+END\s*-->", re.DOTALL)
    sections = {match.group(1): match.group(2).strip() for match in pattern.finditer(text)}
    if sections:
        return sections
    heading_pattern = re.compile(
        r"^###\s+(S\d+[A-Za-z0-9_-]*)\s*[:.].*?(?=^###\s+S\d+[A-Za-z0-9_-]*\s*[:.]|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    return {match.group(1): match.group(0).strip() for match in heading_pattern.finditer(text)}


def _heading_sections_by_kernel_order(text: str, kernels: dict[str, SectionKernel]) -> dict[str, str]:
    matches = list(re.finditer(r"^###\s+.*$", text, flags=re.MULTILINE))
    if not matches:
        return {}
    ids = list(kernels.keys())
    sections: dict[str, str] = {}
    for index, match in enumerate(matches[: len(ids)]):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[ids[index]] = text[start:end].strip()
    return sections


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
    write_text_source = read_text(write_md)
    sections_by_id = _anchored_sections(write_text_source)
    if not sections_by_id:
        sections_by_id = _heading_sections_by_kernel_order(write_text_source, kernels)
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
    staged_replacements: dict[str, tuple[str, str]] = {}
    writing_contracts = load_writing_contracts(ws_dir)

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
        writing_contract = writing_contracts.get(section_id)
        length_invalid = False
        if writing_contract:
            words = _word_count(polished)
            length_invalid = words < writing_contract.min_words or words > writing_contract.max_words
        if added or removed or length_invalid:
            source_pattern_result = evaluate_pattern_contract(source_text, contract, wa_cfg)
            source_pattern_result.candidate_id = f"{section_id}.source-retained.md"
            pattern_results.append(source_pattern_result)
            if source_pattern_result.hard_fail:
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
            write_text(round_dir / f"{section_id}.polished.md", source_text.strip() + "\n")
            polished_sections.append(section_id)
            staged_replacements[section_id] = (kernel.title, source_text.strip() + "\n")
            reason = "citation drift" if added or removed else "word-range drift"
            report_lines.append(
                f"- {section_id}: PASS_SOURCE_RETAINED "
                f"(rejected polish {reason}; added={len(added)}, removed={len(removed)})"
            )
            continue
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
        staged_replacements[section_id] = (kernel.title, polished)
        polished_sections.append(section_id)
        report_lines.append(f"- {section_id}: PASS")

    if in_place:
        for section_id, (title, replacement) in staged_replacements.items():
            replace_section(ws_dir, section_id, title, replacement)
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
