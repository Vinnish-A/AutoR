"""Build section kernels from canonical planning files."""

from __future__ import annotations

import re
import json
from pathlib import Path

import yaml

from autor.write_agent.models import SectionKernel
from autor.write_agent.preflight import infer_main_sections
from autor.write_agent.workspace_io import extract_citekeys, read_text, sidecars_dir, write_jsonl, write_text


def _section_blocks(review_plan: str) -> list[tuple[str, str, str]]:
    matches = list(re.finditer(r"^(#{1,4})\s+.*?\b(S\d+[A-Za-z0-9_-]*)\b.*$", review_plan, flags=re.MULTILINE))
    if not matches:
        return [("S1", "Main section", review_plan)]
    blocks: list[tuple[str, str, str]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(review_plan)
        line = match.group(0).lstrip("#").strip()
        section_id = match.group(2)
        title = re.sub(r"\b" + re.escape(section_id) + r"\b[:：-]?", "", line).strip() or section_id
        blocks.append((section_id, title, review_plan[start:end].strip()))
    return blocks


def _first_sentence(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""
    match = re.search(r"(.{40,240}?[.!?。！？])\s", compact + " ")
    return match.group(1).strip() if match else compact[:220]


def _planned_assets(table_plan: str, section_id: str) -> tuple[list[str], list[str]]:
    tables: list[str] = []
    figures: list[str] = []
    for line in table_plan.splitlines():
        if section_id not in line:
            continue
        tables.extend(re.findall(r"\b(T\d+[A-Za-z0-9_-]*)\b", line))
        figures.extend(re.findall(r"\b(F\d+[A-Za-z0-9_-]*)\b", line))
    return list(dict.fromkeys(tables)), list(dict.fromkeys(figures))


def _reference_roles(ws_dir: Path) -> dict[str, dict]:
    path = ws_dir / "reference-map.json"
    if not path.exists():
        return {}
    data = json.loads(read_text(path))
    records = data.get("references", []) if isinstance(data, dict) else data
    return {str(record.get("citekey", "")): record for record in records if record.get("citekey")}


def _split_evidence_keys(section_keys: list[str], records: dict[str, dict]) -> tuple[list[str], list[str], list[str]]:
    direct: list[str] = []
    adjacent: list[str] = []
    background: list[str] = []
    for key in section_keys:
        record = records.get(key, {})
        paper_type = str(record.get("paper_type") or "").lower()
        review_use = str(record.get("review_use") or "").lower()
        citation_policy = str(record.get("citation_policy") or "").lower()
        role = " ".join(record.get("evidence_role") or []) if isinstance(record.get("evidence_role"), list) else str(record.get("evidence_role") or "")
        if review_use == "background_only" or citation_policy == "background_only" or paper_type in {"review", "systematic_review", "meta_analysis"}:
            background.append(key)
        elif "adjacent" in role or "method" in role or review_use in {"method_source", "taxonomy_boundary"}:
            adjacent.append(key)
        elif record.get("corpus_layer") == "core" or citation_policy == "must_cite" or "core_evidence" in role:
            direct.append(key)
        else:
            adjacent.append(key)
    if not direct and section_keys:
        direct = section_keys[: max(1, min(4, len(section_keys)))]
        adjacent = [key for key in section_keys if key not in direct and key not in background]
    return direct, adjacent, background


def build_kernels(ws_dir: Path) -> list[SectionKernel]:
    review_plan = read_text(ws_dir / "review-plan.md")
    evidence = read_text(ws_dir / "evidence-ledger.md")
    table_plan = read_text(ws_dir / "table-figure-plan.md")
    blocks = _section_blocks(review_plan)
    if not blocks:
        blocks = [(sid, sid, "") for sid in infer_main_sections(review_plan)]
    kernels: list[SectionKernel] = []
    all_evidence_keys = extract_citekeys(evidence)
    records = _reference_roles(ws_dir)
    for section_id, title, body in blocks:
        section_keys = extract_citekeys(body) or all_evidence_keys[:8]
        tables, figures = _planned_assets(table_plan, section_id)
        direct, adjacent, background = _split_evidence_keys(section_keys, records)
        kernel = SectionKernel(
            section_id=section_id,
            title=title,
            controlling_claim=_first_sentence(body) or f"{title} requires evidence-led adjudication.",
            evidence_keys=section_keys,
            direct_evidence_keys=direct,
            adjacent_evidence_keys=adjacent,
            background_only_keys=background,
            contrast="Use the section evidence to distinguish the strongest supported interpretation from adjacent claims.",
            forbidden_overclaim="Do not convert adjacent or background evidence into direct support for the section claim.",
            required_tables=tables,
            required_figures=figures,
            failure_test="",
        )
        kernels.append(kernel)
    write_jsonl(sidecars_dir(ws_dir) / "section-kernels.jsonl", kernels)
    license_doc = {
        "status": "THESIS_LICENSED",
        "rule": "Claims must stay within direct, adjacent, and background evidence roles from the planning package.",
        "sections": [kernel.section_id for kernel in kernels],
    }
    write_text(sidecars_dir(ws_dir) / "thesis-license.yaml", yaml.safe_dump(license_doc, allow_unicode=True, sort_keys=False))
    return kernels
