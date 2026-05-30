from __future__ import annotations

from autor.write_agent.models import WriteAgentConfig
from autor.write_agent.patterns import (
    build_pattern_contract,
    evaluate_pattern_contract,
    extract_markdown_tables,
    has_generic_validation_without_target,
    save_pattern_report,
    scan_negative_patterns,
    table_is_warehouse,
)


def test_generic_integration_opening_is_flagged(tmp_path):
    flags = scan_negative_patterns(
        "This review integrates spatial evidence with clinical endpoints.",
        {
            "patterns": [
                {
                    "id": "generic_integration_opening",
                    "severity": "soft",
                    "regex": "(This review integrates)",
                    "instruction": "Open from a problem.",
                }
            ]
        },
    )

    assert flags[0]["id"] == "generic_integration_opening"


def test_generic_validation_without_target_fails():
    assert has_generic_validation_without_target("The signal is promising. Future studies are needed.") is True
    assert has_generic_validation_without_target(
        "Further validation is required to test endpoint linkage across sampling times."
    ) is False


def test_regenerate_response_is_hard_failed():
    contract = build_pattern_contract("S1", "Evidence section")
    result = evaluate_pattern_contract(
        "Direct evidence tiers remain uncertain at the endpoint. Regenerate response.",
        contract,
        WriteAgentConfig(),
    )

    assert result.hard_fail is True
    assert any(flag["id"] == "process_trace" for flag in result.anti_ai_flags)


def test_evidence_warehouse_table_fails_and_adjudication_table_passes():
    bad = """| Study | Design | Marker | Endpoint | Strength | Limitation |
|---|---|---|---|---|---|
| A | cohort | X | OS | strong | small |
"""
    good = """| Question adjudicated | Direct evidence | Adjacent evidence | What remains unlicensed |
|---|---|---|---|
| Endpoint link | supports association | atlas context | treatment selection |
"""

    assert table_is_warehouse(extract_markdown_tables(bad)[0]) is True
    assert table_is_warehouse(extract_markdown_tables(good)[0]) is False


def test_framework_density_and_citation_stacking_warn():
    contract = build_pattern_contract("S1", "Evidence section")
    text = (
        "Direct evidence tiers show endpoint uncertainty, while the framework and landscape remain broad "
        "[@A; @B; @C; @D]. The assay proof remains unresolved."
    )
    result = evaluate_pattern_contract(text, contract, WriteAgentConfig())

    assert result.hard_fail is False
    assert "framework_noun_density" in result.soft_warnings
    assert "citation_stacking" in result.soft_warnings


def test_missing_required_human_move_blocks_integration():
    contract = build_pattern_contract("S1", "Evidence section")
    result = evaluate_pattern_contract("The topic is important and widely studied.", contract, WriteAgentConfig())

    assert result.hard_fail is True
    assert "evidence_tiering" in result.missing_required_moves


def test_clinical_evidence_hierarchy_counts_as_tiering():
    contract = build_pattern_contract("S1", "Clinical object")
    result = evaluate_pattern_contract(
        "The cohort shows that pCR is prognostic but remains an incomplete surrogate endpoint. "
        "RCB adds a static histologic risk gradient, whereas ctDNA provides a complementary molecular "
        "and systemic signal that cannot be treated as a treatment-directive rule.",
        contract,
        WriteAgentConfig(),
    )

    assert "evidence_tiering" not in result.missing_required_moves


def test_spatial_boundary_counts_as_precise_uncertainty():
    contract = build_pattern_contract("S2", "Baseline spatial atlases")
    result = evaluate_pattern_contract(
        "Direct spatial atlas evidence separates treatment-naive neighborhoods from residual disease "
        "interpretation. The unresolved limitation is scale: ligand-receptor architecture in pre-treatment "
        "ecosystems cannot yet prove which post-treatment niches survive therapy.",
        contract,
        WriteAgentConfig(),
    )

    assert "precise_uncertainty" not in result.missing_required_moves


def test_pattern_report_is_written(tmp_path):
    ws_dir = tmp_path / "workspace" / "pattern-ws"
    ws_dir.mkdir(parents=True)
    contract = build_pattern_contract("S1", "Evidence section")
    result = evaluate_pattern_contract(
        "Direct evidence tiers show endpoint uncertainty and an unresolved assay proof.",
        contract,
        WriteAgentConfig(),
    )

    save_pattern_report(ws_dir, [result])

    assert (ws_dir / "qa" / "write-agent" / "pattern-report.md").exists()
    assert (ws_dir / "sidecars" / "pattern-scores.jsonl").exists()
