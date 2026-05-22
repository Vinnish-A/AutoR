from __future__ import annotations

import json

from autor.write_agent.gates import evaluate_candidate
from autor.write_agent.models import SectionKernel


def _write_boundary(ws_dir):
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "references.bib").write_text(
        "@article{Smith2024,\n title={Direct}\n}\n@article{Bad2020,\n title={Bad}\n}\n",
        encoding="utf-8",
    )
    (ws_dir / "reference-map.json").write_text(
        json.dumps(
            {
                "references": [
                    {"citekey": "Smith2024", "bibliographic_validity": "citable", "citation_policy": "must_cite"},
                    {"citekey": "Bad2020", "bibliographic_validity": "not_citable", "citation_policy": "do_not_cite"},
                ]
            }
        ),
        encoding="utf-8",
    )


class TestWriteAgentGates:
    def test_unknown_citekey_is_evidence_boundary_failure(self, tmp_path):
        _write_boundary(tmp_path)
        result = evaluate_candidate("This shows the direct finding [@Missing2026].", tmp_path)

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "unknown_citekey" in result.failure_class

    def test_l6_claim_is_rejected(self, tmp_path):
        _write_boundary(tmp_path)
        result = evaluate_candidate("This proves clinical efficacy [@Smith2024].", tmp_path)

        assert result.hard_fail is True
        assert "l6_forbidden_leap" in result.failure_class

    def test_generic_validation_ending_requires_style_rewrite(self, tmp_path):
        _write_boundary(tmp_path)
        result = evaluate_candidate("Smith shows the direct finding [@Smith2024]. Future studies are needed.", tmp_path)

        assert result.status == "REWRITE_REQUIRED_STYLE"
        assert "generic_validation_as_ending" in result.failure_class

    def test_no_adjudicative_claim_requires_cowardice_rewrite(self, tmp_path):
        _write_boundary(tmp_path)
        result = evaluate_candidate("The section includes evidence from [@Smith2024].", tmp_path)

        assert result.status == "REWRITE_REQUIRED_COWARDICE"
        assert "no_adjudicative_claim" in result.failure_class

    def test_valid_candidate_passes(self, tmp_path):
        _write_boundary(tmp_path)
        kernel = SectionKernel(
            section_id="S1",
            title="Direct",
            controlling_claim="Smith shows the direct finding.",
            evidence_keys=["Smith2024"],
            direct_evidence_keys=["Smith2024"],
        )
        result = evaluate_candidate("Smith shows that the direct endpoint constrains the broader claim [@Smith2024].", tmp_path, kernel)

        assert result.status == "PASS"
        assert result.hard_fail is False
