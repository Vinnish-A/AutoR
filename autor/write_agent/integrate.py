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
    heading = f"### {section_id}: {title}"
    lines = body.splitlines()
    if lines and re.match(r"^#{1,6}\s+", lines[0]):
        lines = [heading] + lines[1:]
    else:
        lines = [heading, "", body]
    normalized = "\n".join(lines)
    # Candidate drafts may contain peer-review style subsection headings. Demote
    # them so section replacement can keep one canonical major heading per kernel.
    normalized = re.sub(r"(?m)^###\s+(?!S\d+[A-Za-z0-9_-]*\s*[:.])", "#### ", normalized)
    return normalized


def _deduplicate_heading_sections(text: str) -> str:
    heading = re.compile(r"^###\s+(S\d+[A-Za-z0-9_-]*)\s*[:.]", re.MULTILINE)
    matches = list(heading.finditer(text))
    if not matches:
        return text
    seen: set[str] = set()
    chunks: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        section_id = match.group(1)
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if start > cursor:
            chunks.append(text[cursor:start])
        if section_id not in seen:
            chunks.append(text[start:end])
            seen.add(section_id)
        cursor = end
    if cursor < len(text):
        chunks.append(text[cursor:])
    return "".join(chunks)


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
    anchor_pattern = (
        re.escape(start_anchor(section_id))
        + r".*?"
        + re.escape(end_anchor(section_id))
    )
    if re.search(anchor_pattern, text, flags=re.DOTALL):
        updated = re.sub(anchor_pattern, block, text, count=1, flags=re.DOTALL)
    else:
        heading_pattern = (
            rf"^###\s+{re.escape(section_id)}\s*[:.].*?"
            rf"(?=^###\s+S\d+[A-Za-z0-9_-]*\s*[:.]|\Z)"
        )
        if not re.search(heading_pattern, text, flags=re.DOTALL | re.MULTILINE):
            title_pattern = (
                rf"^#{{1,6}}\s+{re.escape(title)}\s*$.*?"
                rf"(?=^#{{1,6}}\s+|\Z)"
            )
            if not re.search(title_pattern, text, flags=re.DOTALL | re.MULTILINE):
                raise ValueError(f"write.md 缺少 section anchor: {section_id}")
            updated = re.sub(title_pattern, block.rstrip() + "\n\n", text, count=1, flags=re.DOTALL | re.MULTILINE)
        else:
            updated = re.sub(heading_pattern, block.rstrip() + "\n\n", text, count=1, flags=re.DOTALL | re.MULTILINE)
    write_text(path, _deduplicate_heading_sections(updated))
    update_state(ws_dir, status="INTEGRATED_WRITE_UPDATED", updated_section=section_id)
    return path
