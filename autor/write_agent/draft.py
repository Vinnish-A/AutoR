"""Candidate drafting with the write-agent LLM boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autor.write_agent import llm
from autor.write_agent.gates import evaluate_section_candidates
from autor.write_agent.models import SectionKernel, WriteAgentConfig
from autor.write_agent.prompts import CANDIDATE_WRITER, WRITER_SYSTEM
from autor.write_agent.workspace_io import read_jsonl, read_text, variants_dir, write_text


def _evidence_packet(ws_dir: Path, kernel: SectionKernel) -> str:
    ledger = read_text(ws_dir / "evidence-ledger.md")
    lines = [line for line in ledger.splitlines() if any(f"@{key}" in line for key in kernel.evidence_keys)]
    return "\n".join(lines[:80]) if lines else ledger[:6000]


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
    for seed in section_seeds:
        prompt = CANDIDATE_WRITER.format(
            section_id=kernel.section_id,
            title=kernel.title,
            controlling_claim=kernel.controlling_claim,
            evidence_keys=", ".join(kernel.evidence_keys),
            contrast=kernel.contrast,
            forbidden_overclaim=kernel.forbidden_overclaim,
            seed=seed,
            evidence_packet=packet,
        )
        text = llm.complete_text(prompt, config, system=WRITER_SYSTEM, model=config.model)
        path = target_dir / (seed["seed_id"].replace(f"{kernel.section_id}-", "") + ".md")
        write_text(path, text.strip() + "\n")
        paths.append(path)
    evaluate_section_candidates(ws_dir, kernel.section_id, paths)
    return paths


def load_seed_bank(ws_dir: Path) -> list[dict[str, Any]]:
    return read_jsonl(ws_dir / "sidecars" / "seed-bank.jsonl")
