"""Seed-bank generation for section candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autor.write_agent.models import SectionKernel
from autor.write_agent.workspace_io import sidecars_dir, write_jsonl

SEED_TYPES = [
    "measurement_blindspot",
    "old_model_failure",
    "direct_vs_adjacent_evidence",
    "clinical_endpoint_failure",
    "method_loss",
    "mechanistic_tension",
    "evidence_downgrade",
    "table_adjudication",
    "failure_test",
]

FORBIDDEN_PATTERNS = [
    "not simply X but Y",
    "not merely X but Y",
    "multi-layer framework",
    "future validation is needed",
]


def build_seed_bank(ws_dir: Path, kernels: list[SectionKernel], seed_count: int = 9) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for kernel in kernels:
        for idx in range(seed_count):
            seed_type = SEED_TYPES[idx % len(SEED_TYPES)]
            direct = kernel.direct_evidence_keys or kernel.evidence_keys
            seed = {
                "seed_id": f"{kernel.section_id}-seed-{idx + 1:02d}",
                "section_id": kernel.section_id,
                "type": seed_type,
                "opening_move": _opening_move(seed_type, kernel),
                "evidence_keys": direct[:2] if direct else [],
                "forbidden_patterns": FORBIDDEN_PATTERNS,
            }
            seeds.append(seed)
    write_jsonl(sidecars_dir(ws_dir) / "seed-bank.jsonl", seeds)
    return seeds


def _opening_move(seed_type: str, kernel: SectionKernel) -> str:
    if seed_type == "measurement_blindspot":
        return f"Start from what current evidence can measure in {kernel.title}, and what it cannot locate."
    if seed_type == "old_model_failure":
        return f"Start by showing where the older explanatory model for {kernel.title} fails."
    if seed_type == "direct_vs_adjacent_evidence":
        return "Make the direct evidence lead, then demote adjacent evidence to boundary-setting."
    if seed_type == "clinical_endpoint_failure":
        return "Start from the endpoint that looks clinically decisive but loses resolution."
    if seed_type == "method_loss":
        return "Start from the information lost by the dominant method."
    if seed_type == "mechanistic_tension":
        return "Start from the mechanistic tension that the evidence has not resolved."
    if seed_type == "evidence_downgrade":
        return "Start by downgrading a tempting interpretation because the direct evidence is thinner."
    if seed_type == "table_adjudication":
        return "Use the planned table as an adjudication device, not an evidence warehouse."
    return "State the decisive failure test that would make this section's claim collapse."
