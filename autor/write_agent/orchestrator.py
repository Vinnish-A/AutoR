"""Deterministic orchestration helpers around write-agent stages."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from autor.write_agent import runner
from autor.write_agent.contracts import load_writing_contracts
from autor.write_agent.workspace_io import extract_citekeys, parse_bibtex_keys, read_text, workspace_dir, write_json


LITERATURE_ROOT_FILES = {
    "references.bib",
    "reference-map.json",
    "review-plan.md",
    "evidence-ledger.md",
    "table-figure-plan.md",
    "acquisition-log.md",
    "papers.json",
    "info.md",
    "csl/nature.csl",
}

LITERATURE_COMPAT_FILES = {
    "paper-classification.md",
    "section-evidence.md",
    "table-plan.md",
    "execution-tasks.md",
}

LITERATURE_SIDECAR_PREFIXES = (
    "records-",
    "info-seed",
    "missing-seed",
    "citation-network",
    "workspace-evidence",
    "local-ranked",
    "planning-summary",
    "verification-local",
    "artifact-staged",
    "formal-descope",
    "trial-contract",
    "ws-status",
)

GENERATED_ROOT_FILES = {
    "write.md",
    "final.md",
    "final.docx",
    "final-cn.md",
    "final-cn.docx",
    "fail_prompt.md",
    "fail_progress.md",
}

GENERATED_DIRS = {"qa", "figure", "variants"}

GENERATED_SIDECARS = {
    "anti-ai-patterns.json",
    "anti-ai-report.md",
    "candidate-scores.jsonl",
    "claim-license-ledger.tsv",
    "critic-context.md",
    "human-move-bank.json",
    "human-move-report.md",
    "pattern-scores.history.jsonl",
    "pattern-scores.jsonl",
    "section-kernels.jsonl",
    "section-pattern-contracts.jsonl",
    "section-writing-contract.jsonl",
    "seed-bank.jsonl",
    "thesis-license.yaml",
    "write-agent-state.json",
    "write-merge-notes.md",
}


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def clean_workspace(root: Path, workspace: str) -> dict[str, Any]:
    ws_dir = workspace_dir(root, workspace)
    removed: list[str] = []
    preserved: list[str] = []
    if not ws_dir.exists():
        return {"status": "BLOCKED_BY_MISSING_INPUT", "workspace": workspace, "removed": removed, "preserved": preserved}

    for path in sorted(ws_dir.iterdir()):
        rel = _rel(path, ws_dir)
        if rel in LITERATURE_ROOT_FILES or rel in LITERATURE_COMPAT_FILES or rel in {"trials", "csl", "sidecars"}:
            preserved.append(rel)
            continue
        if path.is_dir() and path.name in GENERATED_DIRS:
            shutil.rmtree(path)
            removed.append(rel + "/")
        elif path.is_file() and (path.name in GENERATED_ROOT_FILES or path.name.startswith("write.")):
            path.unlink()
            removed.append(rel)
        else:
            preserved.append(rel)

    sidecars = ws_dir / "sidecars"
    if sidecars.exists():
        for path in sorted(sidecars.iterdir()):
            rel = _rel(path, ws_dir)
            if path.is_dir():
                if path.name in {"workflows"} or path.name.startswith("round-"):
                    preserved.append(rel + "/")
                else:
                    preserved.append(rel + "/")
                continue
            if path.name in GENERATED_SIDECARS:
                path.unlink()
                removed.append(rel)
            elif path.name.startswith(LITERATURE_SIDECAR_PREFIXES):
                preserved.append(rel)
            else:
                preserved.append(rel)

    return {"status": "CLEANED", "workspace": workspace, "removed": removed, "preserved": preserved}


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text))


def _section_blocks(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^#{1,6}\s+(S\d+[A-Za-z0-9_-]*)\s*[:.].*$", text))
    blocks: dict[str, str] = {}
    for idx, match in enumerate(matches):
        section_id = match.group(1)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        blocks[section_id] = text[match.start() : end]
    return blocks


def audit_section_depth(ws_dir: Path, text: str | None = None) -> list[dict[str, Any]]:
    manuscript = text if text is not None else read_text(ws_dir / "write.md") if (ws_dir / "write.md").exists() else ""
    blocks = _section_blocks(manuscript)
    rows: list[dict[str, Any]] = []
    for contract in load_writing_contracts(ws_dir).values():
        body = blocks.get(contract.section_id, "")
        words = _word_count(body)
        if not body:
            status = "missing"
        elif words < contract.min_words:
            status = "under_min"
        elif words > contract.max_words:
            status = "over_max"
        else:
            status = "within_range"
        rows.append(
            {
                "section_id": contract.section_id,
                "status": status,
                "words": words,
                "min_words": contract.min_words,
                "target_words": contract.target_words,
                "max_words": contract.max_words,
                "gap_to_min": max(0, contract.min_words - words),
                "gap_to_target": contract.target_words - words,
                "unique_citations": len(set(extract_citekeys(body))),
                "selected_seed_id": contract.selected_seed_id,
                "selected_candidate": contract.selected_candidate,
                "selected_score": contract.selected_score,
                "expansion_objectives": contract.expansion_objectives,
            }
        )
    return rows


def _must_cite_keys(ws_dir: Path) -> set[str]:
    path = ws_dir / "reference-map.json"
    if not path.exists():
        return set()
    data = json.loads(read_text(path))
    records = data.get("references", []) if isinstance(data, dict) else data
    return {record["citekey"] for record in records if record.get("citekey") and record.get("citation_policy") == "must_cite"}


def audit_completion(root: Path, workspace: str) -> dict[str, Any]:
    ws_dir = workspace_dir(root, workspace)
    write_path = ws_dir / "write.md"
    final_path = ws_dir / "final.md"
    bib_path = ws_dir / "references.bib"
    text = read_text(write_path) if write_path.exists() else ""
    citekeys = set(extract_citekeys(text))
    bib_keys = parse_bibtex_keys(read_text(bib_path)) if bib_path.exists() else set()
    must = _must_cite_keys(ws_dir)
    contracts = load_writing_contracts(ws_dir)
    contract_rows = [asdict(contract) for contract in contracts.values()]
    target_words = sum(contract.target_words for contract in contracts.values()) if contracts else 30000
    words = _word_count(text)
    section_depth = audit_section_depth(ws_dir, text) if contracts else []
    under_length = [row for row in section_depth if row["status"] in {"missing", "under_min"}]
    unknown = sorted(citekeys - bib_keys)
    missing_must = sorted(must - citekeys)
    pending = "_Draft pending._" in text
    figures_dir = ws_dir / "figure"
    figure_count = len(list(figures_dir.glob("*.png"))) if figures_dir.exists() else 0
    gates = {
        "write_exists": write_path.exists(),
        "no_pending_sections": bool(text) and not pending,
        "unknown_citekeys_zero": not unknown,
        "must_cite_complete": not missing_must,
        "word_floor_75pct": words >= round(target_words * 0.75),
        "section_word_ranges_ok": bool(contracts) and not under_length,
        "final_exists": final_path.exists(),
    }
    score = round(100 * sum(1 for ok in gates.values() if ok) / len(gates))
    if not write_path.exists() or pending:
        cause_class = "structure"
        next_action = "run_write_sections"
    elif unknown or missing_must:
        cause_class = "citation"
        next_action = "run_plan_repair"
    elif under_length or not gates["word_floor_75pct"]:
        cause_class = "depth_gap"
        next_action = "run_section_depth_repair"
    elif not final_path.exists():
        cause_class = "none"
        next_action = "run_external_critic"
    else:
        cause_class = "none"
        next_action = "stop"
    return {
        "workspace": workspace,
        "status": "READY_FOR_CRITIC" if next_action == "run_external_critic" else "APPROVED" if next_action == "stop" else "IN_PROGRESS",
        "cause_class": cause_class,
        "next_action": next_action,
        "score": score,
        "word_count": words,
        "target_words": target_words,
        "unique_citations": len(citekeys),
        "unknown_citekeys": unknown,
        "missing_must_cites": missing_must,
        "figure_count": figure_count,
        "gates": gates,
        "section_depth": section_depth,
        "under_length_sections": [row["section_id"] for row in under_length],
        "recommended_section_commands": [
            f"autor write-agent run {workspace} --section {row['section_id']} --round <N>" for row in under_length
        ],
        "section_contracts": contract_rows,
    }


def compare_strategies(root: Path, workspace: str) -> dict[str, Any]:
    ws_dir = workspace_dir(root, workspace)
    contracts = list(load_writing_contracts(ws_dir).values())
    if not contracts:
        return {"workspace": workspace, "status": "NO_CONTRACTS", "strategies": []}
    total_required = sum(len(contract.required_citekeys) for contract in contracts)
    total_optional = sum(len(contract.optional_citekeys) for contract in contracts)
    strategies = [
        {
            "name": "contract_first",
            "score": 90 + min(10, total_required // 10),
            "route": "repair claim licenses before rewrite; rerun only failed sections",
            "risk": "slower first pass, lowest hallucination risk",
        },
        {
            "name": "coverage_first",
            "score": 70 + min(20, (total_required + total_optional) // 20),
            "route": "maximize must-cite and representative cite-if-relevant coverage before style gates",
            "risk": "can invite citation-to-claim drift if claim licenses are loose",
        },
        {
            "name": "style_first",
            "score": 55,
            "route": "prioritize anti-AI pattern gates before evidence contract repair",
            "risk": "can produce polished but unsupported prose; use only after critic passes evidence",
        },
    ]
    strategies.sort(reverse=True, key=lambda row: row["score"])
    return {"workspace": workspace, "status": "COMPARED", "recommended": strategies[0]["name"], "strategies": strategies}


def orchestrate(
    root: Path,
    workspace: str,
    *,
    cfg: Any | None = None,
    rounds: int = 1,
    clean: bool = False,
    execute: bool = False,
) -> dict[str, Any]:
    ws_dir = workspace_dir(root, workspace)
    report_dir = ws_dir / "qa" / "orchestrator"
    cleanup = clean_workspace(root, workspace) if clean else None
    states: list[dict[str, Any]] = []
    for round_no in range(1, max(1, rounds) + 1):
        preflight = runner.preflight(workspace, cfg).to_dict()
        states.append({"round": round_no, "stage": "preflight", "state": preflight})
        if preflight.get("status") != "PREFLIGHT_PASSED":
            break
        build = runner.build(workspace, cfg).to_dict()
        states.append({"round": round_no, "stage": "build", "state": build})
        if execute:
            write = runner.write(workspace, cfg, sections=None, round_no=round_no).to_dict()
            states.append({"round": round_no, "stage": "write", "state": write})
            if write.get("status") == "DRAFT_READY_FOR_POLISH":
                polish = runner.polish(workspace, cfg, round_no=round_no).to_dict()
                states.append({"round": round_no, "stage": "polish", "state": polish})
            current = audit_completion(root, workspace)
            states.append({"round": round_no, "stage": "completion_audit", "state": current})
            if current["gates"].get("no_pending_sections") and current["gates"].get("must_cite_complete"):
                break
        else:
            break
    completion = audit_completion(root, workspace)
    strategies = compare_strategies(root, workspace)
    if completion.get("next_action") == "run_section_depth_repair":
        next_action = "run_section_depth_repair"
    elif completion.get("next_action") == "run_external_critic":
        next_action = "run_external_critic"
    else:
        next_action = "run_write_sections" if not execute else completion.get("next_action", "run_external_critic")
    report = {
        "workspace": workspace,
        "cleanup": cleanup,
        "execute": execute,
        "states": states,
        "completion": completion,
        "strategy_comparison": strategies,
        "next_action": next_action,
    }
    write_json(report_dir / "orchestrator-status.json", report)
    write_json(report_dir / "strategy-comparison.json", strategies)
    return report
