from __future__ import annotations

import json

from autor.write_agent.assets import integrate_assets, normalize_workflow_scaffolding


def test_normalize_workflow_scaffolding_removes_evidence_packet_phrase():
    text = (
        "The evidence packet restricts this claim. Another evidence packet prohibits overreach. "
        "a plasma metabolomic signature of fatty-acid and nucleotide metabolism was associated with survival in early breast cancer [@Talarico2024Metabolomic] "
        "The ongoing trials that are testing ctDNA-MRD as a treatment selection biomarker (e.g., DETECT, TRACER-RB) have not yet reported results."
    )

    normalized = normalize_workflow_scaffolding(text)

    assert "evidence packet" not in normalized.lower()
    assert "retained evidence" in normalized
    assert "nucleotide metabolism" not in normalized
    assert "DETECT" not in normalized


def test_t7_integrates_retained_registry_ids_from_reference_map_and_sidecars(tmp_path):
    ws_dir = tmp_path / "workspace" / "BRCA"
    (ws_dir / "sidecars").mkdir(parents=True)
    (ws_dir / "trials" / "core").mkdir(parents=True)
    (ws_dir / "sidecars" / "section-kernels.jsonl").write_text(
        json.dumps({"section_id": "S7", "title": "Clinical trials"}) + "\n",
        encoding="utf-8",
    )
    (ws_dir / "write.md").write_text(
        "### S7: Clinical trials\n\nDirect evidence shows the trial landscape remains bounded.\n",
        encoding="utf-8",
    )
    (ws_dir / "reference-map.json").write_text(
        json.dumps(
            {
                "references": [],
                "trials": [
                    {
                        "trial_id": "NCT03703427",
                        "sections": ["S7"],
                        "paired_assets": ["P7"],
                        "status": "retained",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (ws_dir / "trials" / "core" / "trials.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "trial_id": "NCT03703427",
                        "title": "Capecitabine Versus Vinorelbine in High Risk Breast Cancer With Pathologic Residual Tumors After Preoperative Chemotherapy",
                        "phase": ["PHASE2"],
                        "status": "UNKNOWN",
                        "retention_basis": "High-risk residual breast tumors after preoperative chemotherapy.",
                        "pico": {
                            "P": {
                                "conditions": ["Pathologic Residual Cancer Cells"],
                                "eligibility_excerpt": "pathologic residual cancer cells after preoperative chemotherapy",
                            },
                            "I": {
                                "interventions": ["Capecitabine", "Vinorelbine"],
                                "arms": [{"label": "Capecitabine"}, {"label": "Vinorelbine"}],
                            },
                            "O": {
                                "primary_endpoints": [
                                    {
                                        "measure": "disease free survival",
                                        "time_frame": "5 years",
                                    }
                                ]
                            },
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (ws_dir / "table-figure-plan.md").write_text(
        """## Table/Figure Pair Matrix
| Pair ID | Section slot | Table ID | Figure ID | Shared synthesis question | Shared citekeys | Shared trial IDs | Table function | Figure function |
|---|---|---|---|---|---|---|---|---|
| P7 | S7 | T7 | F7 | Which post-neoadjuvant trials are registry-only? | none | NCT02032823 | Trial taxonomy | Clinical bridge |

## Tables
| Table ID | Table title | Columns |
|---|---|---|
| T7 | Subtype-stratified trial taxonomy | Retained paper/trial; population; entry criterion; intervention/comparator; endpoint/result if retained; claim license; currentness/registry boundary |
""",
        encoding="utf-8",
    )

    result = integrate_assets(ws_dir)
    text = (ws_dir / "write.md").read_text(encoding="utf-8")

    assert result["status"] == "ASSETS_INTEGRATED"
    assert "NCT03703427" in text
    assert "Capecitabine/cytotoxic optimization registry family" in text
    assert "registry-defined iDFS/DFS/EFS/pCR, ctDNA, or safety endpoints; no result inferred" in text
    assert "no efficacy, safety, survival, approval, or comparative treatment-effect conclusion" in text
    assert "Use for registry landscape and trial-design context only." in text
    assert text.count(
        "Registry-only grouping; no efficacy, safety, survival, approval, or comparative treatment-effect conclusion."
    ) == 1
    assert (
        "Use for registry landscape and trial-design context only. | "
        "Registry-only grouping; no efficacy, safety, survival, approval, or comparative treatment-effect conclusion."
    ) in text
