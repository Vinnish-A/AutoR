"""Deterministic table and figure integration for write-agent manuscripts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from autor.write_agent.patterns import evaluate_pattern_contract, load_section_contracts
from autor.write_agent.workspace_io import (
    extract_citekeys,
    read_jsonl,
    read_state,
    read_text,
    write_jsonl,
    write_state,
    write_text,
)

ASSET_START = "<!-- AUTOR:ASSETS START -->"
ASSET_END = "<!-- AUTOR:ASSETS END -->"


@dataclass
class AssetPair:
    pair_id: str
    section_id: str
    table_id: str
    figure_id: str
    question: str
    citekeys: list[str]
    trial_ids: list[str]
    table_title: str
    figure_title: str


@dataclass
class TableSpec:
    table_id: str
    columns: list[str]


@dataclass
class TableContract:
    table_id: str
    headers: list[str]
    rows: list[list[str]]


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _parse_pair_matrix(text: str) -> list[AssetPair]:
    rows: list[AssetPair] = []
    in_matrix = False
    headers: list[str] = []
    for line in text.splitlines():
        if line.startswith("## Table") and "Pair Matrix" in line:
            in_matrix = True
            continue
        if in_matrix and line.startswith("## "):
            break
        if not in_matrix or not line.startswith("|"):
            continue
        cells = _split_row(line)
        if not headers:
            headers = cells
            continue
        if set(cells) == {"---"} or not cells or cells[0] == "---":
            continue
        row = dict(zip(headers, cells))
        citekeys = [item.strip() for item in row.get("Shared citekeys", "").split(";") if item.strip() and item.strip() != "none"]
        trials = [item.strip() for item in row.get("Shared trial IDs", "").split(";") if item.strip() and item.strip() != "none"]
        rows.append(
            AssetPair(
                pair_id=row.get("Pair ID", ""),
                section_id=row.get("Section slot", ""),
                table_id=row.get("Table ID", ""),
                figure_id=row.get("Figure ID", ""),
                question=row.get("Shared synthesis question", ""),
                citekeys=citekeys,
                trial_ids=trials,
                table_title=row.get("Table function", "") or row.get("Shared synthesis question", ""),
                figure_title=row.get("Figure function", "") or row.get("Shared synthesis question", ""),
            )
        )
    return rows


def _parse_table_specs(text: str) -> dict[str, TableSpec]:
    specs: dict[str, TableSpec] = {}
    in_tables = False
    headers: list[str] = []
    for line in text.splitlines():
        if line.startswith("## Tables"):
            in_tables = True
            headers = []
            continue
        if in_tables and line.startswith("## "):
            break
        if not in_tables or not line.startswith("|"):
            continue
        cells = _split_row(line)
        if not headers:
            headers = cells
            continue
        if set(cells) == {"---"} or not cells or cells[0] == "---":
            continue
        row = dict(zip(headers, cells))
        table_id = row.get("Table ID", "")
        columns_text = row.get("Columns", "") or row.get("Required columns", "")
        columns = [cell.strip() for cell in columns_text.split(";") if cell.strip()]
        if table_id and columns:
            specs[table_id] = TableSpec(table_id=table_id, columns=columns)
    return specs


def _parse_analytic_contracts(text: str) -> dict[str, TableContract]:
    contracts: dict[str, TableContract] = {}
    current_id = ""
    headers: list[str] = []
    rows: list[list[str]] = []
    in_contract = False
    for line in text.splitlines() + ["## END"]:
        match = re.match(r"^###\s+(T\d+)\s+Required Rows", line)
        if match or (in_contract and (line.startswith("### ") or line.startswith("## "))):
            if current_id and headers and rows:
                contracts[current_id] = TableContract(current_id, headers, rows)
            current_id = match.group(1) if match else ""
            headers = []
            rows = []
            in_contract = bool(match)
            continue
        if not in_contract or not line.startswith("|"):
            continue
        cells = _split_row(line)
        if not headers:
            headers = cells
            continue
        if all(set(cell) <= {"-"} for cell in cells):
            continue
        rows.append(cells)
    return contracts


def _render_contract_table(pair: AssetPair, contract: TableContract) -> str:
    table_number = re.sub(r"\D+", "", pair.table_id) or pair.table_id
    table_title = _sanitize_manuscript_text(pair.table_title)
    lines = [f"#### Table {table_number}. {table_title} ({pair.table_id}/{pair.pair_id})", ""]
    headers = [_sanitize_manuscript_text(header) for header in contract.headers]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in contract.rows:
        cells = row[: len(headers)] + [""] * max(0, len(headers) - len(row))
        if headers and headers[0].strip().lower().startswith("citekey"):
            first = cells[0].strip()
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_:-]*", first) and not first.startswith("@"):
                cells[0] = f"[@{first}]"
        cells = [_sanitize_manuscript_text(cell).replace("|", "/") for cell in cells]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _reference_records(ws_dir: Path) -> dict[str, dict]:
    data = _reference_map_data(ws_dir)
    records = data.get("references", []) if isinstance(data, dict) else data
    return {str(record.get("citekey", "")): record for record in records if record.get("citekey")}


def _reference_map_data(ws_dir: Path) -> dict:
    path = ws_dir / "reference-map.json"
    if not path.exists():
        return {}
    data = json.loads(read_text(path))
    return data if isinstance(data, dict) else {}


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _retained_trial_ids_from_reference_map(ws_dir: Path, pair: AssetPair) -> list[str]:
    data = _reference_map_data(ws_dir)
    ids: list[str] = []
    for record in data.get("trials", []):
        trial_id = str(record.get("trial_id") or "").strip()
        if not trial_id or record.get("status") != "retained":
            continue
        sections = set(record.get("sections") or [])
        assets = set(record.get("paired_assets") or [])
        if pair.section_id in sections or pair.pair_id in assets or pair.table_id in assets:
            ids.append(trial_id)
    return ids


def _trial_sidecar_records(ws_dir: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    trials_dir = ws_dir / "trials"
    if not trials_dir.exists():
        return records
    for path in sorted(trials_dir.glob("**/trials.json")):
        try:
            data = json.loads(read_text(path))
        except (OSError, json.JSONDecodeError):
            continue
        candidates = data.get("results", []) if isinstance(data, dict) else []
        if not isinstance(candidates, list):
            continue
        for record in candidates:
            if not isinstance(record, dict):
                continue
            trial_id = str(record.get("trial_id") or "").strip()
            if trial_id:
                records[trial_id] = record
    return records


def _retained_trial_ids_from_sidecars(ws_dir: Path, pair: AssetPair) -> list[str]:
    ids: list[str] = []
    for trial_id, record in _trial_sidecar_records(ws_dir).items():
        retention_basis = str(record.get("retention_basis") or "")
        if pair.section_id == "S7" and retention_basis:
            ids.append(trial_id)
    return ids


def _trial_ids_for_pair(ws_dir: Path, pair: AssetPair) -> list[str]:
    ids = list(pair.trial_ids)
    if pair.table_id == "T7":
        ids.extend(_retained_trial_ids_from_reference_map(ws_dir, pair))
        ids.extend(_retained_trial_ids_from_sidecars(ws_dir, pair))
    return _ordered_unique(ids)


def _citation_cell(keys: list[str]) -> str:
    return "; ".join(f"[@{key}]" for key in keys)


def _sanitize_manuscript_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    replacements = [
        (r"\bRound-\d+\s+(?:citation-coverage\s+)?repair:\s*", ""),
        (r"\bStage-\d+[A-Za-z]?\s+repair:\s*", ""),
        (r"\bper\s+local\s+plan\b", "in retained evidence"),
        (r"\bper\s+(?:local\s+)?L3/L4\b", "in retained evidence"),
        (r"\bper\s+(?:local\s+)?L3\b", "in retained evidence"),
        (r"\bmatching\s+(?:local\s+)?L4\b", "matching retained full text"),
        (r"\blocal\s+L3/L4\b", "retained evidence"),
        (r"\blocal\s+L3\b", "retained evidence"),
        (r"\blocal\s+L4\b", "retained full text"),
        (r"\blocal\s+spatial\s+platform\b", "retained spatial platform"),
        (r"\bdirect\s+local\s+evidence\b", "direct retained evidence"),
        (r"\blocal\s+text\b", "retained source text"),
        (r"\blocal\s+residual\s+data\b", "retained residual data"),
        (r"\bpublished\s+local\s+evidence\b", "published retained evidence"),
        (r"\bpublished\s+local\s+", "published retained "),
        (r"\bnot\s+used\s+for\s+local\s+claims\b", "not used for evidence-supported claims"),
        (r"\bplanning\s+record\b", "retained evidence"),
        (r"\blocal\s+plan\b", "retained evidence"),
        (r"\bL3/L4\b", "retained evidence"),
        (r"\bL3\b", "retained evidence"),
        (r"\bL4\b", "retained full text"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\bretained evidence identify\b", "retained evidence identifies", text, flags=re.IGNORECASE)
    text = re.sub(r"\bretained evidence show\b", "retained evidence shows", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _chunk(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _evidence_family(record: dict) -> str:
    title = str(record.get("title") or "").lower()
    paper_type = record.get("paper_type") or "paper"
    if paper_type in {"review", "systematic_review", "meta_analysis"}:
        return "Review and consensus context"
    if paper_type in {"methods", "method"}:
        return "Assay, platform, or validation evidence"
    if paper_type in {"clinical_study", "clinical_trial"}:
        if any(term in title for term in ("ctdna", "circulating tumor dna", "minimal residual", "mrd")):
            return "Molecular MRD evidence"
        if any(term in title for term in ("til", "immune", "lymphocyte", "macrophage", "tertiary")):
            return "Residual immune-context evidence"
        return "Clinical pathology and outcome evidence"
    if any(term in title for term in ("spatial", "single-cell", "single cell", "atlas", "ecosystem")):
        return "Spatial tissue-ecosystem evidence"
    if any(term in title for term in ("metabol", "resistance", "genomic", "transcriptomic", "signature", "predict")):
        return "Resistance-program evidence"
    return "Primary translational evidence"


def _decision_role(record: dict) -> str:
    layer = str(record.get("corpus_layer") or "").lower()
    policy = str(record.get("citation_policy") or "").lower()
    if layer == "core" or policy == "must_cite":
        return "Direct anchor"
    if layer == "coverage_support":
        return "Adjacent support"
    if layer == "review_layer" or policy == "background_only":
        return "Context only"
    return "Supporting signal"


def _licensed_use(family: str) -> str:
    if family == "Clinical pathology and outcome evidence":
        return "Supports prognostic or treatment-context claims when the section keeps subtype, endpoint, and assay limits visible."
    if family == "Molecular MRD evidence":
        return "Supports complementary risk-stratification claims; it does not by itself license spatial mechanism or treatment selection."
    if family == "Residual immune-context evidence":
        return "Supports immune-state stratification and prognosis; predictive use requires trial-linked validation."
    if family == "Spatial tissue-ecosystem evidence":
        return "Supports tissue-neighborhood vocabulary and spatial hypotheses; paired pre/post proof remains the decisive test."
    if family == "Resistance-program evidence":
        return "Supports resistant-cell-state and niche hypotheses; causal therapy-selection claims require prospective testing."
    if family == "Assay, platform, or validation evidence":
        return "Supports measurement design, reproducibility, and validation standards rather than biological effect size."
    if family == "Review and consensus context":
        return "Supports terminology, endpoint definitions, and field framing, not new direct empirical claims."
    return "Supports the section claim only within the evidence role assigned by the planning package."


def _interpretive_boundary(family: str) -> str:
    if family == "Clinical pathology and outcome evidence":
        return "Do not generalize beyond the study endpoint, subtype mix, or post-neoadjuvant treatment setting."
    if family == "Molecular MRD evidence":
        return "Do not treat ctDNA clearance or positivity as a validated replacement for tissue pathology without prospective assignment."
    if family == "Residual immune-context evidence":
        return "Do not convert prognostic immune associations into treatment-directive biomarkers unless trial evidence supports that step."
    if family == "Spatial tissue-ecosystem evidence":
        return "Do not infer therapy-induced remodeling unless matched temporal sampling or direct residual tissue evidence is available."
    if family == "Resistance-program evidence":
        return "Do not infer targetability from residual molecular programs without intervention evidence."
    if family == "Assay, platform, or validation evidence":
        return "Do not use technical feasibility as proof of clinical utility."
    if family == "Review and consensus context":
        return "Do not cite as primary evidence for a disputed mechanistic or clinical claim."
    return "Keep the claim inside the section-specific evidence boundary."


def _record_note(record: dict) -> str:
    return _sanitize_manuscript_text(record.get("notes"))


def _source_label(record: dict, key: str) -> str:
    title = _sanitize_manuscript_text(record.get("title") or key).replace("|", "/")
    return f"{title} [@{key}]"


def _guess_subtype(record: dict) -> str:
    text = f"{record.get('title', '')} {_record_note(record)}".lower()
    if "her2-positive" in text or "her2 positive" in text:
        return "HER2-positive"
    if "triple-negative" in text or "tnbc" in text:
        return "TNBC"
    if "her2-negative" in text or "her2 negative" in text:
        return "HER2-negative"
    return "mixed/unspecified breast cancer"


def _guess_sample_state(record: dict) -> str:
    text = f"{record.get('title', '')} {_record_note(record)}".lower()
    if "residual" in text or "post-neoadjuvant" in text or "after neoadjuvant" in text or "after nac" in text:
        return "residual or post-neoadjuvant tissue"
    if "treatment-naive" in text or "pretreatment" in text or "pre-treatment" in text:
        return "pre-treatment biopsy"
    if "through neoadjuvant" in text or "on-treatment" in text:
        return "longitudinal through therapy"
    return "not specified in retained evidence"


def _guess_platform(record: dict) -> str:
    text = f"{record.get('title', '')} {_record_note(record)}".lower()
    if "aqua" in text or "quantitative immunofluorescence" in text:
        return "CD3/CD8/CD20 quantitative immunofluorescence/AQUA"
    if "h&e" in text or "whole-slide" in text or "machine-learning" in text or "machine learning" in text:
        return "H&E whole-slide image machine learning"
    if "geomx" in text or "digital spatial profiling" in text:
        return "GeoMx/DSP spatial profiling"
    if "multiplex immunofluorescence" in text:
        return "multiplex immunofluorescence"
    if "spatial transcript" in text:
        return "spatial transcriptomics"
    if "spatial proteomic" in text:
        return "spatial proteomics"
    if "genomic" in text or "transcriptomic" in text:
        return "genomic/transcriptomic profiling"
    return "platform not specified in retained evidence"


def _directness_tier(record: dict) -> str:
    review_use = str(record.get("review_use") or "")
    role = " ".join(record.get("evidence_role") or []) if isinstance(record.get("evidence_role"), list) else str(record.get("evidence_role") or "")
    layer = str(record.get("corpus_layer") or "")
    if review_use == "taxonomy_boundary":
        return "taxonomy-boundary only"
    if "method" in role or record.get("paper_type") in {"methods", "method"}:
        return "method-only"
    if "adjacent" in role:
        return "adjacent"
    if layer == "core" or "core_evidence" in role:
        return "direct/core"
    if layer == "review_layer":
        return "background"
    return "supporting"


def _allowed_claim(record: dict) -> str:
    note = _record_note(record)
    if note:
        return note
    return _licensed_use(_evidence_family(record))


def _prohibited_overclaim(record: dict) -> str:
    note = _record_note(record)
    if "Do not" in note:
        return note[note.find("Do not") :]
    return _interpretive_boundary(_evidence_family(record))


def _cell_for_column(column: str, key: str, record: dict, pair: AssetPair) -> str:
    normalized = column.strip().lower()
    if normalized == "citekey":
        return f"[@{key}]"
    if normalized in {"paper citekey or registry id", "paper citekey or registry ID".lower()}:
        return f"[@{key}]"
    if normalized in {"source", "evidence base"}:
        return _source_label(record, key)
    if "subtype" in normalized:
        return _guess_subtype(record)
    if "sample" in normalized:
        return _guess_sample_state(record)
    if "platform" in normalized or "assay" in normalized or "method" in normalized:
        return _guess_platform(record)
    if "treatment context" in normalized:
        return "neoadjuvant/post-neoadjuvant context only as specified by source"
    if "endpoint" in normalized:
        return "endpoint as reported by the source; do not infer survival or efficacy if absent"
    if "directness" in normalized or "evidence tier" in normalized:
        return _directness_tier(record)
    if "allowed claim" in normalized or "mechanism supported" in normalized or "actionable status" in normalized:
        return _allowed_claim(record)
    if "prohibited" in normalized or "boundary" in normalized or "uncertainty" in normalized or "decision-grade gap" in normalized:
        return _prohibited_overclaim(record)
    if "program" in normalized or "niche" in normalized or "immune feature" in normalized:
        return _evidence_family(record)
    if "clinical endpoint linkage" in normalized:
        return "clinical endpoint linkage only if reported by source"
    if "cross-platform claim" in normalized:
        return "not licensed unless the source directly compares platforms"
    if "analytic validation" in normalized:
        return "requires reproducibility and external validation"
    if "question" in normalized:
        return _sanitize_manuscript_text(pair.question)
    return _allowed_claim(record)


T2_ROW_FACTS = {
    "Ali2024Spatial": {
        "source type": "review/background framework",
        "tissue state": "pan-cancer spatial-biology context",
        "platform": "platform not specified in retained evidence",
        "transferable vocabulary": "spatial scale, tissue-ecosystem framing, and assay-limitation language",
        "non-transferable claim": "residual breast cancer cohort biology or therapy-induced remodeling",
        "directness tier": "background vocabulary",
        "boundary": "Use for field framing only; do not cite as quantitative or causal residual-disease evidence.",
    },
    "An2024Spatial": {
        "source type": "review/background",
        "tissue state": "breast cancer spatial-transcriptomics literature context",
        "platform": "spatial transcriptomics overview",
        "transferable vocabulary": "terminology for spatial transcriptomics technologies, heterogeneity, and individualized-therapy hypotheses",
        "non-transferable claim": "cohort result, checkpoint-response signal, or post-neoadjuvant residual-disease proof",
        "directness tier": "background only",
        "boundary": "Review only; keep claims at vocabulary and technology-overview level.",
    },
    "Andersson2021Spatial": {
        "source type": "experimental baseline spatial study",
        "tissue state": "baseline HER2-positive breast tumors",
        "platform": "spatial transcriptomics",
        "transferable vocabulary": "tumor-stroma spatial gene-expression gradients and lymphoid-aggregate proximity concepts",
        "non-transferable claim": "therapy-induced remodeling or residual-disease persistence after neoadjuvant treatment",
        "directness tier": "adjacent baseline vocabulary",
        "boundary": "Small HER2-positive baseline cohort; residual use requires direct post-treatment validation.",
    },
    "Hammerl2021Spatial": {
        "source type": "experimental spatial-immunophenotype cohort",
        "tissue state": "pre-treatment TNBC and mixed breast cancer context",
        "platform": "spatial immunophenotyping",
        "transferable vocabulary": "immune-inflamed, immune-excluded, immune-desert, and T-cell-evasion patterns",
        "non-transferable claim": "post-neoadjuvant immune persistence or residual-treatment selection",
        "directness tier": "baseline immune-architecture vocabulary",
        "boundary": "Use for immune-spatial classes; do not treat response or prognosis associations as residual tissue proof.",
    },
    "Klughammer2024Multimodal": {
        "source type": "experimental multimodal atlas",
        "tissue state": "metastatic breast cancer core-needle biopsies",
        "platform": "single-cell and spatial expression profiling",
        "transferable vocabulary": "multimodal cell-state integration and spatial-position mapping",
        "non-transferable claim": "primary post-neoadjuvant residual architecture or treatment-resistant niche identity",
        "directness tier": "adjacent atlas vocabulary",
        "boundary": "Metastatic biopsy atlas; use as a template for analysis, not as residual primary-tumor evidence.",
    },
    "Wu2021Singlecell": {
        "source type": "experimental single-cell/spatial atlas",
        "tissue state": "baseline human breast tumors",
        "platform": "single-cell and spatially resolved profiling",
        "transferable vocabulary": "cellular taxonomy, spatial location maps, and tumor-host coordination motifs",
        "non-transferable claim": "therapy-selected residual cell states or post-treatment spatial reorganization",
        "directness tier": "core baseline atlas vocabulary",
        "boundary": "Use as a testable vocabulary for residual disease; do not assume stability after therapy.",
    },
    "Zhao2023Singlecell": {
        "source type": "computational pathology framework",
        "tissue state": "breast cancer whole-slide-image context",
        "platform": "WSI-based single-cell morphology/topology analysis",
        "transferable vocabulary": "morphological and topological ecosystem descriptors from routine pathology images",
        "non-transferable claim": "molecular spatial identity or validated post-neoadjuvant residual biology",
        "directness tier": "method vocabulary",
        "boundary": "Morphology-derived framework; molecular and residual-disease claims need separate validation.",
    },
}


FIGURE_FOCUS = {
    "F1": "a layered view of pathology endpoints, residual tissue biology, and systemic MRD as non-interchangeable risk layers",
    "F2": "a baseline-to-residual map that separates transferable spatial vocabulary from direct residual-disease proof",
    "F3": "a trajectory map that separates direct residual spatial studies from pretreatment-response and adjacent spatial contexts",
    "F4": "an immune-niche model that distinguishes residual prognostic evidence from pretreatment response association and assay evidence",
    "F5": "a failure-mode map that ranks malignant, stromal, metabolic, and CAF programs by direct residual-disease support",
    "F6": "a two-layer MRD model in which tissue residual disease and systemic assays provide complementary rather than substitutive risk information",
    "F7": "a clinical decision bridge that separates retained treatment-positive evidence, negative outcome evidence, registry-only hypotheses, and acquisition gaps",
    "F8": "a validation workflow that keeps sampling, platform reproducibility, tissue-MRD linkage, and prospective endpoint testing distinct",
}


def _fallback_t2_fact(column: str, key: str, record: dict) -> str:
    normalized = column.strip().lower()
    family = _evidence_family(record)
    if normalized == "citekey":
        return f"[@{key}]"
    if normalized == "source type":
        return family.lower()
    if normalized == "tissue state":
        return _guess_sample_state(record).replace("not specified in retained evidence", "baseline/pre-treatment breast cancer tissue context")
    if normalized == "platform":
        platform = _guess_platform(record)
        if platform == "platform not specified in retained evidence" and "spatial" in family.lower():
            return "single-cell/spatial atlas vocabulary"
        return platform
    if normalized == "transferable vocabulary":
        return "single-cell/spatial atlas vocabulary"
    if normalized == "non-transferable claim":
        return "direct residual-disease, treatment-effect, or therapy-remodeling claim"
    if normalized == "directness tier":
        return _directness_tier(record)
    if normalized == "boundary":
        return "Use only within the source's sampled tissue state and assay scope."
    return _allowed_claim(record)


def _build_t2_table(pair: AssetPair, spec: TableSpec, records: dict[str, dict]) -> str:
    table_number = re.sub(r"\D+", "", pair.table_id) or pair.table_id
    table_title = _sanitize_manuscript_text(pair.table_title)
    headers = [_sanitize_manuscript_text(column) for column in spec.columns]
    lines = [f"#### Table {table_number}. {table_title} ({pair.table_id}/{pair.pair_id})", ""]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for key in pair.citekeys:
        record = records.get(key, {})
        facts = T2_ROW_FACTS.get(key, {})
        cells = []
        for header in headers:
            normalized = header.strip().lower()
            value = f"[@{key}]" if normalized == "citekey" else facts.get(normalized)
            if value is None:
                value = _fallback_t2_fact(header, key, record)
            cells.append(_sanitize_manuscript_text(value).replace("|", "/"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _build_spec_table(
    pair: AssetPair,
    spec: TableSpec,
    records: dict[str, dict],
    contract: TableContract | None = None,
    ws_dir: Path | None = None,
) -> str:
    if pair.table_id == "T2":
        return _build_t2_table(pair, spec, records)
    if contract and pair.table_id != "T7":
        return _render_contract_table(pair, contract)
    table_number = re.sub(r"\D+", "", pair.table_id) or pair.table_id
    table_title = _sanitize_manuscript_text(pair.table_title)
    lines = [f"#### Table {table_number}. {table_title} ({pair.table_id}/{pair.pair_id})", ""]
    headers = [_sanitize_manuscript_text(column) for column in spec.columns]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    if pair.table_id == "T7":
        trial_ids = _trial_ids_for_pair(ws_dir, pair) if ws_dir else pair.trial_ids
        trial_records = _trial_sidecar_records(ws_dir) if ws_dir else {}
        lines.extend(_trial_rows(headers, trial_ids, trial_records))
        return "\n".join(lines)
    for key in pair.citekeys:
        record = records.get(key, {})
        cells = [_sanitize_manuscript_text(_cell_for_column(column, key, record, pair)).replace("|", "/") for column in headers]
        lines.append("| " + " | ".join(cells) + " |")
    if pair.trial_ids:
        for ids in _chunk(pair.trial_ids, 5):
            row = []
            for column in headers:
                normalized = column.strip().lower()
                if "registry" in normalized or "trial" in normalized or "paper citekey" in normalized:
                    row.append(_sanitize_manuscript_text("; ".join(ids)))
                elif "boundary" in normalized:
                    boundary = "Registry-only: no efficacy, survival, or safety conclusion."
                    if "NCT06393374" in ids:
                        boundary += " NCT06393374 has no posted results; treatment effect remains unknown."
                    row.append(_sanitize_manuscript_text(boundary))
                else:
                    row.append("program landscape/status context")
            lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _list_text(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    if value is None:
        return ""
    return str(value)


def _trial_condition_label(record: dict) -> str:
    title = f"{record.get('title') or ''} {record.get('official_title') or ''}".lower()
    conditions = " ".join(record.get("pico", {}).get("P", {}).get("conditions", []) or []).lower()
    text = f"{title} {conditions}"
    if "her2" in text:
        return "HER2-positive residual/non-pCR breast cancer"
    if "triple negative" in text or "tnbc" in text:
        return "TNBC residual/non-pCR breast cancer"
    if "brca" in text or "parp" in text:
        return "gBRCA/HRD-selected high-risk breast cancer"
    return "high-risk residual/non-pCR breast cancer"


def _trial_treatment_label(record: dict) -> str:
    pico = record.get("pico", {})
    interventions = pico.get("I", {}).get("interventions", []) if isinstance(pico, dict) else []
    source = " ".join(interventions) or str(record.get("title") or record.get("official_title") or "")
    lowered = source.lower()
    if "t-dm1" in lowered or "trastuzumab emtansine" in lowered:
        return "T-DM1 post-neoadjuvant registry design"
    if "capecitabine" in lowered and "vinorelbine" in lowered:
        return "capecitabine versus vinorelbine registry design"
    if "capecitabine" in lowered:
        return "capecitabine schedule or combination registry design"
    if "pembrolizumab" in lowered or "pd-1" in lowered or "pd-l1" in lowered:
        return "immunotherapy escalation registry design"
    if "sacituzumab" in lowered or "deruxtecan" in lowered or "adc" in lowered:
        return "ADC escalation registry design"
    return "post-neoadjuvant adjuvant strategy registry design"


def _trial_selection_label(record: dict) -> str:
    pico = record.get("pico", {})
    population = pico.get("P", {}) if isinstance(pico, dict) else {}
    excerpt = str(population.get("eligibility_excerpt") or "")
    title = str(record.get("title") or record.get("official_title") or "")
    text = f"{title} {excerpt}".lower()
    if "residual invasive" in text:
        return "residual invasive disease after neoadjuvant therapy"
    if "non-pcr" in text or "non pcr" in text:
        return "non-pCR after neoadjuvant therapy"
    if "pathologic residual" in text or "pathological residual" in text:
        return "pathologic residual tumor after preoperative chemotherapy"
    return "registry-defined high-risk residual/non-pCR selection"


def _trial_comparator_label(record: dict) -> str:
    pico = record.get("pico", {})
    if not isinstance(pico, dict):
        return "registry-defined comparator or cohort structure"
    comparator = pico.get("C", {}).get("summary") if isinstance(pico.get("C"), dict) else ""
    arms = pico.get("I", {}).get("arms", []) if isinstance(pico.get("I"), dict) else []
    labels = [str(arm.get("label")) for arm in arms if isinstance(arm, dict) and arm.get("label")]
    if labels:
        return " versus ".join(labels[:3])
    if comparator:
        return str(comparator)
    return "registry-defined comparator or cohort structure"


def _trial_endpoint_label(record: dict) -> str:
    pico = record.get("pico", {})
    outcomes = pico.get("O", {}) if isinstance(pico, dict) else {}
    primary = outcomes.get("primary_endpoints", []) if isinstance(outcomes, dict) else []
    measures = [str(item.get("measure")) for item in primary if isinstance(item, dict) and item.get("measure")]
    if measures:
        return "; ".join(measures[:2]) + "; registry endpoint only, no result inferred"
    return "registry-defined endpoint only, no result inferred"


def _registry_trial_item(trial_id: str, record: dict | None) -> dict[str, str]:
    record = record or {}
    overrides = {
        "NCT01772472": {
            "Subtype": "HER2-positive residual invasive disease",
            "treatment class": "retained initial KATHERINE T-DM1 evidence",
            "biomarker": "residual invasive disease after neoadjuvant taxane/trastuzumab-based therapy",
            "comparator": "T-DM1 versus trastuzumab",
            "endpoint": "retained IDFS treatment-effect evidence from initial paper; registry endpoint context only",
            "status": "completed; PHASE3; linked retained KATHERINE initial paper",
            "boundary": "NCT01772472 is registry metadata linked to vonMinckwitz2019Trastuzumab; do not use it for final OS/IDFS update claims.",
            "source": "[@vonMinckwitz2019Trastuzumab]; NCT01772472",
        },
        "NCT04595565": {
            "Subtype": "HER2-negative/TNBC",
            "treatment class": "SASCIA sacituzumab govitecan registry design",
            "biomarker": "post-neoadjuvant high-risk primary HER2-negative breast cancer",
            "comparator": "sacituzumab govitecan versus treatment of physician's choice",
            "endpoint": "registry-defined iDFS endpoint only, no result inferred",
            "status": "active not recruiting; PHASE3; registry-only/no posted results",
            "boundary": "Registry/status/design row only; no sacituzumab govitecan iDFS efficacy claim.",
            "source": "NCT04595565",
        },
        "NCT06966700": {
            "Subtype": "adjacent neoadjuvant high-risk TNBC or HR-low/HER2-negative breast cancer",
            "treatment class": "MK-2870-032 sacituzumab tirumotecan program",
            "biomarker": "neoadjuvant high-risk early TNBC or HR-low/HER2-negative context, not HER2-positive residual disease",
            "comparator": "sac-TMT versus chemotherapy",
            "endpoint": "registry-defined pCR/EFS endpoints only, no result inferred",
            "status": "recruiting; PHASE3; registry-only/no posted results",
            "boundary": "Adjacent landscape/status row only; do not render as HER2-positive residual/non-pCR treatment.",
            "source": "NCT06966700",
        },
    }
    if trial_id in overrides:
        return overrides[trial_id]
    phase = _list_text(record.get("phase")) or "phase not specified"
    status = str(record.get("status") or "registry-only").lower().replace("_", " ")
    return {
        "Subtype": _trial_condition_label(record) if record else "additional registry landscape",
        "treatment class": _trial_treatment_label(record) if record else "active or completed program not yet linked to retained result paper",
        "biomarker": _trial_selection_label(record) if record else "program landscape context",
        "comparator": _trial_comparator_label(record) if record else "program landscape context",
        "endpoint": _trial_endpoint_label(record) if record else "registry-defined endpoint only, no result inferred",
        "status": f"{status}; {phase}; registry-only/no retained outcome paper",
        "boundary": "Registry-only row from retained S7/P7 records: use for design, status, selection, comparator, and endpoint context only; no efficacy, safety, survival, approval, or comparative treatment-effect conclusion.",
        "source": trial_id,
    }


def _registry_family_key(item: dict[str, str]) -> str:
    text = " ".join(item.values()).lower()
    if "her2-positive" in text and (
        "t-dm1" in text or "trastuzumab emtansine" in text or "adc" in text or "a1811" in text or "bl-m07d1" in text
    ):
        return "HER2-positive ADC/T-DM1 comparator registry family"
    if "sacituzumab" in text or "adc" in text or "sac-tmt" in text or "deruxtecan" in text:
        return "TNBC/HER2-negative ADC escalation registry family"
    if (
        "pembrolizumab" in text
        or "atezolizumab" in text
        or "camrelizumab" in text
        or "pd-1" in text
        or "pd-l1" in text
        or "immunoscore" in text
        or "tls" in text
    ):
        return "TNBC immunotherapy/immune-selection registry family"
    if (
        "capecitabine" in text
        or "vinorelbine" in text
        or "cisplatin" in text
        or "gemcitabine" in text
        or "utd1" in text
        or "utidelone" in text
        or "tetrathiomolybdate" in text
    ):
        return "Capecitabine/cytotoxic optimization registry family"
    if "ctdna" in text or "mrd" in text or "genomic" in text:
        return "Molecularly selected MRD/genomics registry family"
    return "Other residual-disease registry family"


def _registry_family_rows(remaining: list[str], trial_records: dict[str, dict], headers: list[str]) -> list[str]:
    families: dict[str, list[dict[str, str]]] = {}
    for trial_id in remaining:
        item = _registry_trial_item(trial_id, trial_records.get(trial_id))
        item["source"] = trial_id
        families.setdefault(_registry_family_key(item), []).append(item)
    rows: list[str] = []
    for family, items in sorted(families.items()):
        ids = [item["source"] for item in items]
        statuses = sorted({_sanitize_manuscript_text(item["status"]) for item in items if item.get("status")})
        subtype = "residual/non-pCR breast cancer registry family"
        if family.startswith("HER2-positive"):
            subtype = "HER2-positive residual/non-pCR breast cancer"
        elif family.startswith("TNBC") or family.startswith("Capecitabine"):
            subtype = "TNBC or HER2-negative residual/non-pCR breast cancer"
        endpoint = "registry-defined iDFS/DFS/EFS/pCR, ctDNA, or safety endpoints; no result inferred"
        comparator = "protocol-specific active comparator, physician's choice, placebo/control, or single-arm design"
        claim_license = "Use for registry landscape and trial-design context only."
        boundary = "Registry-only grouping; no efficacy, safety, survival, approval, or comparative treatment-effect conclusion."
        row_values = {
            "subtype": subtype,
            "treatment class": family,
            "biomarker": "registry-defined residual/non-pCR, immune-selected, HER2-positive, ADC, MRD, or high-risk eligibility as specified by protocol",
            "comparator": comparator,
            "endpoint": endpoint,
            "claim_license": claim_license,
            "status": "; ".join(statuses[:4]) if statuses else "registry-only/no retained outcome paper",
            "boundary": boundary,
            "source": "; ".join(ids),
        }
        cells = []
        for header in headers:
            normalized = header.lower()
            if "retained paper" in normalized or "source" in normalized or normalized == "trial":
                value = row_values["source"]
            elif "population" in normalized or "subtype" in normalized:
                value = row_values["subtype"]
            elif "entry criterion" in normalized or "biomarker" in normalized or "mrd" in normalized:
                value = row_values["biomarker"]
            elif "intervention" in normalized or "treatment class" in normalized:
                value = row_values["treatment class"]
            elif "comparator" in normalized:
                value = row_values["comparator"]
            elif "endpoint" in normalized:
                value = row_values["endpoint"]
            elif "status" in normalized or "recruitment" in normalized:
                value = row_values["status"]
            elif "claim license" in normalized:
                value = row_values["claim_license"]
            elif "boundary" in normalized or "currentness" in normalized or "registry" in normalized:
                value = row_values["boundary"]
            else:
                value = row_values["boundary"]
            cells.append(_sanitize_manuscript_text(value))
        rows.append("| " + " | ".join(cells) + " |")
    return rows


def _trial_rows(headers: list[str], trial_ids: list[str], trial_records: dict[str, dict] | None = None) -> list[str]:
    taxonomy = [
        {
            "Subtype": "TNBC residual disease after NACT",
            "treatment class": "biomarker-risk bridge evidence, not treatment standard",
            "biomarker": "immune transcriptomic signature in post-NACT residual samples",
            "comparator": "not a treatment comparator; residual immune-risk stratification evidence",
            "endpoint": "relapse-free survival / metastatic relapse risk association",
            "status": "published local prognostic bridge evidence",
            "boundary": "Use to explain residual TNBC immune-risk stratification before trials; do not present as a validated assay or treatment assignment rule.",
            "source": "[@Blaye2022Immunological]",
        },
        {
            "Subtype": "HER2-positive residual disease after NAT",
            "treatment class": "biomarker-risk bridge evidence, not randomized escalation standard",
            "biomarker": "residual ER/PR/HER2/Ki-67 and clinicopathologic factors",
            "comparator": "not a randomized treatment comparator; residual biomarker prognosis evidence",
            "endpoint": "DFS prognostic association",
            "status": "published local prognostic bridge evidence",
            "boundary": "Use to separate HER2-positive residual biomarker prognosis from KATHERINE/T-DM1 treatment-effect evidence; do not treat receptor change as a validated assignment rule.",
            "source": "[@Ma2023Impact]",
        },
        {
            "Subtype": "HER2-positive residual disease after anti-HER2 chemotherapy-based NAT",
            "treatment class": "biomarker-risk bridge evidence, not randomized escalation standard",
            "biomarker": "RCB plus RD-TIL composite risk score on residual surgical samples",
            "comparator": "not a randomized treatment comparator; residual composite risk evidence",
            "endpoint": "OS prognostic association",
            "status": "published local prognostic bridge evidence",
            "boundary": "Use to show HER2-positive residual RCB+RD-TIL prognosis may differ from TNBC; do not present as adjuvant treatment assignment evidence.",
            "source": "[@Miglietta2023Prognostic]",
        },
        {
            "Subtype": "HER2-positive residual disease after neoadjuvant HER2 blockade",
            "treatment class": "biomarker-risk bridge evidence, not randomized escalation standard",
            "biomarker": "residual-disease immune/gene-expression signatures across HER2-blockade studies",
            "comparator": "not a randomized treatment comparator; residual immune/gene-expression prognosis evidence",
            "endpoint": "EFS prognostic model / RD immune-signature association",
            "status": "published local prognostic bridge evidence",
            "boundary": "Use to explain HER2-positive residual immune and gene-expression prognosis; do not present as TNBC evidence or a validated treatment-assignment rule.",
            "source": "[@FernandezMartinez2025Prognostic]",
        },
        {
            "Subtype": "TNBC / HER2-negative residual disease",
            "treatment class": "retained capecitabine evidence",
            "biomarker": "residual invasive disease after preoperative chemotherapy",
            "comparator": "observation or non-capecitabine control in source trial context",
            "endpoint": "survival endpoints from retained paper",
            "status": "published local evidence",
            "boundary": "CREATE-X supports capecitabine context; do not generalize to all post-pembrolizumab residual TNBC.",
            "source": "[@Masuda2017Adjuvant]",
        },
        {
            "Subtype": "TNBC residual disease after NAC",
            "treatment class": "platinum versus capecitabine outcome comparison",
            "biomarker": "residual invasive TNBC; PAM50 basal/nonbasal in residual disease",
            "comparator": "platinum (carboplatin/cisplatin) versus capecitabine",
            "endpoint": "3-year invasive disease-free survival / early futility / grade 3-4 toxicity",
            "status": "retained full-text EA1131 outcome paper",
            "boundary": "Use only for residual TNBC post-NAC EA1131 comparison; do not generalize to all platinum use or neoadjuvant platinum benefit.",
            "source": "[@Mayer2021Randomized]; NCT02445391",
        },
        {
            "Subtype": "HER2-positive residual invasive disease",
            "treatment class": "retained initial KATHERINE T-DM1 evidence",
            "biomarker": "residual invasive disease after HER2-directed neoadjuvant therapy",
            "comparator": "T-DM1 versus trastuzumab",
            "endpoint": "invasive disease-free survival from retained initial paper; registry endpoint context only",
            "status": "published retained KATHERINE initial paper plus linked registry design",
            "boundary": "Published initial T-DM1 evidence is separate from abstract-only final KATHERINE and registry-only T-DXd/atezolizumab hypotheses.",
            "source": "[@vonMinckwitz2019Trastuzumab]; NCT01772472",
        },
        {
            "Subtype": "gBRCA1/2 high-risk HER2-negative early breast cancer",
            "treatment class": "PARP/HRD strategy",
            "biomarker": "germline BRCA for OlympiA; HRD/platinum response is separate",
            "comparator": "olaparib versus placebo; PARPi/PD-1 registry hypotheses",
            "endpoint": "OS/IDFS/DDFS for retained OlympiA update; registry endpoints for active studies",
            "status": "published local OlympiA update plus active registry trials",
            "boundary": "Telli supports HRD/platinum neoadjuvant response, not adjuvant olaparib benefit.",
            "source": "[@Geyer2022Overall]; [@Telli2016Homologous]; NCT02032823; NCT06533384",
        },
        {
            "Subtype": "Early TNBC in KEYNOTE-522 pCR-era evidence",
            "treatment class": "neoadjuvant/adjuvant pembrolizumab regimen context",
            "biomarker": "stage II/III TNBC; not a residual-disease-only selection marker",
            "comparator": "pembrolizumab-containing regimen versus placebo-containing regimen",
            "endpoint": "pCR-era retained paper endpoint context only",
            "status": "retained KEYNOTE-522 pCR-era paper",
            "boundary": "Use Schmid2020Pembrolizumab only for pCR-era context; do not cite it for later EFS/OS or residual escalation results.",
            "source": "[@Schmid2020Pembrolizumab]; NCT03036488",
        },
        {
            "Subtype": "KEYNOTE-522 currentness gap",
            "treatment class": "immunotherapy outcome update",
            "biomarker": "stage II/III TNBC in KEYNOTE-522 publication stream",
            "comparator": "not used for local claims",
            "endpoint": "OS publication PMID 39282906",
            "status": "abstract-only/non-citable until full text retained; do not claim results",
            "boundary": "List as acquisition/currentness gap only; no OS direction or magnitude may be stated.",
            "source": "PMID 39282906",
        },
        {
            "Subtype": "KEYNOTE-522 currentness gap",
            "treatment class": "residual cancer burden / EFS update",
            "biomarker": "RCB categories in KEYNOTE-522 publication stream",
            "comparator": "not used for local claims",
            "endpoint": "EFS/RCB publication PMID 38369015",
            "status": "abstract-only/non-citable until full text retained; do not claim results",
            "boundary": "List as acquisition/currentness gap only; no EFS or RCB result claim may be stated.",
            "source": "PMID 38369015",
        },
        {
            "Subtype": "HER2-positive currentness gap",
            "treatment class": "KATHERINE final outcome update",
            "biomarker": "residual invasive HER2-positive disease after neoadjuvant therapy",
            "comparator": "not used for local claims",
            "endpoint": "final OS/IDFS publication PMID 39813643",
            "status": "abstract-only/non-citable until full text retained; do not claim results",
            "boundary": "List as acquisition/currentness gap only; use retained KATHERINE initial paper for citable T-DM1 claims.",
            "source": "PMID 39813643",
        },
        {
            "Subtype": "HER2-positive currentness gap",
            "treatment class": "T-DXd versus T-DM1 successor outcome update",
            "biomarker": "high-risk HER2-positive early breast cancer after neoadjuvant therapy",
            "comparator": "not used for local claims",
            "endpoint": "DESTINY-Breast05 DOI 10.1056/NEJMoa2514661 / PMID 41370739",
            "status": "abstract-only/non-citable until full text retained; do not claim results",
            "boundary": "List as acquisition/currentness gap only; registry and abstract-only records cannot support treatment-effect claims.",
            "source": "DOI 10.1056/NEJMoa2514661; PMID 41370739; NCT04622319",
        },
        {
            "Subtype": "molecularly selected residual disease",
            "treatment class": "MRD/genomics-guided intervention",
            "biomarker": "ctDNA/MRD, genomic target, or HER2 MRD selection",
            "comparator": "protocol-specific targeted or standard strategy",
            "endpoint": "registry-defined endpoint; no treatment effect from registry status",
            "status": "active registry-only or design landscape",
            "boundary": "Use for decision-architecture context only until results are retained locally.",
            "source": "[@PenaultLlorca2016Biomarkers]; NCT05332561; NCT05388149",
        },
        {
            "Subtype": "TNBC residual/non-pCR after chemo-immunotherapy",
            "treatment class": "immunotherapy continuation/escalation",
            "biomarker": "residual disease/non-pCR after neoadjuvant therapy",
            "comparator": "protocol-specific pembrolizumab, capecitabine, or active control",
            "endpoint": "registry-defined iDFS/EFS endpoints",
            "status": "registry-only; no retained outcome paper",
            "boundary": "Use only for design, status, selection, comparator, and endpoint context.",
            "source": "NCT02954874; NCT07486687",
        },
        {
            "Subtype": "TNBC residual/non-pCR ADC programs",
            "treatment class": "ADC escalation",
            "biomarker": "residual invasive disease/non-pCR; protocol-specific eligibility",
            "comparator": "physician's choice, capecitabine, pembrolizumab/capecitabine, or active control",
            "endpoint": "registry-defined iDFS/EFS endpoints",
            "status": "registry-only; active or completed program landscape",
            "boundary": "NCT06393374 has no posted results in retained evidence; registry status is not efficacy evidence.",
            "source": "NCT05633654; NCT06393374",
        },
    ]
    rows: list[str] = []
    for item in taxonomy:
        cells = []
        for header in headers:
            normalized = header.lower()
            if "retained paper" in normalized or "source" in normalized or normalized == "trial":
                value = item["source"]
            elif "population" in normalized or "subtype" in normalized:
                value = item["Subtype"]
            elif "entry criterion" in normalized or "biomarker" in normalized or "mrd" in normalized:
                value = item["biomarker"]
            elif "intervention" in normalized or "treatment class" in normalized:
                value = item["treatment class"]
            elif "comparator" in normalized:
                value = item["comparator"]
            elif "endpoint" in normalized:
                value = item["endpoint"]
            elif "claim license" in normalized:
                value = item["boundary"]
            elif "currentness" in normalized or "registry" in normalized:
                value = item["status"]
            elif "status" in normalized or "recruitment" in normalized:
                value = item["status"]
            elif "boundary" in normalized:
                value = item["boundary"]
            else:
                value = item["boundary"]
            cells.append(_sanitize_manuscript_text(value).replace("|", "/"))
        rows.append("| " + " | ".join(cells) + " |")
    trial_records = trial_records or {}
    mentioned = set(re.findall(r"NCT\d{8}", "\n".join(row for row in rows)))
    remaining = [trial_id for trial_id in trial_ids if trial_id not in mentioned]
    if remaining:
        rows.extend(_registry_family_rows(remaining, trial_records, headers))
    return rows


def _group_records(pair: AssetPair, records: dict[str, dict]) -> dict[tuple[str, str], list[str]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for key in pair.citekeys:
        record = records.get(key, {})
        family = _evidence_family(record)
        role = _decision_role(record)
        grouped.setdefault((family, role), []).append(key)
    return grouped


def _build_table(
    pair: AssetPair,
    records: dict[str, dict],
    spec: TableSpec | None = None,
    contract: TableContract | None = None,
    ws_dir: Path | None = None,
) -> str:
    if spec:
        return _build_spec_table(pair, spec, records, contract, ws_dir)
    if contract and pair.table_id != "T7":
        return _render_contract_table(pair, contract)
    table_number = re.sub(r"\D+", "", pair.table_id) or pair.table_id
    table_title = _sanitize_manuscript_text(pair.table_title)
    lines = [
        f"#### Table {table_number}. {table_title} ({pair.table_id}/{pair.pair_id})",
        "",
        "| Question adjudicated | Evidence base | What the evidence licenses | Boundary for interpretation |",
        "|---|---|---|---|",
    ]
    grouped = _group_records(pair, records)
    for (family, role), keys in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        for key_chunk in _chunk(keys, 10):
            evidence = f"{family}; {role}: {_citation_cell(key_chunk)}"
            lines.append(
                f"| {_sanitize_manuscript_text(pair.question)} | {evidence} | {_licensed_use(family)} | {_interpretive_boundary(family)} |"
            )
    trial_ids = _trial_ids_for_pair(ws_dir, pair) if ws_dir else pair.trial_ids
    if trial_ids:
        for ids in _chunk(trial_ids, 5):
            label = "; ".join(ids)
            boundary = "Registry status does not establish efficacy, survival benefit, or safety benefit."
            if "NCT06393374" in ids:
                boundary += " NCT06393374 has no posted results in the retained trial sidecar; treatment effect remains unknown."
            lines.append(
                f"| {_sanitize_manuscript_text(pair.question)} | Registry landscape evidence: {label} | Supports program, phase, recruitment, and endpoint context only. | {boundary} |"
            )
    return "\n".join(lines)


def _build_figure_reference(pair: AssetPair, ws_dir: Path | None = None) -> str:
    figure_number = re.sub(r"\D+", "", pair.figure_id) or pair.figure_id
    table_number = re.sub(r"\D+", "", pair.table_id) or pair.table_id
    citation_tail = _citation_cell(pair.citekeys[:8])
    figure_title = _sanitize_manuscript_text(pair.figure_title)
    focus = FIGURE_FOCUS.get(pair.figure_id, "a visual synthesis of the paired evidence tiers and interpretation boundaries")
    citation_sentence = f" Key sources include {citation_tail}." if citation_tail else ""
    trial_note = ""
    trial_ids = _trial_ids_for_pair(ws_dir, pair) if ws_dir else pair.trial_ids
    if trial_ids:
        trial_note = (
            " Registry identifiers are used only for design, status, comparator, and endpoint context: "
            + "; ".join(trial_ids)
            + "."
        )
    return (
        f"**Figure {figure_number} ({pair.figure_id}/{pair.pair_id}). {figure_title}.** "
        f"The schematic condenses Table {table_number} into {focus}."
        f"{citation_sentence}{trial_note}"
    )


def _remove_bold_table_blocks(section_text: str) -> str:
    lines = section_text.splitlines()
    cleaned: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if re.match(r"^\*\*Table\s+\d+\.", line.strip()):
            index += 1
            while index < len(lines) and not lines[index].lstrip().startswith("|"):
                index += 1
            if index < len(lines) and lines[index].lstrip().startswith("|"):
                index += 1
                while index < len(lines) and lines[index].lstrip().startswith("|"):
                    index += 1
            while cleaned and not cleaned[-1].strip():
                cleaned.pop()
            continue
        cleaned.append(line)
        index += 1
    return "\n".join(cleaned)


def _remove_plan_only_tables(section_text: str) -> str:
    lines = section_text.splitlines()
    cleaned: list[str] = []
    index = 0
    plan_headers = (
        "| Figure ID | Paired Table ID |",
        "| Evidence lane | Required rows | Boundary |",
    )
    while index < len(lines):
        line = lines[index]
        if any(line.startswith(header) for header in plan_headers):
            index += 1
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                index += 1
            while cleaned and not cleaned[-1].strip():
                cleaned.pop()
            continue
        cleaned.append(line)
        index += 1
    return "\n".join(cleaned)


def _strip_asset_blocks(section_text: str) -> str:
    pattern = re.escape(ASSET_START) + r".*?" + re.escape(ASSET_END)
    section_text = re.sub(pattern, "", section_text, flags=re.DOTALL).rstrip()
    section_text = _remove_bold_table_blocks(section_text).rstrip()
    section_text = _remove_plan_only_tables(section_text).rstrip()
    section_text = re.sub(r"\n+####\s+(?:T\d+\.|Table\s+\d+\.|Table\s+[A-Za-z0-9_-]+\.).*\Z", "", section_text, flags=re.DOTALL).rstrip()
    return section_text


def _section_pattern(section_id: str) -> str:
    return rf"(^###\s+{re.escape(section_id)}\s*[:.].*?)(?=^###\s+S\d+[A-Za-z0-9_-]*\s*[:.]|\Z)"


def _kernel_order(ws_dir: Path) -> list[str]:
    rows = read_jsonl(ws_dir / "sidecars" / "section-kernels.jsonl")
    return [row["section_id"] for row in rows if row.get("section_id")]


def _normalize_section_headings(text: str, ws_dir: Path) -> str:
    rows = read_jsonl(ws_dir / "sidecars" / "section-kernels.jsonl")
    headings = list(re.finditer(r"^#{2,3}\s+(?!T\d+\b).*$", text, flags=re.MULTILINE))
    for index, row in reversed(list(enumerate(rows[: len(headings)]))):
        section_id = row.get("section_id") or f"S{index + 1}"
        title = row.get("title") or row.get("section_id") or headings[index].group(0).lstrip("#").strip()
        start, end = headings[index].span()
        text = text[:start] + f"### {section_id}: {title}" + text[end:]
    return text


def _current_sections(text: str, ws_dir: Path) -> dict[str, str]:
    kernels = _kernel_order(ws_dir)
    matches = list(re.finditer(r"^#{2,3}\s+.*$", text, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for index, section_id in enumerate(kernels[: len(matches)]):
        start = matches[index].start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[section_id] = text[start:end].strip()
    return sections


def _refresh_selected_pattern_report(ws_dir: Path, text: str) -> dict:
    contracts = load_section_contracts(ws_dir)
    sections = _current_sections(text, ws_dir)
    results = []
    for section_id, section_text in sections.items():
        contract = contracts.get(section_id)
        if not contract:
            continue
        result = evaluate_pattern_contract(section_text, contract)
        result.candidate_id = f"{section_id}.selected"
        results.append(result)
    score_path = ws_dir / "sidecars" / "pattern-scores.jsonl"
    if score_path.exists():
        history_path = ws_dir / "sidecars" / "pattern-scores.history.jsonl"
        if not history_path.exists():
            write_text(history_path, read_text(score_path))
    write_jsonl(score_path, [result.to_dict() for result in results])
    qa_dir = ws_dir / "qa" / "write-agent"
    qa_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# WriteAgent Pattern Report", "", "Selected integrated manuscript sections:"]
    for result in results:
        lines.append(f"- {result.section_id}: {result.status}")
        if result.missing_required_moves:
            lines.append(f"  missing moves: {', '.join(result.missing_required_moves)}")
        hard_flags = [flag["id"] for flag in result.anti_ai_flags if flag.get("severity") == "hard"]
        if hard_flags:
            lines.append("  hard flags: " + ", ".join(hard_flags))
    write_text(qa_dir / "pattern-report.md", "\n".join(lines) + "\n")
    return {
        "sections": [result.section_id for result in results],
        "hard_failures": [result.section_id for result in results if result.hard_fail],
    }


def _write_integration_report(ws_dir: Path, text: str, pairs: list[str], pattern_state: dict) -> None:
    qa_dir = ws_dir / "qa" / "write-agent"
    qa_dir.mkdir(parents=True, exist_ok=True)
    cite_count = len(set(extract_citekeys(text)))
    lines = [
        "# WriteAgent Write Report",
        "",
        "Status: WRITE_READY_FOR_EXTERNAL_CRITIC",
        "",
        f"- Unique manuscript citekeys: {cite_count}",
        f"- Integrated table/figure pairs: {', '.join(pairs)}",
        f"- Selected-section pattern hard failures: {len(pattern_state.get('hard_failures', []))}",
        "- Deterministic asset integration removed AutoR section comments and planning-only table labels.",
        "- Historical candidate pattern scores, if present, are archived in `sidecars/pattern-scores.history.jsonl`; `pattern-scores.jsonl` describes the selected integrated manuscript surface.",
    ]
    write_text(qa_dir / "write-report.md", "\n".join(lines) + "\n")


def _replace_section_by_order(text: str, ws_dir: Path, section_id: str, block: str) -> tuple[str, int]:
    order = _kernel_order(ws_dir)
    if section_id not in order:
        return text, 0
    index = order.index(section_id)
    matches = list(re.finditer(r"^#{2,3}\s+.*$", text, flags=re.MULTILINE))
    if index >= len(matches):
        return text, 0
    start = matches[index].start()
    end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
    section = _strip_asset_blocks(text[start:end])
    return text[:start] + section + block + "\n" + text[end:], 1


def strip_autor_section_comments(text: str) -> str:
    text = re.sub(r"<!--\s*AUTOR:SECTION\s+[A-Za-z0-9_-]+\s+START\s*-->\n?", "", text)
    text = re.sub(r"\n?<!--\s*AUTOR:SECTION\s+[A-Za-z0-9_-]+\s+END\s*-->", "", text)
    text = re.sub(r"\n?<!--\s*AUTOR:[^>]*-->\n?", "\n", text)
    return text


def normalize_workflow_scaffolding(text: str) -> str:
    """Remove write-agent process vocabulary from the manuscript surface."""
    replacements = {
        "the evidence packet": "the retained evidence",
        "The evidence packet": "The retained evidence",
        "evidence packet": "retained evidence",
        "Evidence packet": "Retained evidence",
        "a plasma metabolomic signature of fatty-acid and nucleotide metabolism was associated with survival in early breast cancer [@Talarico2024Metabolomic]": "plasma metabolomic variation was associated with disease-free and overall survival in breast cancer [@Talarico2024Metabolomic]",
        "The ongoing trials that are testing ctDNA-MRD as a treatment selection biomarker (e.g., DETECT, TRACER-RB) have not yet reported results.": "Prospective trials testing ctDNA-MRD as a treatment-selection biomarker have not yet supplied retained outcome evidence.",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def integrate_assets(ws_dir: Path) -> dict:
    """Insert required table/figure/trial assets into a complete write.md surface."""
    write_path = ws_dir / "write.md"
    text = strip_autor_section_comments(read_text(write_path))
    text = normalize_workflow_scaffolding(text)
    text = _normalize_section_headings(text, ws_dir)
    if "_Draft pending._" in text:
        return {"status": "SKIPPED_PENDING_SECTIONS"}
    table_plan = read_text(ws_dir / "table-figure-plan.md")
    pairs = _parse_pair_matrix(table_plan)
    specs = _parse_table_specs(table_plan)
    contracts = _parse_analytic_contracts(table_plan)
    records = _reference_records(ws_dir)
    inserted: list[str] = []
    for pair in pairs:
        if not pair.section_id:
            continue
        block = (
            f"\n\n{_build_table(pair, records, specs.get(pair.table_id), contracts.get(pair.table_id), ws_dir)}"
            f"\n\n{_build_figure_reference(pair, ws_dir)}\n"
        )
        text, count = _replace_section_by_order(text, ws_dir, pair.section_id, block)
        if count:
            inserted.append(pair.pair_id)
    write_text(write_path, text.rstrip() + "\n")
    pattern_state = _refresh_selected_pattern_report(ws_dir, text)
    _write_integration_report(ws_dir, text, inserted, pattern_state)
    state = read_state(ws_dir)
    for stale_key in ("error", "section_id", "unresolved_sections", "revised_sections"):
        state.pop(stale_key, None)
    state.update(
        {
            "status": "WRITE_READY_FOR_EXTERNAL_CRITIC",
            "failed_stage": "none",
            "cause_class": "none",
            "next_action": "continue",
            "asset_integration": {
                "status": "ASSETS_INTEGRATED",
                "pairs": inserted,
                "selected_pattern_hard_failures": pattern_state.get("hard_failures", []),
            },
        }
    )
    write_state(ws_dir, state)
    return {"status": "ASSETS_INTEGRATED", "pairs": inserted}
