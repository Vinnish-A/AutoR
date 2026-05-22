"""Ticket-driven revision for failed external critic/check rounds."""

from __future__ import annotations

import re
from pathlib import Path

from autor.write_agent.integrate import replace_section
from autor.write_agent.workspace_io import read_jsonl, read_text, update_state

REPLACEMENT_RE = re.compile(
    r"<!--\s*AUTOR:REPLACEMENT\s+(S\d+[A-Za-z0-9_-]*)\s+START\s*-->(.*?)<!--\s*AUTOR:REPLACEMENT\s+\1\s+END\s*-->",
    flags=re.DOTALL,
)


def affected_sections(ticket_text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\bS\d+[A-Za-z0-9_-]*\b", ticket_text)))


def revise_from_tickets(ws_dir: Path, ticket_paths: list[Path]) -> dict:
    kernels = {row["section_id"]: row for row in read_jsonl(ws_dir / "sidecars" / "section-kernels.jsonl")}
    changed: list[str] = []
    unresolved: list[str] = []
    for ticket_path in ticket_paths:
        text = read_text(ticket_path)
        replacements = list(REPLACEMENT_RE.finditer(text))
        if replacements:
            for match in replacements:
                section_id = match.group(1)
                kernel = kernels.get(section_id, {"title": section_id})
                replace_section(ws_dir, section_id, kernel.get("title", section_id), match.group(2).strip())
                changed.append(section_id)
            continue
        for section_id in affected_sections(text):
            unresolved.append(section_id)
    status = "WRITE_READY_FOR_EXTERNAL_CRITIC" if changed and not unresolved else "WRITE_AGENT_API_FAILED"
    if unresolved and not changed:
        status = "REWRITE_REQUIRED_STYLE"
    state = update_state(
        ws_dir,
        status=status,
        failed_stage="none" if not unresolved else "revise",
        cause_class="none" if not unresolved else "requires_llm_rewrite",
        revised_sections=sorted(set(changed)),
        unresolved_sections=sorted(set(unresolved)),
    )
    return state
