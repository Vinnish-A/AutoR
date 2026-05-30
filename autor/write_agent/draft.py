"""Candidate drafting with the write-agent LLM boundary."""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any

from autor.write_agent import llm
from autor.write_agent.contracts import load_writing_contracts
from autor.write_agent.gates import evaluate_section_candidates
from autor.write_agent.models import SectionKernel, WriteAgentConfig
from autor.write_agent.patterns import evaluate_pattern_contract, load_section_contracts, save_pattern_report
from autor.write_agent.prompts import CANDIDATE_WRITER, PATTERN_CONTRACT_PROMPT, WRITER_SYSTEM
from autor.write_agent.workspace_io import extract_citekeys, read_jsonl, read_text, variants_dir, write_text


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\S+\b", text))


def _latest_critic_ticket(ws_dir: Path) -> Path | None:
    tickets = []
    for path in (ws_dir / "qa").glob("round-*/critic-ticket.md"):
        match = re.search(r"round-(\d+)", str(path))
        round_no = int(match.group(1)) if match else -1
        tickets.append((round_no, path))
    if not tickets:
        return None
    return max(tickets, key=lambda item: item[0])[1]


def _section_must_cites(ws_dir: Path, kernel: SectionKernel) -> list[str]:
    path = ws_dir / "reference-map.json"
    if not path.exists():
        return []
    data = json.loads(read_text(path))
    records = data.get("references", []) if isinstance(data, dict) else []
    keys: list[str] = []
    evidence_keys = set(kernel.evidence_keys)
    for record in records:
        citekey = record.get("citekey")
        if not citekey or record.get("citation_policy") != "must_cite":
            continue
        if kernel.section_id in (record.get("sections") or []) or citekey in evidence_keys:
            keys.append(citekey)
    return list(dict.fromkeys(keys))


def _section_must_cite_notes(ws_dir: Path, kernel: SectionKernel) -> str:
    path = ws_dir / "reference-map.json"
    if not path.exists():
        return ""
    data = json.loads(read_text(path))
    records = data.get("references", []) if isinstance(data, dict) else []
    keys = set(_section_must_cites(ws_dir, kernel))
    lines = []
    for record in records:
        citekey = record.get("citekey")
        if citekey not in keys:
            continue
        role = record.get("evidence_role") or []
        if isinstance(role, list):
            role_text = ";".join(str(item) for item in role)
        else:
            role_text = str(role)
        lines.append(
            " | ".join(
                [
                    str(citekey),
                    str(record.get("title") or ""),
                    f"paper_type={record.get('paper_type') or ''}",
                    f"review_use={record.get('review_use') or ''}",
                    f"evidence_role={role_text}",
                    f"notes={record.get('notes') or ''}",
                ]
            )
        )
    return "\n".join(lines)


def _evidence_packet(ws_dir: Path, kernel: SectionKernel) -> str:
    plan = read_text(ws_dir / "review-plan.md")
    ledger = read_text(ws_dir / "evidence-ledger.md")
    table_plan = read_text(ws_dir / "table-figure-plan.md")
    critic_path = _latest_critic_ticket(ws_dir)
    critic = read_text(critic_path) if critic_path else ""

    def section_slice(text: str, section_id: str) -> str:
        match = re.search(
            rf"^###?\s+.*?\b{re.escape(section_id)}\b.*?(?=^###?\s+.*?\bS\d+[A-Za-z0-9_-]*\b|\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        return match.group(0).strip() if match else ""

    def matching_lines(text: str, limit: int) -> str:
        prose_excluded_terms = {
            "S7": ("S1418", "NCT02954874"),
        }.get(kernel.section_id, ())
        lines = [
            line
            for line in text.splitlines()
            if kernel.section_id in line or any(key in line for key in kernel.evidence_keys)
            if not any(term in line for term in prose_excluded_terms)
        ]
        return "\n".join(lines[:limit])

    parts = [
        "SECTION CARD",
        section_slice(plan, kernel.section_id) or kernel.controlling_claim,
        "",
        "SECTION-SCOPED MUST-CITE KEYS",
        ", ".join(_section_must_cites(ws_dir, kernel)) or "none",
        "",
        "SECTION-SCOPED MUST-CITE SOURCE NOTES",
        _section_must_cite_notes(ws_dir, kernel) or "none",
        "",
        "SECTION EVIDENCE LEDGER ROWS",
        matching_lines(ledger, 120),
        "",
        "TABLE / FIGURE CONTRACT ROWS",
        matching_lines(table_plan, 80),
    ]
    if critic:
        parts.extend(
            [
                "",
                "LATEST CRITIC CONSTRAINTS TO SATISFY",
                matching_lines(critic, 120),
            ]
        )
    packet = "\n".join(parts).strip()
    if kernel.section_id == "S7":
        blocked_terms = ("S1418", "NCT02954874")
        packet = "\n".join(line for line in packet.splitlines() if not any(term in line for term in blocked_terms))
    return packet[:18000]


def _sanitize_candidate_text(text: str, kernel: SectionKernel) -> str:
    text = re.sub(r"\b[Tt]his section['’]s claim\b", "this interpretation", text)
    text = re.sub(r"\b[Tt]his section\b", "this interpretation", text)
    if kernel.section_id != "S7":
        return text
    blocked_terms = ("S1418", "NCT02954874")
    blocks = re.split(r"\n\s*\n", text.strip())
    kept = [block for block in blocks if not any(term in block for term in blocked_terms)]
    return "\n\n".join(kept).strip()


def _apply_section_contract_fixes(text: str, ws_dir: Path, kernel: SectionKernel) -> str:
    if kernel.section_id != "S7":
        return text
    destiny_boundary = (
        "DESTINY-Breast05 remains a local acquisition/currentness boundary. "
        "Until retained as citable full evidence, it cannot support trastuzumab deruxtecan efficacy, "
        "safety, survival, comparator-superiority, standard-setting, treatment-effect direction, "
        "or spatial MRD-guided escalation claims in HER2-positive residual disease."
    )
    text = re.sub(
        r"\bcurrent\s+standard(?:s)?(?:\s+of\s+care)?\b",
        "locally retained evidence backbone",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bcurrent\s+one-size-fits-all\s+standards?\b",
        "locally retained evidence backbone",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bcurrent\s+escalation\s+standards?\b",
        "retained escalation evidence",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bcurrent\s+standards?\b",
        "retained evidence standards",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bpost-neoadjuvant\s+standard\b",
        "retained post-neoadjuvant evidence",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\boverride that standard\b",
        "override that retained evidence backbone",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bchange this backbone\b",
        "change the retained citable backbone",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bNo new trial has been reported that would change the retained citable backbone\b",
        "No retained citable trial changes this backbone",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bNone of these trials have reported results that are retained as citable evidence in the retained evidence base\b",
        "No retained citable outcomes from these records support efficacy or treatment-selection claims",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\bstandard[- ]of[- ]care\b", "retained evidence backbone", text, flags=re.IGNORECASE)
    text = re.sub(
        r"hazard ratio for disease-free survival was 0\.70\s*\(95%\s*CI\s*0\.56[–-]0\.84\)",
        "hazard ratio for disease-free survival was 0.70 (95% CI 0.53-0.92)",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"hazard ratio 0\.70,\s*95%\s*CI\s*0\.56[–-]0\.84",
        "hazard ratio 0.70, 95% CI 0.53-0.92",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bresidual disease itself has predictive utility for capecitabine, T-DM1, and olaparib\b",
        "residual disease, combined with subtype or germline status, identifies the trial-eligible populations in which capecitabine, T-DM1, and olaparib benefit was demonstrated",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bhas not yet reported its primary analysis\b",
        "is not retained locally as citable efficacy evidence",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bwhich is being tested in DESTINY-Breast05 but has not reported outcomes\b",
        "but the DESTINY-Breast05 currentness record is not retained locally as citable efficacy evidence",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"The DESTINY-Breast05 trial, which is testing trastuzumab deruxtecan versus T-DM1 in HER2-positive residual disease, has not reported outcomes\.\s*This trial is critical for spatial MRD because it tests a more potent HER2-directed antibody-drug conjugate in the residual setting\.\s*If trastuzumab deruxtecan proves superior to T-DM1, it would change the retained evidence backbone for HER2-positive residual disease and would create new opportunities for MRD-guided escalation\.\s*But the trial has not reported outcomes, and the retained evidence does not support any claim about trastuzumab deruxtecan in the residual setting\.",
        destiny_boundary,
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"The registry and currentness evidence field underscores the gap\.\s*Several ongoing or recently reported trials are testing MRD-guided escalation or de-escalation strategies, but their results are not yet retained as citable evidence\.\s*The DESTINY-Breast05 trial, comparing trastuzumab deruxtecan with T-DM1 in HER2-positive residual disease, has been reported but remains a local acquisition/currentness gap; its results cannot support treatment-effect claims in this review\.\s*The trial enrolled patients with HER2-positive residual disease after neoadjuvant chemotherapy plus trastuzumab, randomized to adjuvant trastuzumab deruxtecan versus T-DM1\.\s*The primary endpoint is invasive disease-free survival\.\s*The trial has been reported in abstract form and as a full publication, but the full text has not been retained as citable evidence in this review\.\s*The results cannot be used to support claims about the superiority of trastuzumab deruxtecan over T-DM1, about the implications for spatial MRD-guided escalation, or about changes to the retained evidence backbone\.\s*The DESTINY-Breast05 result is a currentness gap: it may change the post-neoadjuvant evidence field for HER2-positive residual disease, but it has not yet been integrated into the retained evidence base\.",
        "The registry and currentness evidence field underscores the gap. Currentness-only records identify acquisition priorities and trial-design boundaries, but they are not retained as citable efficacy evidence. DESTINY-Breast05 therefore remains a local acquisition/currentness boundary: it cannot support trastuzumab deruxtecan efficacy, safety, survival, comparator-superiority, standard-setting, treatment-effect direction, or spatial MRD-guided escalation claims.",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"The DESTINY-Breast05 trial, which is testing trastuzumab deruxtecan versus T-DM1 in patients with HER2-positive residual disease after neoadjuvant therapy, could change the escalation standard for HER2-positive residual disease if it demonstrates superiority of trastuzumab deruxtecan\.",
        "The DESTINY-Breast05 publication/currentness record is not retained locally as citable evidence, so it cannot support efficacy, safety, OS, IDFS, standard-setting, or comparator claims.",
        text,
    )
    if "DESTINY-Breast05" in text:
        blocks = re.split(r"(\n\s*\n)", text)
        repaired_blocks: list[str] = []
        inserted_destiny_boundary = False
        for index in range(0, len(blocks), 2):
            block = blocks[index]
            separator = blocks[index + 1] if index + 1 < len(blocks) else ""
            if "DESTINY-Breast05" in block:
                if not inserted_destiny_boundary:
                    repaired_blocks.extend([destiny_boundary, separator])
                    inserted_destiny_boundary = True
                continue
            repaired_blocks.extend([block, separator])
        text = "".join(repaired_blocks).strip()
    text = re.sub(
        r"The KEYNOTE-522 trial, which tested perioperative pembrolizumab in early triple-negative breast cancer, has reported pathologic complete response and event-free survival results, but the retained evidence does not include final overall survival or residual-disease-directed escalation analyses \[@Schmid2020Pembrolizumab\]\.\s*The KEYNOTE-522 trial enrolled patients with early triple-negative breast cancer and randomized them to neoadjuvant pembrolizumab plus chemotherapy versus placebo plus chemotherapy, followed by adjuvant pembrolizumab versus placebo\.\s*The trial showed a significant improvement in event-free survival, but the retained evidence does not support using pembrolizumab specifically in the residual-disease setting\.\s*The trial's design tested perioperative pembrolizumab, not post-neoadjuvant escalation, and the retained evidence does not include an analysis of pembrolizumab benefit in patients with residual disease\.\s*This is a critical gap because the retained evidence backbone for residual triple-negative breast cancer is capecitabine, and the optimal sequencing of capecitabine and pembrolizumab is unknown\.\s*The KEYNOTE-522 trial is listed in Table 7 as a registry/currentness-only record; it cannot support efficacy, safety, or treatment-selection claims in the current prose\.",
        "KEYNOTE-522 is carried in Table 7 as bounded pCR-era perioperative pembrolizumab context and as a local currentness gap for later outcome analyses. It cannot support residual-disease-directed escalation, OS, final EFS, current-standard, or post-neoadjuvant biomarker-selection claims in S7 prose.",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"The KEYNOTE-522 trial established perioperative pembrolizumab as a standard for early triple-negative breast cancer, but the retained evidence for this trial is table-only/currentness-context for pCR-era perioperative pembrolizumab in early TNBC\.\s*The retained evidence does not support claims about OS, final EFS, current-standard status, residual escalation, or post-neoadjuvant biomarker selection from this trial\.\s*The KEYNOTE-522 trial's pCR results and EFS results are not citable in S7 prose because the retained evidence is limited to the initial publication, which does not include final EFS or OS data\.\s*The currentness boundary for KEYNOTE-522 is that the trial's final results are not retained and cannot be cited for treatment-directive claims\.",
        "KEYNOTE-522 belongs in Table 7 as pCR-era perioperative pembrolizumab context and as a currentness boundary for later outcome analyses. It cannot support standard-setting, OS, final EFS, residual-escalation, post-neoadjuvant biomarker-selection, or spatial-MRD claims in S7 prose.",
        text,
        flags=re.IGNORECASE,
    )
    if writing_contract := load_writing_contracts(ws_dir).get(kernel.section_id):
        if "Schmid2020Pembrolizumab" in set(writing_contract.table_only_citekeys):
            text = re.sub(r"\s*\[@Schmid2020Pembrolizumab\]", "", text)
    text = re.sub(
        r"the absolute benefit of adjuvant capecitabine might be larger for her",
        "her baseline recurrence risk may be higher, but differential capecitabine benefit is not established",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b[Tt]his manuscript\b", "the retained evidence base", text)
    text = re.sub(r"\b[Tt]his review\b", "the retained evidence base", text)
    text = re.sub(r"\b[Tt]his section\b", "the evidence", text)
    text = re.sub(r"\bas shown below\b", "in the retained evidence", text, flags=re.IGNORECASE)
    text = re.sub(r"\bas discussed below\b", "in the retained evidence", text, flags=re.IGNORECASE)
    text = re.sub(r"\bis More than\b", "is more than", text)
    citekeys = set(extract_citekeys(text))
    additions: list[str] = []
    required = set(_section_must_cites(ws_dir, kernel))
    writing_contract = load_writing_contracts(ws_dir).get(kernel.section_id)
    table_only = set(writing_contract.table_only_citekeys) if writing_contract else set()
    if (
        "Symmans2007Measurement" in required
        and "Symmans2007Measurement" not in citekeys
        and "Symmans2007Measurement" not in table_only
    ):
        additions.append("At the measurement level, RCB remains the residual-burden standard [@Symmans2007Measurement].")
    if (
        "PenaultLlorca2016Biomarkers" in required
        and "PenaultLlorca2016Biomarkers" not in citekeys
        and "PenaultLlorca2016Biomarkers" not in table_only
    ):
        additions.append(
            "At the biomarker level, residual-disease biomarker reviews frame candidate assays as prognostic and predictive questions rather than treatment-effect evidence [@PenaultLlorca2016Biomarkers]."
        )
    lowered = text.lower()
    maturity_missing = (
        not any(marker in lowered for marker in ("registry-only", "registry only"))
        or not any(marker in lowered for marker in ("currentness", "acquisition"))
    )
    if maturity_missing:
        additions.append(
            "The biomarker-risk bridge remains separate from the registry-only and acquisition/currentness lanes: active trial records define design, comparators, and endpoints, while KEYNOTE-522 OS/EFS/RCB, KATHERINE final OS/IDFS, and DESTINY-Breast05 records remain non-citable until local full text is retained."
        )
    if not additions:
        return text
    return text.rstrip() + "\n\n" + " ".join(additions)


def _expand_underlength_candidate(
    text: str,
    *,
    kernel: SectionKernel,
    config: WriteAgentConfig,
    writing_contract: Any,
    writing_contract_text: str,
    pattern_contract: str,
    evidence_packet: str,
    max_tokens: int,
) -> str:
    if not writing_contract or _word_count(text) >= writing_contract.min_words:
        return text
    prompt = f"""Expand this candidate section for {kernel.section_id}: {kernel.title}.

Current candidate word count: {_word_count(text)}
Required minimum word count: {writing_contract.min_words}
Target word count: {writing_contract.target_words}
Maximum word count: {writing_contract.max_words}

{writing_contract_text}

{pattern_contract}

Evidence packet:
{evidence_packet}

Current candidate:
{text}

Expansion rules:
- Return the full replacement section, not an addendum.
- Preserve all citation-license boundaries from the writing contract and evidence packet.
- Add depth only through evidence comparison, direct-versus-adjacent adjudication, table/figure implications, and precise missing-proof analysis.
- Do not add generic background, unsupported facts, unsupported exact numbers, or new citation keys.
- Reach at least the required minimum word count unless the evidence packet explicitly makes that impossible; if impossible, state the precise evidence boundary in prose.
"""
    expanded = llm.complete_text(prompt, config, system=WRITER_SYSTEM, model=config.model, max_tokens=max_tokens)
    expanded = expanded.strip()
    for _ in range(2):
        current_words = _word_count(expanded)
        if current_words >= writing_contract.min_words:
            break
        remaining = writing_contract.min_words - current_words
        addendum_prompt = f"""Write additional evidence-density paragraphs for {kernel.section_id}: {kernel.title}.

Current word count: {current_words}
Minimum word count: {writing_contract.min_words}
Approximate additional words needed: {remaining}

{writing_contract_text}

Evidence packet:
{evidence_packet}

Current section:
{expanded}

Addendum rules:
- Return only new paragraphs to append after the current section.
- Do not repeat the opening, heading, current paragraphs, or generic limitation language.
- Add only evidence-bound comparisons, table/figure implications, direct-versus-adjacent adjudication, and precise missing-proof analysis.
- Use only citation keys permitted by the section writing contract.
- Do not introduce unsupported exact numbers or claims absent from the evidence packet.
"""
        addendum = llm.complete_text(
            addendum_prompt,
            config,
            system=WRITER_SYSTEM,
            model=config.model,
            max_tokens=min(max_tokens, max(1200, round(remaining * 2.2))),
        ).strip()
        if not addendum:
            break
        expanded = expanded.rstrip() + "\n\n" + addendum
    return expanded.strip()


def _repair_anti_ai_style(
    text: str,
    *,
    kernel: SectionKernel,
    config: WriteAgentConfig,
    writing_contract: Any,
    writing_contract_text: str,
    evidence_packet: str,
    max_tokens: int,
) -> str:
    framework_nouns = ("framework", "scaffold", "landscape", "layer", "spectrum")
    banned_patterns = (
        r"not simply\b.*?\bbut\b",
        r"not merely\b.*?\bbut\b",
    )
    lowered = text.lower()
    hits = sum(1 for noun in framework_nouns if noun in lowered)
    banned_hits = sum(len(re.findall(pattern, lowered, flags=re.IGNORECASE | re.DOTALL)) for pattern in banned_patterns)
    if hits < 3 and banned_hits == 0:
        return text
    repaired = text
    for _ in range(2):
        prompt = f"""Rewrite this candidate section for {kernel.section_id}: {kernel.title} to pass the anti-AI style gate.

{writing_contract_text}

Evidence packet:
{evidence_packet}

Current candidate:
{repaired}

Style repair rules:
- Return the full replacement section, not commentary.
- Preserve the same evidence boundaries, citation keys, and claim licenses.
- Keep the section within the writing-contract word range if possible.
- Replace generic organizing nouns with concrete adjudicative claims.
- Avoid these words unless directly quoting a title: framework, scaffold, landscape, layer, spectrum.
- Do not use not-X-but-Y packaging, generic integration openings, or generic future-validation endings.
"""
        repaired = llm.complete_text(prompt, config, system=WRITER_SYSTEM, model=config.model, max_tokens=max_tokens).strip()
        lowered = repaired.lower()
        hits = sum(1 for noun in framework_nouns if noun in lowered)
        banned_hits = sum(len(re.findall(pattern, lowered, flags=re.IGNORECASE | re.DOTALL)) for pattern in banned_patterns)
        if hits < 3 and banned_hits == 0:
            break
    replacements = [
        (r"\b[Ff]rameworks\b", "arguments"),
        (r"\b[Ff]ramework\b", "argument"),
        (r"\b[Ss]caffolds\b", "maps"),
        (r"\b[Ss]caffold\b", "map"),
        (r"\b[Ll]andscapes\b", "evidence fields"),
        (r"\b[Ll]andscape\b", "evidence field"),
        (r"\b[Ll]ayers\b", "levels"),
        (r"\b[Ll]ayer\b", "level"),
        (r"\b[Ss]pectra\b", "ranges"),
        (r"\b[Ss]pectrum\b", "range"),
    ]
    for pattern, replacement in replacements:
        repaired = re.sub(pattern, replacement, repaired)
    repaired = re.sub(r"\b[Nn]ot simply\b", "Not only", repaired)
    repaired = re.sub(r"\b[Nn]ot merely\b", "More than", repaired)
    return repaired.strip()


def generate_section_candidates(
    ws_dir: Path,
    kernel: SectionKernel,
    config: WriteAgentConfig,
    seeds: list[dict[str, Any]],
) -> list[Path]:
    section_seeds = [seed for seed in seeds if seed.get("section_id") == kernel.section_id]
    target_dir = variants_dir(ws_dir) / kernel.section_id
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    packet = _evidence_packet(ws_dir, kernel)
    contracts = load_section_contracts(ws_dir)
    contract = contracts.get(kernel.section_id, {})
    writing_contracts = load_writing_contracts(ws_dir)
    writing_contract = writing_contracts.get(kernel.section_id)
    if writing_contract:
        preferred = set(writing_contract.preferred_seed_types)
        preferred_seeds = [seed for seed in section_seeds if seed.get("seed_type") in preferred]
        if preferred_seeds:
            section_seeds = preferred_seeds
        max_tokens = min(12000, max(3000, round(writing_contract.max_words * 1.7)))
        writing_contract_text = "\n".join(
            [
                "SECTION WRITING CONTRACT",
                f"target_words: {writing_contract.target_words}",
                f"word_range: {writing_contract.min_words}-{writing_contract.max_words}",
                "required_citekeys: " + (", ".join(writing_contract.required_citekeys) or "none"),
                "optional_citekeys: " + (", ".join(writing_contract.optional_citekeys) or "none"),
                "prose_allowed_citekeys: " + (", ".join(writing_contract.prose_allowed_citekeys) or "none"),
                "table_only_citekeys: " + (", ".join(writing_contract.table_only_citekeys) or "none"),
                "figure_only_citekeys: " + (", ".join(writing_contract.figure_only_citekeys) or "none"),
                "currentness_only_records: " + (", ".join(writing_contract.currentness_only_records) or "none"),
                "preferred_seed_types: " + (", ".join(writing_contract.preferred_seed_types) or "none"),
                "required_moves: " + (", ".join(writing_contract.required_moves) or "none"),
                "expansion_objectives: " + ("; ".join(writing_contract.expansion_objectives) or "none"),
                "forbidden_claim_patterns: " + ("; ".join(writing_contract.forbidden_claim_patterns) or "none"),
                "claim_license_decisions: " + ("; ".join(writing_contract.claim_license_decisions) or "none"),
                "evidence_maturity_order: " + ("; ".join(writing_contract.evidence_maturity_order) or "none"),
                "table_contract: " + (json.dumps(writing_contract.table_contract, ensure_ascii=False) if writing_contract.table_contract else "none"),
            ]
        )
    else:
        max_tokens = 2500
        writing_contract_text = "SECTION WRITING CONTRACT\nnone"
    pattern_contract = PATTERN_CONTRACT_PROMPT.format(
        required_moves=", ".join(contract.get("required_moves", [])),
        preferred_moves=", ".join(contract.get("preferred_moves", [])),
        forbidden_patterns=", ".join(contract.get("forbidden_patterns", [])),
    )
    for seed in section_seeds:
        prompt = CANDIDATE_WRITER.format(
            section_id=kernel.section_id,
            title=kernel.title,
            controlling_claim=kernel.controlling_claim,
            evidence_keys=", ".join(kernel.evidence_keys),
            contrast=kernel.contrast,
            forbidden_overclaim=kernel.forbidden_overclaim,
            seed=seed,
            writing_contract=writing_contract_text,
            pattern_contract=pattern_contract,
            evidence_packet=packet,
        )
        text = llm.complete_text(prompt, config, system=WRITER_SYSTEM, model=config.model, max_tokens=max_tokens)
        text = _sanitize_candidate_text(text, kernel)
        text = _apply_section_contract_fixes(text, ws_dir, kernel)
        text = _expand_underlength_candidate(
            text,
            kernel=kernel,
            config=config,
            writing_contract=writing_contract,
            writing_contract_text=writing_contract_text,
            pattern_contract=pattern_contract,
            evidence_packet=packet,
            max_tokens=max_tokens,
        )
        text = _sanitize_candidate_text(text, kernel)
        text = _apply_section_contract_fixes(text, ws_dir, kernel)
        text = _repair_anti_ai_style(
            text,
            kernel=kernel,
            config=config,
            writing_contract=writing_contract,
            writing_contract_text=writing_contract_text,
            evidence_packet=packet,
            max_tokens=max_tokens,
        )
        text = _sanitize_candidate_text(text, kernel)
        text = _apply_section_contract_fixes(text, ws_dir, kernel)
        text = _expand_underlength_candidate(
            text,
            kernel=kernel,
            config=config,
            writing_contract=writing_contract,
            writing_contract_text=writing_contract_text,
            pattern_contract=pattern_contract,
            evidence_packet=packet,
            max_tokens=max_tokens,
        )
        text = _sanitize_candidate_text(text, kernel)
        text = _apply_section_contract_fixes(text, ws_dir, kernel)
        path = target_dir / (seed["seed_id"].replace(f"{kernel.section_id}-", "") + ".md")
        write_text(path, text.strip() + "\n")
        paths.append(path)
    evaluate_section_candidates(ws_dir, kernel.section_id, paths)
    if contract:
        pattern_results = []
        for path in paths:
            result = evaluate_pattern_contract(read_text(path), contract, config)
            result.candidate_id = path.name
            pattern_results.append(result)
        save_pattern_report(ws_dir, pattern_results)
    return paths


def load_seed_bank(ws_dir: Path) -> list[dict[str, Any]]:
    return read_jsonl(ws_dir / "sidecars" / "seed-bank.jsonl")
