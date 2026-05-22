"""Deterministic early gates for write-agent candidates."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from autor.write_agent.models import CandidateScore, SectionKernel
from autor.write_agent.preflight import load_reference_policy
from autor.write_agent.workspace_io import (
    extract_citekeys,
    parse_bibtex_keys,
    read_jsonl,
    read_text,
    sidecars_dir,
    write_jsonl,
    write_text,
)

BANNED_PATTERNS = [
    r"not simply\b.*\bbut\b",
    r"not merely\b.*\bbut\b",
    r"不是.*而是",
]

FRAMEWORK_NOUNS = [
    "framework",
    "scaffold",
    "landscape",
    "layer",
    "spectrum",
    "骨架",
    "层面",
    "谱系",
    "图谱",
    "框架",
]

GENERIC_ENDINGS = [
    "future studies are needed",
    "further validation is required",
    "provides new insights",
    "临床转化仍面临挑战",
    "仍需进一步研究",
]

ADJUDICATIVE_TERMS = [
    "shows",
    "show",
    "demonstrates",
    "indicates",
    "supports",
    "challenges",
    "fails",
    "failed",
    "outperforms",
    "undercuts",
    "constrains",
    "suggests",
    "establishes",
    "reveals",
    "argues",
    "therefore",
    "因此",
    "显示",
    "支持",
    "削弱",
    "限制",
]

FORBIDDEN_LEAPS = [
    " [l6]",
    "proves clinical efficacy",
    "guarantees clinical benefit",
    "establishes clinical efficacy",
    "definitively proves",
    "必然改善",
    "证明临床获益",
]


@dataclass
class GateDecision:
    status: str
    hard_fail: bool
    failure_class: list[str] = field(default_factory=list)
    rewrite_instruction: str = ""
    score: CandidateScore = field(default_factory=CandidateScore)
    citekeys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scores"] = asdict(self.score)
        data.pop("score", None)
        return data


def _load_kernels(ws_dir: Path) -> dict[str, SectionKernel]:
    rows = read_jsonl(sidecars_dir(ws_dir) / "section-kernels.jsonl")
    kernels: dict[str, SectionKernel] = {}
    for row in rows:
        kernels[row["section_id"]] = SectionKernel(
            section_id=row["section_id"],
            title=row.get("title", row["section_id"]),
            controlling_claim=row.get("controlling_claim", ""),
            evidence_keys=row.get("evidence_keys", []),
            contrast=row.get("contrast", ""),
            forbidden_overclaim=row.get("forbidden_overclaim", ""),
            required_tables=row.get("required_tables", []),
            direct_evidence_keys=row.get("direct_evidence_keys", []),
            adjacent_evidence_keys=row.get("adjacent_evidence_keys", []),
            background_only_keys=row.get("background_only_keys", []),
            required_figures=row.get("required_figures", []),
            failure_test=row.get("failure_test", ""),
        )
    return kernels


def load_reference_boundary(ws_dir: Path) -> tuple[set[str], set[str]]:
    bib_keys = parse_bibtex_keys(read_text(ws_dir / "references.bib"))
    _refmap_keys, blocked_keys, _records = load_reference_policy(ws_dir / "reference-map.json")
    return bib_keys, blocked_keys


def evidence_gate(text: str, ws_dir: Path, kernel: SectionKernel | None = None) -> GateDecision:
    citekeys = extract_citekeys(text)
    bib_keys, blocked_keys = load_reference_boundary(ws_dir)
    unknown = sorted(set(citekeys) - bib_keys)
    blocked = sorted(set(citekeys) & blocked_keys)
    failures: list[str] = []
    if unknown:
        failures.append("unknown_citekey")
    if blocked:
        failures.append("blocked_citekey")
    if kernel and citekeys:
        direct = set(kernel.direct_evidence_keys or kernel.evidence_keys)
        adjacent = set(kernel.adjacent_evidence_keys) | set(kernel.background_only_keys)
        if direct and citekeys[0] in adjacent and not any(key in direct for key in citekeys[:2]):
            failures.append("adjacent_evidence_leads")
    if failures:
        return GateDecision(
            status="BLOCKED_BY_EVIDENCE_BOUNDARY",
            hard_fail=True,
            failure_class=failures,
            rewrite_instruction="Rewrite using only licensed citation keys and direct evidence for the section claim.",
            score=CandidateScore(evidence_fidelity=0, hard_fail=True, failure_class=failures),
            citekeys=citekeys,
        )
    return GateDecision(
        status="PASS",
        hard_fail=False,
        score=CandidateScore(evidence_fidelity=5, section_specificity=3, boundary_precision=3),
        citekeys=citekeys,
    )


def claim_license_gate(text: str) -> GateDecision:
    lowered = text.lower()
    failures = [term.strip() for term in FORBIDDEN_LEAPS if term in lowered]
    if failures:
        return GateDecision(
            status="BLOCKED_BY_EVIDENCE_BOUNDARY",
            hard_fail=True,
            failure_class=["l6_forbidden_leap"],
            rewrite_instruction="Remove L6 clinical or causal leaps and recast the claim at the licensed evidence level.",
            score=CandidateScore(boundary_precision=0, hard_fail=True, failure_class=["l6_forbidden_leap"]),
        )
    status = "PASS"
    score = CandidateScore(boundary_precision=4)
    return GateDecision(status=status, hard_fail=False, score=score)


def anti_ai_gate(text: str) -> GateDecision:
    lowered = text.lower()
    failures: list[str] = []
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE | re.DOTALL):
            failures.append("banned_pattern")
            break
    if any(ending in lowered for ending in GENERIC_ENDINGS):
        failures.append("generic_validation_as_ending")
    framework_hits = sum(1 for noun in FRAMEWORK_NOUNS if noun.lower() in lowered)
    if framework_hits >= 3:
        failures.append("framework_noun_stack")
    if failures:
        return GateDecision(
            status="REWRITE_REQUIRED_STYLE",
            hard_fail=True,
            failure_class=list(dict.fromkeys(failures)),
            rewrite_instruction="Replace generic framework prose with section-specific adjudication grounded in evidence.",
            score=CandidateScore(anti_ai_penalty=5, hard_fail=True, failure_class=failures),
        )
    return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(anti_ai_penalty=0, human_move_score=3))


def cowardice_gate(text: str, kernel: SectionKernel | None = None) -> GateDecision:
    lowered = text.lower()
    failures: list[str] = []
    if not any(term in lowered for term in ADJUDICATIVE_TERMS):
        failures.append("no_adjudicative_claim")
    if kernel and kernel.failure_test and kernel.failure_test.lower() not in lowered:
        failures.append("no_decisive_failure_test")
    if any(ending in lowered for ending in GENERIC_ENDINGS):
        failures.append("generic_validation_as_ending")
    if failures:
        return GateDecision(
            status="REWRITE_REQUIRED_COWARDICE",
            hard_fail=True,
            failure_class=failures,
            rewrite_instruction="Make the direct evidence lead and state what interpretation it defeats or constrains.",
            score=CandidateScore(claim_courage=0, human_move_score=0, hard_fail=True, failure_class=failures),
        )
    return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(claim_courage=4, human_move_score=4))


def evaluate_candidate(text: str, ws_dir: Path, kernel: SectionKernel | None = None) -> GateDecision:
    decisions = [
        evidence_gate(text, ws_dir, kernel),
        claim_license_gate(text),
        anti_ai_gate(text),
        cowardice_gate(text, kernel),
    ]
    failures: list[str] = []
    for decision in decisions:
        failures.extend(decision.failure_class)
        if decision.hard_fail:
            decision.failure_class = list(dict.fromkeys(failures))
            decision.score.failure_class = decision.failure_class
            decision.score.hard_fail = True
            return decision
    citekeys = decisions[0].citekeys
    score = CandidateScore(
        evidence_fidelity=5,
        section_specificity=4,
        claim_courage=4,
        boundary_precision=4,
        anti_ai_penalty=0,
        human_move_score=4,
        hard_fail=False,
        failure_class=[],
    )
    return GateDecision(status="PASS", hard_fail=False, score=score, citekeys=citekeys)


def evaluate_section_candidates(ws_dir: Path, section_id: str, candidate_paths: list[Path]) -> list[dict[str, Any]]:
    kernel = _load_kernels(ws_dir).get(section_id)
    rows: list[dict[str, Any]] = []
    for path in candidate_paths:
        decision = evaluate_candidate(read_text(path), ws_dir, kernel)
        row = {"section_id": section_id, "candidate": path.name, **decision.to_dict()}
        rows.append(row)
    score_path = sidecars_dir(ws_dir) / "candidate-scores.jsonl"
    existing = [r for r in read_jsonl(score_path) if r.get("section_id") != section_id]
    write_jsonl(score_path, existing + rows)
    _write_reports(ws_dir, rows)
    _write_claim_license_ledger(ws_dir, rows)
    return rows


def _write_reports(ws_dir: Path, rows: list[dict[str, Any]]) -> None:
    anti = [r for r in rows if "banned_pattern" in r.get("failure_class", []) or r.get("status") == "REWRITE_REQUIRED_STYLE"]
    human = [r for r in rows if r.get("status") == "REWRITE_REQUIRED_COWARDICE"]
    write_text(
        sidecars_dir(ws_dir) / "anti-ai-report.md",
        "# Anti-AI Report\n\n" + "\n".join(f"- {r['section_id']} {r['candidate']}: {r['status']}" for r in anti) + "\n",
    )
    write_text(
        sidecars_dir(ws_dir) / "human-move-report.md",
        "# Human-Move Report\n\n" + "\n".join(f"- {r['section_id']} {r['candidate']}: {r['status']}" for r in human) + "\n",
    )


def _write_claim_license_ledger(ws_dir: Path, rows: list[dict[str, Any]]) -> None:
    path = sidecars_dir(ws_dir) / "claim-license-ledger.tsv"
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    if not existing:
        existing = "section_id\tcandidate\tlicense_level\tstatus\tfailure_class\n"
    lines = []
    for row in rows:
        failures = row.get("failure_class", [])
        level = "L6" if "l6_forbidden_leap" in failures else "L2"
        lines.append(
            f"{row['section_id']}\t{row['candidate']}\t{level}\t{row['status']}\t{','.join(failures)}"
        )
    write_text(path, existing.rstrip() + "\n" + "\n".join(lines) + "\n")
