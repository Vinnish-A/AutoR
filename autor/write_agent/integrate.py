"""Anchor replacement for the canonical integrated manuscript."""

from __future__ import annotations

import re
from pathlib import Path

from autor.write_agent.models import SectionKernel
from autor.write_agent.workspace_io import read_text, update_state, write_text

YAML_HEADER = """---
bibliography: references.bib
csl: csl/nature.csl
link-citations: true
reference-section-title: References
---
"""


def start_anchor(section_id: str) -> str:
    return f"<!-- AUTOR:SECTION {section_id} START -->"


def end_anchor(section_id: str) -> str:
    return f"<!-- AUTOR:SECTION {section_id} END -->"


def make_section_block(section_id: str, title: str, body: str) -> str:
    body = body.strip()
    if not re.match(r"^#{1,6}\s+", body):
        body = f"## {title}\n\n{body}"
    return f"{start_anchor(section_id)}\n{body}\n{end_anchor(section_id)}"


def create_skeleton(ws_dir: Path, kernels: list[SectionKernel]) -> Path:
    blocks = [make_section_block(kernel.section_id, kernel.title, "_Draft pending._") for kernel in kernels]
    path = ws_dir / "write.md"
    write_text(path, YAML_HEADER + "\n\n".join(blocks) + "\n")
    update_state(ws_dir, write_md=str(path), status="INTEGRATED_WRITE_UPDATED")
    return path


def replace_section(ws_dir: Path, section_id: str, title: str, body: str) -> Path:
    path = ws_dir / "write.md"
    if not path.exists():
        create_skeleton(ws_dir, [SectionKernel(section_id=section_id, title=title, controlling_claim="")])
    text = read_text(path)
    block = make_section_block(section_id, title, body)
    pattern = (
        re.escape(start_anchor(section_id))
        + r".*?"
        + re.escape(end_anchor(section_id))
    )
    if not re.search(pattern, text, flags=re.DOTALL):
        raise ValueError(f"write.md 缺少 section anchor: {section_id}")
    updated = re.sub(pattern, block, text, count=1, flags=re.DOTALL)
    write_text(path, updated)
    update_state(ws_dir, status="INTEGRATED_WRITE_UPDATED", updated_section=section_id)
    return path
