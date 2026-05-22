"""Data-driven writing pattern policy for write-agent."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from autor.write_agent.models import SectionKernel, WriteAgentConfig
from autor.write_agent.workspace_io import read_json, read_jsonl, sidecars_dir, write_json, write_jsonl, write_text

LIBRARY_DIR = Path(__file__).parent / "pattern_library"


@dataclass
class PatternGateResult:
    section_id: str
    candidate_id: str | None
    status: str
    hard_fail: bool
    missing_required_moves: list[str] = field(default_factory=list)
    anti_ai_flags: list[dict[str, Any]] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)
    rewrite_instruction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_library_json(name: str) -> Any:
    return json.loads((LIBRARY_DIR / name).read_text(encoding="utf-8"))


def load_human_moves(ws_dir: Path) -> dict:
    sidecar = sidecars_dir(ws_dir) / "human-move-bank.json"
    if sidecar.exists():
        data = read_json(sidecar, default={})
    else:
        data = {"moves": _read_library_json("human-moves.json")}
    return data if isinstance(data, dict) else {"moves": data}


def load_negative_patterns(ws_dir: Path) -> dict:
    sidecar = sidecars_dir(ws_dir) / "anti-ai-patterns.json"
    if sidecar.exists():
        data = read_json(sidecar, default={})
    else:
        data = {"patterns": _read_library_json("negative-patterns.json")}
    return data if isinstance(data, dict) else {"patterns": data}


def _section_kind(section_id: str, title: str) -> str:
    text = f"{section_id} {title}".lower()
    if "intro" in text or "introduction" in text or "overview" in text:
        return "introduction"
    if "clinical" in text or "trial" in text or "translat" in text or "endpoint" in text:
        return "clinical"
    if "discussion" in text or "conclusion" in text or "future" in text:
        return "discussion"
    if "background" in text:
        return "background"
    return "evidence"


def build_pattern_contract(section_id: str, title: str) -> dict:
    kind = _section_kind(section_id, title)
    if kind == "introduction":
        required = ["real_tension_opening", "evidence_before_concept"]
        preferred = ["verbs_carry_judgment", "measurement_blindspot"]
        forbidden = ["generic_integration_opening", "framework_noun_density"]
    elif kind == "background":
        required = ["evidence_tiering", "verbs_carry_judgment"]
        preferred = ["old_model_failure", "precise_uncertainty"]
        forbidden = ["citation_stacking", "framework_noun_density"]
    elif kind == "clinical":
        required = ["clinical_claim_boundary", "evidence_tiering", "precise_uncertainty"]
        preferred = ["failure_test_ending", "verbs_carry_judgment"]
        forbidden = ["generic_validation_ending", "adjacent_evidence_as_direct"]
    elif kind == "discussion":
        required = ["failure_test_ending", "precise_uncertainty"]
        preferred = ["clinical_claim_boundary", "evidence_tiering"]
        forbidden = ["generic_validation_ending", "safe_conclusion_without_claim"]
    else:
        required = ["evidence_tiering", "precise_uncertainty"]
        preferred = ["verbs_carry_judgment", "measurement_blindspot"]
        forbidden = ["citation_stacking", "generic_validation_ending"]
    return {
        "section_id": section_id,
        "section_kind": kind,
        "required_moves": required,
        "preferred_moves": preferred,
        "forbidden_patterns": forbidden,
        "table_policy": "Tables must rank or downgrade evidence.",
        "ending_policy": "Ending must name a concrete missing proof or failure test.",
    }


def build_pattern_sidecars(ws_dir: Path, kernels: list[SectionKernel]) -> None:
    human_moves = {"moves": _read_library_json("human-moves.json")}
    negative_patterns = {"patterns": _read_library_json("negative-patterns.json")}
    contracts = [build_pattern_contract(kernel.section_id, kernel.title) for kernel in kernels]
    write_json(sidecars_dir(ws_dir) / "human-move-bank.json", human_moves)
    write_json(sidecars_dir(ws_dir) / "anti-ai-patterns.json", negative_patterns)
    write_jsonl(sidecars_dir(ws_dir) / "section-pattern-contracts.jsonl", contracts)


def load_section_contracts(ws_dir: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(sidecars_dir(ws_dir) / "section-pattern-contracts.jsonl")
    return {row["section_id"]: row for row in rows}


def scan_negative_patterns(text: str, patterns: dict) -> list[dict]:
    flags: list[dict] = []
    for pattern in patterns.get("patterns", []):
        regex = pattern.get("regex")
        if not regex:
            continue
        matches = re.findall(regex, text, flags=re.IGNORECASE | re.DOTALL)
        if matches:
            flags.append(
                {
                    "id": pattern["id"],
                    "severity": pattern.get("severity", "soft"),
                    "count": len(matches),
                    "instruction": pattern.get("instruction", ""),
                }
            )
    return flags


def has_generic_validation_without_target(text: str) -> bool:
    generic = re.search(
        r"future studies are needed|further validation is required|requires prospective validation|仍需进一步研究|需要进一步验证|临床转化仍面临挑战",
        text,
        flags=re.IGNORECASE,
    )
    if not generic:
        return False
    target_terms = (
        "assay",
        "endpoint",
        "mechanism",
        "subtype",
        "sampling",
        "trial",
        "ROI",
        "segmentation",
        "predictive",
        "pharmacodynamic",
        "reproducibility",
        "proof",
        "缺失",
        "机制",
        "终点",
        "亚型",
    )
    window = text[max(0, generic.start() - 160): generic.end() + 160].lower()
    return not any(term.lower() in window for term in target_terms)


def extract_markdown_tables(text: str) -> list[str]:
    tables: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if "|" in line and line.strip().startswith("|"):
            current.append(line)
        elif current:
            tables.append("\n".join(current))
            current = []
    if current:
        tables.append("\n".join(current))
    return tables


def table_is_warehouse(table_md: str) -> bool:
    first_lines = "\n".join(table_md.splitlines()[:2]).lower()
    warehouse_terms = ["study", "design", "marker", "assay", "endpoint", "strength", "limitation"]
    adjudication_terms = ["question", "direct", "adjacent", "unlicensed", "threshold", "downgrade", "conflict"]
    return sum(term in first_lines for term in warehouse_terms) >= 5 and not any(
        term in first_lines for term in adjudication_terms
    )


def _move_present(move_id: str, text: str) -> bool:
    lowered = text.lower()
    opening = " ".join(text.split()[:90]).lower()
    if move_id == "real_tension_opening":
        return any(token in opening for token in ("tension", "contradiction", "blind spot", "cannot", "fails", "whereas", "however"))
    if move_id == "evidence_before_concept":
        concept_pos = min([lowered.find(t) for t in ("framework", "concept", "paradigm", "model") if t in lowered] or [99999])
        evidence_pos = min([lowered.find(t) for t in ("shows", "reveals", "demonstrates", "limits", "fails") if t in lowered] or [99999])
        return evidence_pos < concept_pos or evidence_pos < 220
    if move_id == "verbs_carry_judgment":
        return bool(re.search(r"\b(separates|restricts|exposes|qualifies|licenses|fails|invalidates|converts|downgrades|constrains|reveals|shows|demonstrates)\b", lowered))
    if move_id == "evidence_tiering":
        return bool(re.search(r"\b(direct|adjacent|background|method-only|speculative|unlicensed|downgrade|tier)\b", lowered))
    if move_id == "precise_uncertainty":
        return bool(re.search(r"\b(assay|endpoint|mechanism|subtype|sampling|trial|roi|segmentation|predictive|pharmacodynamic|reproducibility|proof|uncertain|unresolved)\b", lowered))
    if move_id == "table_as_adjudication":
        return any(not table_is_warehouse(table) for table in extract_markdown_tables(text))
    if move_id == "failure_test_ending":
        ending = " ".join(text.split()[-120:]).lower()
        return any(token in ending for token in ("would fail", "would be incomplete", "failure test", "missing proof", "falsify", "prove the claim wrong"))
    if move_id == "old_model_failure":
        return bool(re.search(r"\b(old|traditional|prevailing|older).{0,80}\b(fails|cannot|inadequate|challenged)\b", lowered))
    if move_id == "measurement_blindspot":
        return bool(re.search(r"\b(can see|can count|identifies|measures).{0,120}\b(cannot|loses|misses|blind spot|spatial|location)\b", lowered))
    if move_id == "clinical_claim_boundary":
        return bool(re.search(r"\b(prognostic|predictive|treatment-directive|pharmacodynamic|trial-enrichment|endpoint|clinical boundary)\b", lowered))
    return False


def evaluate_pattern_contract(text: str, contract: dict, config: WriteAgentConfig | None = None) -> PatternGateResult:
    del config
    patterns = {"patterns": _read_library_json("negative-patterns.json")}
    flags = scan_negative_patterns(text, patterns)
    if has_generic_validation_without_target(text):
        flags.append(
            {
                "id": "generic_validation_without_target",
                "severity": "hard",
                "count": 1,
                "instruction": "Replace generic validation with a specific missing proof.",
            }
        )
    for table in extract_markdown_tables(text):
        if table_is_warehouse(table):
            flags.append(
                {
                    "id": "evidence_warehouse_table",
                    "severity": "hard",
                    "count": 1,
                    "instruction": "Rewrite the table so it ranks, separates, or downgrades evidence.",
                }
            )
    scores = {
        "real_tension_opening": int(_move_present("real_tension_opening", text)) * 2,
        "evidence_before_concept": int(_move_present("evidence_before_concept", text)) * 2,
        "verbs_carry_judgment": int(_move_present("verbs_carry_judgment", text)) * 2,
        "evidence_tiering": int(_move_present("evidence_tiering", text)) * 2,
        "precise_uncertainty": int(_move_present("precise_uncertainty", text)) * 2,
        "table_as_adjudication": int(_move_present("table_as_adjudication", text)) * 2,
        "failure_test_ending": int(_move_present("failure_test_ending", text)) * 2,
        "clinical_claim_boundary": int(_move_present("clinical_claim_boundary", text)) * 2,
        "anti_ai_penalty": sum(flag.get("count", 1) for flag in flags),
    }
    required_moves = contract.get("required_moves", [])
    missing = [move for move in required_moves if not _move_present(move, text)]
    soft_warnings = [flag["id"] for flag in flags if flag.get("severity") != "hard"]
    hard_flags = [flag for flag in flags if flag.get("severity") == "hard"]
    hard_fail = bool(hard_flags or missing)
    status = "REWRITE_REQUIRED_STYLE" if hard_fail else "PASS"
    instruction = "Rewrite from the section-specific pattern contract; do not patch with generic limitation prose."
    return PatternGateResult(
        section_id=contract.get("section_id", ""),
        candidate_id=None,
        status=status,
        hard_fail=hard_fail,
        missing_required_moves=missing,
        anti_ai_flags=flags,
        soft_warnings=soft_warnings,
        scores=scores,
        rewrite_instruction=instruction if hard_fail else "",
    )


def save_pattern_report(ws_dir: Path, results: list[PatternGateResult]) -> None:
    qa_dir = ws_dir / "qa" / "write-agent"
    qa_dir.mkdir(parents=True, exist_ok=True)
    rows = [result.to_dict() for result in results]
    score_path = sidecars_dir(ws_dir) / "pattern-scores.jsonl"
    existing = read_jsonl(score_path)
    result_keys = {(row.get("section_id"), row.get("candidate_id")) for row in rows}
    merged = [row for row in existing if (row.get("section_id"), row.get("candidate_id")) not in result_keys] + rows
    write_jsonl(score_path, merged)
    lines = ["# WriteAgent Pattern Report", ""]
    for result in results:
        lines.append(f"- {result.section_id}: {result.status}")
        if result.missing_required_moves:
            lines.append(f"  missing moves: {', '.join(result.missing_required_moves)}")
        if result.anti_ai_flags:
            lines.append("  flags: " + ", ".join(flag["id"] for flag in result.anti_ai_flags))
    write_text(qa_dir / "pattern-report.md", "\n".join(lines) + "\n")
