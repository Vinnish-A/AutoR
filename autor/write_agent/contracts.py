"""Section-level writing contracts for write-agent orchestration."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from autor.write_agent.models import SectionKernel, SectionWritingContract
from autor.write_agent.patterns import load_section_contracts
from autor.write_agent.workspace_io import extract_citekeys, read_jsonl, read_text, sidecars_dir, write_jsonl


CONTRACT_FILE = "section-writing-contract.jsonl"


def _word_target_from_plan(ws_dir: Path) -> int:
    plan_path = ws_dir / "review-plan.md"
    if not plan_path.exists():
        return 30000
    text = read_text(plan_path).lower()
    match = re.search(r"(\d{2,3}[,，]?\d{3}|\d{4,5})\s*(?:words|word count|词)", text)
    if match:
        return int(match.group(1).replace(",", "").replace("，", ""))
    if "mini_review" in text or "mini review" in text:
        return 12000
    if "focused_review" in text or "focused review" in text:
        return 16000
    return 30000


def _reference_records(ws_dir: Path) -> list[dict[str, Any]]:
    path = ws_dir / "reference-map.json"
    if not path.exists():
        return []
    data = json.loads(read_text(path))
    return data.get("references", []) if isinstance(data, dict) else data


def _known_citekeys(ws_dir: Path) -> list[str]:
    return [str(record.get("citekey")) for record in _reference_records(ws_dir) if record.get("citekey")]


def _keys_in_text(text: str, known_keys: list[str]) -> list[str]:
    keys = extract_citekeys(text)
    for key in known_keys:
        if re.search(rf"(?<![A-Za-z0-9_.:/#-]){re.escape(key)}(?![A-Za-z0-9_.:/#-])", text):
            keys.append(key)
    return list(dict.fromkeys(keys))


def _contract_context_lines(ws_dir: Path, kernel: SectionKernel) -> list[str]:
    markers = {kernel.section_id, *kernel.required_tables, *kernel.required_figures}
    lines: list[str] = []
    for filename in ("review-plan.md", "evidence-ledger.md", "table-figure-plan.md"):
        path = ws_dir / filename
        if not path.exists():
            continue
        for line in read_text(path).splitlines():
            if any(marker and marker in line for marker in markers):
                lines.append(line)
    return lines


def _scope_fields(ws_dir: Path, kernel: SectionKernel, required: list[str], optional: list[str]) -> dict[str, list[str]]:
    known = _known_citekeys(ws_dir)
    context = _contract_context_lines(ws_dir, kernel)
    all_section_keys = list(dict.fromkeys([*required, *optional, *[key for line in context for key in _keys_in_text(line, known)]]))
    table_only: list[str] = []
    figure_only: list[str] = []
    currentness_only: list[str] = []
    forbidden: list[str] = []
    for line in context:
        lowered = line.lower()
        line_keys = _keys_in_text(line, known)
        if not line_keys:
            continue
        table_only_hits: list[str] = []
        if "table-only" in lowered or "table only" in lowered or "prose-support" in lowered:
            for match in re.finditer(
                r"([^|.;]{0,360}?)\b(?:are|is)\b[^|.;]*(?:table[- ]only|boundary rows?|not[^|.;]*prose)",
                line,
                flags=re.IGNORECASE,
            ):
                table_only_hits.extend(_keys_in_text(match.group(1), known))
            if not table_only_hits and len(line_keys) <= 5:
                table_only_hits.extend(line_keys)
        table_only.extend(table_only_hits)
        if "figure-only" in lowered or "figure only" in lowered:
            figure_only.extend(line_keys)
        if "currentness" in lowered or "acquisition gap" in lowered or "non-citable until" in lowered:
            currentness_only.extend(
                token
                for token in re.findall(r"\b(?:UNRESOLVED|ACQ_TARGET)[A-Za-z0-9_.:/#-]*", line)
                if not token.endswith("_")
            )
        if "do not" in lowered or "forbidden overclaim" in lowered or "not direct" in lowered:
            forbidden.append(line.strip())
    table_only = list(dict.fromkeys(table_only))
    figure_only = list(dict.fromkeys(figure_only))
    currentness_only = list(dict.fromkeys(currentness_only))
    scoped_out = set(table_only) | set(figure_only) | set(currentness_only)
    prose_allowed = [key for key in all_section_keys if key not in scoped_out]
    return {
        "prose_allowed_citekeys": prose_allowed,
        "table_only_citekeys": table_only,
        "figure_only_citekeys": figure_only,
        "currentness_only_records": currentness_only,
        "forbidden_claim_patterns": list(dict.fromkeys(forbidden))[:12],
    }


def _expansion_objectives(kernel: SectionKernel) -> list[str]:
    objectives = [
        "open from the section's strongest evidence tension rather than broad background",
        "separate direct, adjacent, method-only, background, and table-only evidence",
        "turn the planned table/figure into prose-level adjudication before the asset",
    ]
    title = kernel.title.lower()
    if any(token in title for token in ("clinical", "trial", "decision", "endpoint")):
        objectives.append("rank retained clinical evidence by endpoint maturity and treatment-decision license")
    if any(token in title for token in ("immune", "tumor", "tumour", "niche", "mechan")):
        objectives.append("explain what mechanism is directly shown, what is only adjacent vocabulary, and what proof is missing")
    if any(token in title for token in ("mrd", "ctdna")):
        objectives.append("separate prognostic MRD signal from validated treatment-guiding utility")
    if any(token in title for token in ("method", "platform", "validation", "assay")):
        objectives.append("rank platforms by what validation loss each one actually solves")
    return objectives


def _required_citekeys(ws_dir: Path, kernel: SectionKernel) -> list[str]:
    keys: list[str] = []
    evidence = set(kernel.evidence_keys)
    for record in _reference_records(ws_dir):
        citekey = record.get("citekey")
        if not citekey or record.get("citation_policy") != "must_cite":
            continue
        if kernel.section_id in (record.get("sections") or []) or citekey in evidence:
            keys.append(citekey)
    return list(dict.fromkeys(keys))


def _prohibited_citekeys(ws_dir: Path) -> list[str]:
    keys: list[str] = []
    for record in _reference_records(ws_dir):
        citekey = record.get("citekey")
        if not citekey:
            continue
        if record.get("citation_policy") == "do_not_cite" or record.get("bibliographic_validity") != "citable":
            keys.append(citekey)
    return list(dict.fromkeys(keys))


def _preferred_seed_types(kernel: SectionKernel) -> list[str]:
    text = f"{kernel.section_id} {kernel.title}".lower()
    if any(token in text for token in ("clinical", "trial", "endpoint", "decision")):
        return ["clinical_endpoint_failure", "evidence_downgrade", "table_adjudication"]
    if any(token in text for token in ("method", "platform", "validation", "assay")):
        return ["method_loss", "measurement_blindspot", "table_adjudication"]
    if any(token in text for token in ("immune", "tumor", "tumour", "mechan", "niche", "mrd", "ctdna")):
        return ["mechanistic_tension", "direct_vs_adjacent_evidence", "measurement_blindspot"]
    return ["direct_vs_adjacent_evidence", "measurement_blindspot", "old_model_failure"]


def _section_weight(kernel: SectionKernel) -> float:
    evidence_weight = min(len(kernel.evidence_keys), 30) * 0.06
    direct_weight = min(len(kernel.direct_evidence_keys), 20) * 0.04
    asset_weight = len(kernel.required_tables) * 0.35 + len(kernel.required_figures) * 0.25
    clinical_weight = 0.8 if any(token in kernel.title.lower() for token in ("clinical", "trial", "decision")) else 0.0
    return 1.0 + evidence_weight + direct_weight + asset_weight + clinical_weight


def build_writing_contracts(ws_dir: Path, kernels: list[SectionKernel]) -> list[SectionWritingContract]:
    total_words = _word_target_from_plan(ws_dir)
    weights = {kernel.section_id: _section_weight(kernel) for kernel in kernels}
    total_weight = sum(weights.values()) or 1.0
    pattern_contracts = load_section_contracts(ws_dir)
    prohibited = _prohibited_citekeys(ws_dir)
    existing = load_writing_contracts(ws_dir)
    contracts: list[SectionWritingContract] = []
    for kernel in kernels:
        target = max(900, round(total_words * weights[kernel.section_id] / total_weight))
        required = _required_citekeys(ws_dir, kernel)
        optional = [key for key in kernel.evidence_keys if key not in set(required)]
        pattern = pattern_contracts.get(kernel.section_id, {})
        scope = _scope_fields(ws_dir, kernel, required, optional)
        previous = existing.get(kernel.section_id)
        contract = SectionWritingContract(
            section_id=kernel.section_id,
            target_words=target,
            min_words=max(500, round(target * 0.75)),
            max_words=round(target * 1.25),
            required_citekeys=required,
            optional_citekeys=optional,
            prohibited_citekeys=prohibited,
            preferred_seed_types=_preferred_seed_types(kernel),
            required_moves=list(pattern.get("required_moves", [])),
            table_ids=kernel.required_tables,
            figure_ids=kernel.required_figures,
            prose_allowed_citekeys=scope["prose_allowed_citekeys"],
            table_only_citekeys=scope["table_only_citekeys"],
            figure_only_citekeys=scope["figure_only_citekeys"],
            currentness_only_records=scope["currentness_only_records"],
            forbidden_claim_patterns=scope["forbidden_claim_patterns"],
            expansion_objectives=_expansion_objectives(kernel),
        )
        if previous:
            contract.target_words = previous.target_words
            contract.min_words = previous.min_words
            contract.max_words = previous.max_words
            contract.forbidden_claim_patterns = list(
                dict.fromkeys([*contract.forbidden_claim_patterns, *previous.forbidden_claim_patterns])
            )
            contract.expansion_objectives = list(
                dict.fromkeys([*contract.expansion_objectives, *previous.expansion_objectives])
            )
            contract.claim_license_decisions = previous.claim_license_decisions
            contract.evidence_maturity_order = previous.evidence_maturity_order
            contract.table_contract = previous.table_contract
            contract.selected_seed_id = previous.selected_seed_id
            contract.selected_candidate = previous.selected_candidate
            contract.selected_score = previous.selected_score
        if kernel.section_id == "S7":
            direct_treatment_keys = {
                "Masuda2017Adjuvant",
                "vonMinckwitz2019Trastuzumab",
                "Geyer2022Overall",
                "Mayer2021Randomized",
                "Litton2020Neoadjuvant",
            }
            contract.table_only_citekeys = [
                key for key in contract.table_only_citekeys if key not in direct_treatment_keys
            ]
            contract.prose_allowed_citekeys = list(
                dict.fromkeys([*contract.prose_allowed_citekeys, *[key for key in contract.required_citekeys if key in direct_treatment_keys]])
            )
            if "Schmid2020Pembrolizumab" not in contract.table_only_citekeys:
                contract.table_only_citekeys.append("Schmid2020Pembrolizumab")
            contract.prose_allowed_citekeys = [
                key for key in contract.prose_allowed_citekeys if key != "Schmid2020Pembrolizumab"
            ]
        contracts.append(contract)
    write_jsonl(sidecars_dir(ws_dir) / CONTRACT_FILE, contracts)
    return contracts


def load_writing_contracts(ws_dir: Path) -> dict[str, SectionWritingContract]:
    rows = read_jsonl(sidecars_dir(ws_dir) / CONTRACT_FILE)
    return {row["section_id"]: SectionWritingContract(**row) for row in rows}


def update_selected_candidate(ws_dir: Path, section_id: str, candidate_path: Path, score: int) -> None:
    contracts = load_writing_contracts(ws_dir)
    contract = contracts.get(section_id)
    if not contract:
        return
    candidate = candidate_path.name
    seed_id = f"{section_id}-{candidate_path.stem}"
    contract.selected_candidate = candidate
    contract.selected_seed_id = seed_id
    contract.selected_score = score
    write_jsonl(sidecars_dir(ws_dir) / CONTRACT_FILE, list(contracts.values()))
