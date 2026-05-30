from __future__ import annotations

import json

from autor.write_agent.draft import (
    _apply_section_contract_fixes,
    _latest_critic_ticket,
    _section_must_cite_notes,
    _section_must_cites,
)
from autor.write_agent.models import SectionKernel


def test_latest_critic_ticket_uses_highest_round(tmp_path):
    older = tmp_path / "qa" / "round-4" / "critic-ticket.md"
    latest = tmp_path / "qa" / "round-11" / "critic-ticket.md"
    older.parent.mkdir(parents=True)
    latest.parent.mkdir(parents=True)
    older.write_text("old", encoding="utf-8")
    latest.write_text("latest", encoding="utf-8")

    assert _latest_critic_ticket(tmp_path) == latest


def test_section_must_cites_includes_section_and_evidence_required_keys(tmp_path):
    (tmp_path / "reference-map.json").write_text(
        json.dumps(
            {
                "references": [
                    {"citekey": "A2024", "citation_policy": "must_cite", "sections": ["S7"]},
                    {"citekey": "B2024", "citation_policy": "must_cite", "sections": ["S1"]},
                    {"citekey": "C2024", "citation_policy": "must_cite", "sections": ["S1"]},
                    {"citekey": "D2024", "citation_policy": "cite_if_relevant", "sections": ["S7"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    kernel = SectionKernel(section_id="S7", title="Trials", controlling_claim="", evidence_keys=["C2024"])

    assert _section_must_cites(tmp_path, kernel) == ["A2024", "C2024"]


def test_section_must_cite_notes_include_role_context(tmp_path):
    (tmp_path / "reference-map.json").write_text(
        json.dumps(
            {
                "references": [
                    {
                        "citekey": "PenaultLlorca2016Biomarkers",
                        "title": "Biomarkers of residual disease",
                        "paper_type": "review",
                        "review_use": "included_main",
                        "citation_policy": "must_cite",
                        "sections": ["S7"],
                        "evidence_role": ["field_anchor", "section_anchor"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    kernel = SectionKernel(section_id="S7", title="Trials", controlling_claim="")

    notes = _section_must_cite_notes(tmp_path, kernel)

    assert "PenaultLlorca2016Biomarkers" in notes
    assert "Biomarkers of residual disease" in notes
    assert "paper_type=review" in notes


def test_s7_contract_fixes_add_missing_must_cites_and_currentness_lane(tmp_path):
    (tmp_path / "reference-map.json").write_text(
        json.dumps(
            {
                "references": [
                    {
                        "citekey": "Symmans2007Measurement",
                        "citation_policy": "must_cite",
                        "sections": ["S7"],
                    },
                    {
                        "citekey": "PenaultLlorca2016Biomarkers",
                        "citation_policy": "must_cite",
                        "sections": ["S7"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    kernel = SectionKernel(section_id="S7", title="Trials", controlling_claim="")

    text = _apply_section_contract_fixes("CREATE-X, OlympiA, KATHERINE, and EA1131 define the hierarchy.", tmp_path, kernel)

    assert "[@Symmans2007Measurement]" in text
    assert "[@PenaultLlorca2016Biomarkers]" in text
    assert "registry-only" in text
    assert "acquisition/currentness" in text
