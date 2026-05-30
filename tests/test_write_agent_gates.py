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

    def test_s5_caf_adjacent_sources_cannot_be_promoted_to_residual_evidence(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Cords2023Cancerassociated,\n title={CAF}\n}\n"
            "@article{Croizer2024Deciphering,\n title={CAF spatial}\n}\n",
            encoding="utf-8",
        )
        (tmp_path / "reference-map.json").write_text(
            json.dumps(
                {
                    "references": [
                        {
                            "citekey": "Cords2023Cancerassociated",
                            "bibliographic_validity": "citable",
                            "citation_policy": "cite_if_relevant",
                        },
                        {
                            "citekey": "Croizer2024Deciphering",
                            "bibliographic_validity": "citable",
                            "citation_policy": "cite_if_relevant",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S5",
            title="Residual programs",
            controlling_claim="Residual programs require direct evidence boundaries.",
            evidence_keys=["Cords2023Cancerassociated", "Croizer2024Deciphering"],
            direct_evidence_keys=[],
            adjacent_evidence_keys=["Cords2023Cancerassociated", "Croizer2024Deciphering"],
        )

        result = evaluate_candidate(
            "Cancer-associated fibroblasts in residual breast tumors show distinct spatial organization "
            "and functional states [@Cords2023Cancerassociated; @Croizer2024Deciphering]. "
            "Cords and Croizer show evidence tiers but overreach here.",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s5_caf_adjacent_source_promoted_to_residual_evidence" in result.failure_class

    def test_section_rewrite_preserves_section_scoped_must_cites(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Smith2024,\n title={Direct}\n}\n@article{Jiang2019Genomic,\n title={Required}\n}\n",
            encoding="utf-8",
        )
        (tmp_path / "reference-map.json").write_text(
            json.dumps(
                {
                    "references": [
                        {
                            "citekey": "Smith2024",
                            "bibliographic_validity": "citable",
                            "citation_policy": "must_cite",
                            "sections": ["S1"],
                        },
                        {
                            "citekey": "Jiang2019Genomic",
                            "bibliographic_validity": "citable",
                            "citation_policy": "must_cite",
                            "sections": ["S5"],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "write.md").write_text(
            "### S1: Other\n\nSmith shows another result [@Smith2024].\n\n"
            "### S5: Residual programs\n\nThe old section is being replaced.\n",
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S5",
            title="Residual programs",
            controlling_claim="Residual programs require direct evidence.",
            evidence_keys=["Jiang2019Genomic"],
            direct_evidence_keys=["Jiang2019Genomic"],
        )

        result = evaluate_candidate(
            "Direct evidence shows the residual program remains bounded [@Smith2024].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "missing_must_cite_after_section_rewrite" in result.failure_class

    def test_s5_round11_metabolomic_and_im_misuse_are_blocked(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Wei2013Metabolomics,\n title={Serum metabolomics}\n}\n"
            "@article{Talarico2024Metabolomic,\n title={Plasma metabolomics}\n}\n"
            "@article{Liu2024Metabolic,\n title={Review}\n}\n"
            "@article{Im2025Genomic,\n title={Residual TNBC MIRINAE}\n}\n",
            encoding="utf-8",
        )
        (tmp_path / "reference-map.json").write_text(
            json.dumps(
                {
                    "references": [
                        {"citekey": "Wei2013Metabolomics", "bibliographic_validity": "citable"},
                        {"citekey": "Talarico2024Metabolomic", "bibliographic_validity": "citable"},
                        {"citekey": "Liu2024Metabolic", "bibliographic_validity": "citable"},
                        {"citekey": "Im2025Genomic", "bibliographic_validity": "citable"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S5",
            title="Residual programs",
            controlling_claim="Residual programs require direct evidence boundaries.",
            evidence_keys=[
                "Wei2013Metabolomics",
                "Talarico2024Metabolomic",
                "Liu2024Metabolic",
                "Im2025Genomic",
            ],
        )

        result = evaluate_candidate(
            "Wei and colleagues profiled residual breast tumors and fatty acid oxidation "
            "intermediates [@Wei2013Metabolomics]. Talarico reported residual TNBC RCB-II/III "
            "nucleotide biosynthesis and glutathione signals [@Talarico2024Metabolomic]. "
            "Liu2024Metabolic supports residual TNBC FAO poor prognosis [@Liu2024Metabolic]. "
            "Im2025Genomic describes HER2-positive residual genomics [@Im2025Genomic].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s5_wei_serum_metabolomics_promoted_to_residual_tissue" in result.failure_class
        assert "s5_talarico_serum_metabolomics_promoted_to_residual_tnbc" in result.failure_class
        assert "s5_liu_review_promoted_to_residual_tnbc_metabolism" in result.failure_class
        assert "s5_im_tnbc_mirinae_promoted_to_her2_positive" in result.failure_class

    def test_s6_round11_ctdna_superiority_misuse_is_blocked(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Dong2025Unraveling,\n title={Integrated analysis}\n}\n"
            "@article{Magbanua2021Circulating,\n title={ctDNA}\n}\n",
            encoding="utf-8",
        )
        (tmp_path / "reference-map.json").write_text(
            json.dumps(
                {
                    "references": [
                        {"citekey": "Dong2025Unraveling", "bibliographic_validity": "citable"},
                        {"citekey": "Magbanua2021Circulating", "bibliographic_validity": "citable"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S6",
            title="MRD",
            controlling_claim="ctDNA evidence remains bounded.",
            evidence_keys=["Dong2025Unraveling", "Magbanua2021Circulating"],
        )

        result = evaluate_candidate(
            "Dong and colleagues showed the strongest single predictor of distant recurrence, "
            "outperforming RCB in multivariable models [@Dong2025Unraveling]. "
            "Magbanua2021Circulating exceeded conventional clinicopathologic factors [@Magbanua2021Circulating].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s6_dong_promoted_to_superiority_or_rcb_comparison" in result.failure_class
        assert "s6_magbanua_unverified_clinicopathologic_superiority" in result.failure_class

    def test_s5_round12_jiang_and_im_misuse_are_blocked(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Jiang2019Genomic,\n title={Primary TNBC}\n}\n"
            "@article{Im2025Genomic,\n title={MIRINAE}\n}\n",
            encoding="utf-8",
        )
        (tmp_path / "reference-map.json").write_text(
            json.dumps(
                {
                    "references": [
                        {"citekey": "Jiang2019Genomic", "bibliographic_validity": "citable"},
                        {"citekey": "Im2025Genomic", "bibliographic_validity": "citable"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S5",
            title="Residual programs",
            controlling_claim="Residual programs require direct evidence boundaries.",
            evidence_keys=["Jiang2019Genomic", "Im2025Genomic"],
        )

        result = evaluate_candidate(
            "Jiang and colleagues showed clonal diversity in 50 residual TNBCs after neoadjuvant therapy "
            "[@Jiang2019Genomic]. Im2025Genomic used whole-exome sequencing in 30 residual cases and found "
            "MYC and CCND1 copy-number enrichment [@Im2025Genomic].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s5_jiang_primary_tnbc_promoted_to_residual_tnbc" in result.failure_class
        assert "s5_im_mirinae_evidence_inflated" in result.failure_class

    def test_s6_round12_mcdonald_dong_and_sensitivity_arithmetic_are_blocked(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{McDonald2019Personalized,\n title={TARDIS}\n}\n"
            "@article{Dong2025Unraveling,\n title={NAC multi-omic}\n}\n",
            encoding="utf-8",
        )
        (tmp_path / "reference-map.json").write_text(
            json.dumps(
                {
                    "references": [
                        {"citekey": "McDonald2019Personalized", "bibliographic_validity": "citable"},
                        {"citekey": "Dong2025Unraveling", "bibliographic_validity": "citable"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S6",
            title="MRD",
            controlling_claim="ctDNA evidence remains bounded.",
            evidence_keys=["McDonald2019Personalized", "Dong2025Unraveling"],
        )

        result = evaluate_candidate(
            "McDonald and colleagues followed 142 patients after surgery and adjuvant chemotherapy, "
            "reporting an 8-10 month lead time [@McDonald2019Personalized]. Dong2025Unraveling showed "
            "matched ctDNA enrichment in residual tumor transcriptomes from 50 patients with TNBC "
            "[@Dong2025Unraveling]. The sensitivity was approximately 50%, so half of eventual recurrences "
            "were ctDNA-negative.",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s6_mcdonald_tardis_promoted_to_recurrence_lead_time" in result.failure_class
        assert "s6_dong_residual_tnbc_ctdna_concordance_overframed" in result.failure_class
        assert "s6_unsupported_ctdna_sensitivity_arithmetic" in result.failure_class

    def test_s7_round12_unqualified_current_standard_is_blocked(self, tmp_path):
        _write_boundary(tmp_path)
        kernel = SectionKernel(
            section_id="S7",
            title="Trials",
            controlling_claim="Clinical evidence must be ranked.",
            evidence_keys=["Smith2024"],
        )

        result = evaluate_candidate(
            "CREATE-X, OlympiA, initial KATHERINE, EA1131, biomarker-risk bridge, registry-only "
            "hypotheses, and currentness gaps form the hierarchy. T-DM1 is the current standard "
            "for HER2-positive residual disease [@Smith2024].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s7_unqualified_current_standard_wording" in result.failure_class

    def test_s7_yau_ctdna_mismatch_and_missing_maturity_narrative_are_blocked(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text("@article{Yau2022Residual,\n title={RCB}\n}\n", encoding="utf-8")
        (tmp_path / "reference-map.json").write_text(
            json.dumps({"references": [{"citekey": "Yau2022Residual", "bibliographic_validity": "citable"}]}),
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S7",
            title="Trials",
            controlling_claim="Clinical evidence must be ranked.",
            evidence_keys=["Yau2022Residual"],
        )

        result = evaluate_candidate(
            "The I-SPY2 ctDNA result was insufficient for de-escalation [@Yau2022Residual].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s7_yau_rcb_cited_for_ctdna_or_deescalation" in result.failure_class
        assert "s7_missing_evidence_maturity_narrative" in result.failure_class

    def test_s7_geyer_cannot_support_katherine_final_os(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Geyer2022Overall,\n title={OlympiA}\n}\n"
            "@article{Mayer2021Randomized,\n title={EA1131}\n}\n",
            encoding="utf-8",
        )
        (tmp_path / "reference-map.json").write_text(
            json.dumps(
                {
                    "references": [
                        {"citekey": "Geyer2022Overall", "bibliographic_validity": "citable"},
                        {"citekey": "Mayer2021Randomized", "bibliographic_validity": "citable"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S7",
            title="Trials",
            controlling_claim="Clinical evidence must be ranked.",
            evidence_keys=["Geyer2022Overall", "Mayer2021Randomized"],
        )

        result = evaluate_candidate(
            "CREATE-X, OlympiA, initial KATHERINE, EA1131, biomarker-risk bridge, registry-only "
            "hypotheses, and currentness gaps form the hierarchy. The KATHERINE final overall "
            "survival analysis was confirmed [@Geyer2022Overall].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "katherine_final_or_os_claim_without_retained_full_text" in result.failure_class

    def test_s7_currentness_records_cannot_support_fda_or_publication_status_in_prose(self, tmp_path):
        _write_boundary(tmp_path)
        kernel = SectionKernel(
            section_id="S7",
            title="Trials",
            controlling_claim="Currentness records stay non-citable.",
            evidence_keys=["Smith2024"],
        )

        result = evaluate_candidate(
            "CREATE-X, OlympiA, initial KATHERINE, EA1131, biomarker-risk bridge, registry-only "
            "hypotheses, and currentness gaps form the hierarchy. DESTINY-Breast05 and the "
            "May 15, 2026 FDA adjuvant T-DXd approval remain non-citable until local full text "
            "is retained.",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s7_currentness_only_record_promoted_to_status_claim" in result.failure_class

    def test_s7_keynote522_cannot_be_promoted_to_standard_claim(self, tmp_path):
        _write_boundary(tmp_path)
        kernel = SectionKernel(
            section_id="S7",
            title="Trials",
            controlling_claim="KEYNOTE-522 remains table-only currentness context.",
            evidence_keys=["Smith2024"],
        )

        result = evaluate_candidate(
            "CREATE-X, OlympiA, initial KATHERINE, EA1131, biomarker-risk bridge, registry-only "
            "hypotheses, and currentness gaps form the hierarchy. The KEYNOTE-522 trial established "
            "perioperative pembrolizumab as a standard for early triple-negative breast cancer, but "
            "the retained evidence does not support current-standard status.",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "keynote522_promoted_to_standard_claim" in result.failure_class

    def test_s7_registry_table_rows_cannot_duplicate_boundary_warning(self, tmp_path):
        _write_boundary(tmp_path)
        kernel = SectionKernel(
            section_id="S7",
            title="Trials",
            controlling_claim="Registry rows use one boundary cell.",
            evidence_keys=["Smith2024"],
        )

        result = evaluate_candidate(
            "CREATE-X, OlympiA, initial KATHERINE, EA1131, biomarker-risk bridge, registry-only "
            "hypotheses, and currentness gaps form the hierarchy.\n\n"
            "| trial | endpoint | claim license | currentness boundary |\n"
            "|---|---|---|---|\n"
            "| NCT03703427 | registry-defined endpoint only | Registry-only grouping; no efficacy, safety, survival, approval, or comparative treatment-effect conclusion. | Registry-only grouping; no efficacy, safety, survival, approval, or comparative treatment-effect conclusion. |",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s7_registry_table_boundary_duplicated" in result.failure_class

    def test_generic_failure_test_instruction_accepts_failure_test_sentence(self, tmp_path):
        _write_boundary(tmp_path)
        kernel = SectionKernel(
            section_id="S1",
            title="Direct",
            controlling_claim="Smith shows the direct finding.",
            evidence_keys=["Smith2024"],
            direct_evidence_keys=["Smith2024"],
            failure_test="direct evidence leads",
        )
        result = evaluate_candidate(
            "Smith shows that the direct endpoint constrains the broader claim [@Smith2024]. "
            "A possible failure test would be a prospective cohort that breaks this association.",
            tmp_path,
            kernel,
        )

        assert result.status == "PASS"
        assert result.hard_fail is False

    def test_single_not_but_contrast_is_not_hard_banned(self, tmp_path):
        _write_boundary(tmp_path)
        result = evaluate_candidate(
            "Smith shows the result is not simply a bulk signal but a direct endpoint constraint [@Smith2024].",
            tmp_path,
        )

        assert "banned_pattern" not in result.failure_class

    def test_repeated_not_but_packaging_is_hard_banned(self, tmp_path):
        _write_boundary(tmp_path)
        result = evaluate_candidate(
            "Smith shows the result is not simply a signal but a constraint [@Smith2024]. "
            "It is not merely a method but a framework.",
            tmp_path,
        )

        assert result.status == "REWRITE_REQUIRED_STYLE"
        assert "banned_pattern" in result.failure_class

    def test_s4_denkert_cannot_be_promoted_to_residual_specimen_til_evidence(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Denkert2018Tumourinfiltrating,\n title={Denkert}\n}\n",
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S4",
            title="Residual immune ecology",
            controlling_claim="Sample state must be explicit.",
            evidence_keys=["Denkert2018Tumourinfiltrating"],
        )

        result = evaluate_candidate(
            "The strongest direct residual evidence comes from residual specimens. In a pooled "
            "analysis of 3,771 patients treated with neoadjuvant chemotherapy across nine trials, "
            "Denkert and colleagues demonstrated that higher stromal TILs in residual disease were "
            "independently associated with survival [@Denkert2018Tumourinfiltrating].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s4_denkert2018_promoted_to_residual_specimen_evidence" in result.failure_class
        assert "s4_denkert2018_wrong_trial_count" in result.failure_class

    def test_s4_pinard_cannot_support_unretained_intermediate_rcb_hr(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Pinard2020Residual,\n title={Pinard}\n}\n",
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S4",
            title="Residual immune ecology",
            controlling_claim="Quantitative claims must match retained evidence.",
            evidence_keys=["Pinard2020Residual"],
        )

        result = evaluate_candidate(
            "Pinard extended this by studying residual TNBC [@Pinard2020Residual]. In their "
            "analysis of 146 TNBC patients, the hazard ratio for recurrence was 0.32 in the "
            "intermediate RCB stratum.",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s4_pinard2020_wrong_146_patient_claim" in result.failure_class
        assert "s4_pinard2020_wrong_hr_032_claim" in result.failure_class
        assert "s4_pinard2020_unlicensed_intermediate_rcb_interaction" in result.failure_class

    def test_s4_luen_cannot_inherit_denkert_sample_or_her2_scope(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Luen2019Prognostic,\n title={Luen}\n}\n",
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S4",
            title="Residual immune ecology",
            controlling_claim="Sample and subtype scope must match retained evidence.",
            evidence_keys=["Luen2019Prognostic"],
        )

        result = evaluate_candidate(
            "In a pooled analysis of 3771 patients, residual stromal TILs retained "
            "prognostic value in TNBC and HER2-positive subtypes [@Luen2019Prognostic].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s4_luen2019_wrong_denkert_sample_size" in result.failure_class
        assert "s4_luen2019_wrong_her2_positive_scope" in result.failure_class

    def test_s4_lejeune_cannot_support_unretained_stromal_til_hr(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Lejeune2023Prognostic,\n title={Lejeune}\n}\n",
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S4",
            title="Residual immune ecology",
            controlling_claim="Marker license must match retained evidence.",
            evidence_keys=["Lejeune2023Prognostic"],
        )

        result = evaluate_candidate(
            "A study of 118 residual TNBC specimens found that stromal TILs remained "
            "independently prognostic for disease-free survival after adjusting for RCB "
            "(HR 0.95 per 10% increment, p=0.04) [@Lejeune2023Prognostic].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s4_lejeune2023_wrong_118_sample_size" in result.failure_class
        assert "s4_lejeune2023_wrong_rcb_adjusted_claim" in result.failure_class
        assert "s4_lejeune2023_wrong_dfs_hr_p_claim" in result.failure_class

    def test_s4_blaye_cannot_blend_signature_families_or_unretained_dmfs(self, tmp_path):
        _write_boundary(tmp_path)
        (tmp_path / "references.bib").write_text(
            "@article{Blaye2022Immunological,\n title={Blaye}\n}\n",
            encoding="utf-8",
        )
        kernel = SectionKernel(
            section_id="S4",
            title="Residual immune ecology",
            controlling_claim="Signature families must stay separate.",
            evidence_keys=["Blaye2022Immunological"],
        )

        result = evaluate_candidate(
            "In 146 residual TNBC specimens, Blaye used a 12-gene signature including "
            "CD8A, GZMB, PRF1, and CXCL9, with 5-year distant metastasis-free survival "
            "of 91% versus 56% independent of RCB [@Blaye2022Immunological].",
            tmp_path,
            kernel,
        )

        assert result.status == "BLOCKED_BY_EVIDENCE_BOUNDARY"
        assert "s4_blaye2022_wrong_146_analyzed_claim" in result.failure_class
        assert "s4_blaye2022_wrong_main_12_gene_signature" in result.failure_class
        assert "s4_blaye2022_wrong_main_signature_genes" in result.failure_class
        assert "s4_blaye2022_unlicensed_dmfs_values" in result.failure_class
        assert "s4_blaye2022_unlicensed_rcb_independence_claim" in result.failure_class
