"""Deterministic early gates for write-agent candidates."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from autor.write_agent.models import CandidateScore, SectionKernel
from autor.write_agent.preflight import load_reference_policy
from autor.write_agent.workspace_io import (
    extract_citekeys,
    parse_bibtex_keys,
    read_jsonl,
    read_text,
    sidecars_dir,
    write_jsonl,
    write_text,
)

BANNED_PATTERNS = [
    r"not simply\b.*\bbut\b",
    r"not merely\b.*\bbut\b",
    r"不是.*而是",
]

FRAMEWORK_NOUNS = [
    "framework",
    "scaffold",
    "landscape",
    "layer",
    "spectrum",
    "骨架",
    "层面",
    "谱系",
    "图谱",
    "框架",
]

GENERIC_ENDINGS = [
    "future studies are needed",
    "further validation is required",
    "provides new insights",
    "临床转化仍面临挑战",
    "仍需进一步研究",
]

ADJUDICATIVE_TERMS = [
    "shows",
    "show",
    "demonstrates",
    "demonstrated",
    "indicates",
    "identified",
    "supports",
    "challenges",
    "fails",
    "failed",
    "outperforms",
    "undercuts",
    "constrains",
    "constrained",
    "suggests",
    "establishes",
    "established",
    "improves",
    "improved",
    "limits",
    "limited",
    "reveals",
    "argues",
    "therefore",
    "因此",
    "显示",
    "支持",
    "削弱",
    "限制",
]

FAILURE_TEST_TERMS = [
    "failure test",
    "critical test",
    "decisive test",
    "prospective test",
    "would be tested",
    "would test",
]

GENERIC_FAILURE_TESTS = {
    "direct evidence leads",
}

FORBIDDEN_LEAPS = [
    " [l6]",
    "proves clinical efficacy",
    "guarantees clinical benefit",
    "establishes clinical efficacy",
    "definitively proves",
    "必然改善",
    "证明临床获益",
]

S7_FORBIDDEN_CLINICAL_CLAIMS = [
    (
        r"\bS1418\b",
        "s7_registry_record_in_prose",
    ),
    (
        r"\bS1418\b.{0,160}\b(reported results|did not meet|failed|primary endpoint|efficacy|benefit)\b",
        "s1418_registry_promoted_to_outcome",
    ),
    (
        r"\bSchmid2020Pembrolizumab\b.{0,220}\b(event-free survival|efs|overall survival|os|survival improvement)\b",
        "keynote522_survival_claim_from_pcr_paper",
    ),
    (
        r"\bKEYNOTE-522\b.{0,220}\b(improv(?:es|ed|ing).{0,60}event-free survival|event-free survival improvement|overall survival improvement|efs benefit|os benefit)\b",
        "keynote522_survival_claim_without_local_paper",
    ),
    (
        r"\bKEYNOTE-522\b.{0,220}\b(?:establish(?:ed|es)?|became|is|as)\b.{0,80}\b(?:standard|standard[- ]of[- ]care|clinical backbone|evidence backbone)\b",
        "keynote522_promoted_to_standard_claim",
    ),
    (
        r"\b(?:perioperative\s+)?pembrolizumab\b.{0,120}\b(?:establish(?:ed|es)?|became|is|as)\b.{0,80}\b(?:standard|standard[- ]of[- ]care|clinical backbone|evidence backbone)\b",
        "keynote522_promoted_to_standard_claim",
    ),
    (
        r"\b(?:standard|standard[- ]of[- ]care|clinical backbone|evidence backbone)\b.{0,120}\b(?:KEYNOTE-522|perioperative\s+pembrolizumab|pembrolizumab)\b",
        "keynote522_promoted_to_standard_claim",
    ),
    (
        r"\bEA1131\b.{0,180}\b(failed|failure|did not show superiority|no superiority|no benefit|closed early|improve outcomes|efficacy)\b",
        "ea1131_registry_promoted_to_outcome",
    ),
    (
        r"\b(failure|negative result|negative results)\b.{0,80}\bEA1131\b",
        "ea1131_registry_promoted_to_outcome",
    ),
    (
        r"\bKATHERINE\b.{0,220}\b(?:final|overall survival|OS|IDFS)\b.{0,220}\bGeyer2022Overall\b",
        "katherine_final_or_os_claim_without_retained_full_text",
    ),
    (
        r"\bGeyer2022Overall\b.{0,220}\bKATHERINE\b.{0,220}\b(?:final|overall survival|OS|IDFS)\b",
        "katherine_final_or_os_claim_without_retained_full_text",
    ),
]

S5_FORBIDDEN_CAF_CLAIMS = [
    (
        r"\b(?:CAF(?:s)?|cancer-associated fibroblasts)\b.{0,80}\bresidual breast (?:tumou?rs?|tissue|cancer|disease)\b.{0,140}\b(?:show|shows|exhibit|exhibits|demonstrat(?:e|es|ed)|identify|support|create|drive)\b.{0,220}\b(?:Cords2023Cancerassociated|Croizer2024Deciphering)\b",
        "s5_caf_adjacent_source_promoted_to_residual_evidence",
    ),
    (
        r"\b(?:Cords2023Cancerassociated|Croizer2024Deciphering)\b.{0,260}\b(?:residual tumor survival|residual tumour survival|residual breast|post[- ]?neoadjuvant|post[- ]?NAC|therapy[- ]?resistant niche|therapy[- ]?induced CAF|immune exclusion)\b",
        "s5_caf_adjacent_source_promoted_to_residual_evidence",
    ),
    (
        r"\b(?:Cords|Croizer)\b.{0,220}\b(?:contribute to residual tumor survival|contribute to residual tumour survival|support residual tumor|support residual tumour|create spatial niches that support tumor cell proliferation|create spatial niches that support tumour cell proliferation|immune exclusion)\b",
        "s5_caf_adjacent_source_promoted_to_residual_evidence",
    ),
]

S5_CAF_BOUNDARY_TERMS = [
    "neither study",
    "did not examine",
    "do not directly",
    "does not directly",
    "not directly",
    "not established",
    "not yet established",
    "do not establish",
    "does not establish",
    "remains sparse",
    "remain sparse",
    "evidence remains sparse",
    "direct evidence for caf",
    "direct post-neoadjuvant residual caf evidence",
    "vocabulary",
    "adjacent",
]

S5_FORBIDDEN_ROUND11_CLAIMS = [
    (
        r"\bWei(?:\s+and\s+colleagues)?\b.{0,180}\bresidual breast (?:tumou?rs?|tissue|cancer|disease)\b",
        "s5_wei_serum_metabolomics_promoted_to_residual_tissue",
    ),
    (
        r"\bWei2013Metabolomics\b.{0,240}\b(?:residual breast|fatty acid oxidation|fatty-acid oxidation|oxidation intermediates)\b",
        "s5_wei_serum_metabolomics_promoted_to_residual_tissue",
    ),
    (
        r"\bTalarico(?:\s+and\s+colleagues)?\b.{0,220}\b(?:residual TNBC|RCB[- ]?(?:II|III|2|3)|nucleotide biosynthesis|glutathione)\b",
        "s5_talarico_serum_metabolomics_promoted_to_residual_tnbc",
    ),
    (
        r"\bTalarico2024Metabolomic\b.{0,260}\b(?:residual TNBC|RCB[- ]?(?:II|III|2|3)|nucleotide biosynthesis|glutathione)\b",
        "s5_talarico_serum_metabolomics_promoted_to_residual_tnbc",
    ),
    (
        r"\bLiu2024Metabolic\b.{0,260}\b(?:residual TNBC|fatty acid oxidation|fatty-acid oxidation|FAO|gene-expression signature|poor prognosis)\b",
        "s5_liu_review_promoted_to_residual_tnbc_metabolism",
    ),
    (
        r"\bLiu(?:\s+and\s+colleagues)?\b.{0,220}\b(?:residual TNBC|fatty acid oxidation|fatty-acid oxidation|FAO|gene-expression signature|poor prognosis)\b",
        "s5_liu_review_promoted_to_residual_tnbc_metabolism",
    ),
    (
        r"\bIm(?:\s+and\s+colleagues)?\b.{0,180}\bHER2[- ]positive\b.{0,180}\bresidual",
        "s5_im_tnbc_mirinae_promoted_to_her2_positive",
    ),
    (
        r"\bIm2025Genomic\b.{0,220}\bHER2[- ]positive\b",
        "s5_im_tnbc_mirinae_promoted_to_her2_positive",
    ),
]

S6_FORBIDDEN_ROUND11_CLAIMS = [
    (
        r"\bDong(?:\s+and\s+colleagues)?\b.{0,260}\b(?:strongest single predictor|outperform(?:ed|ing)? RCB|distant recurrence|multivariable models?)\b",
        "s6_dong_promoted_to_superiority_or_rcb_comparison",
    ),
    (
        r"\bDong2025Unraveling\b.{0,280}\b(?:strongest single predictor|outperform(?:ed|ing)? RCB|distant recurrence|multivariable models?)\b",
        "s6_dong_promoted_to_superiority_or_rcb_comparison",
    ),
    (
        r"\bMagbanua2021Circulating\b.{0,260}\b(?:exceed(?:ed|s|ing)? conventional clinicopathologic|outperform(?:ed|s|ing)? conventional clinicopathologic|stronger than conventional clinicopathologic)\b",
        "s6_magbanua_unverified_clinicopathologic_superiority",
    ),
    (
        r"\bMagbanua(?:\s+and\s+colleagues)?\b.{0,260}\b(?:exceed(?:ed|s|ing)? conventional clinicopathologic|outperform(?:ed|s|ing)? conventional clinicopathologic|stronger than conventional clinicopathologic)\b",
        "s6_magbanua_unverified_clinicopathologic_superiority",
    ),
]

S5_FORBIDDEN_ROUND12_CLAIMS = [
    (
        r"\bJiang(?:\s+and\s+colleagues)?\b.{0,220}\b(?:residual\s+TNBC|residual\s+triple-negative|post[- ]?NAC|after\s+neoadjuvant|50\s+residual|clonal\s+diversity|subclonal|emerg(?:ing|ed)|persist(?:ing|ed))\b",
        "s5_jiang_primary_tnbc_promoted_to_residual_tnbc",
    ),
    (
        r"\b(?:residual\s+TNBC|residual\s+triple-negative|post[- ]?NAC|after\s+neoadjuvant|50\s+residual|clonal\s+diversity|subclonal|emerg(?:ing|ed)|persist(?:ing|ed))\b.{0,220}\bJiang2019Genomic\b",
        "s5_jiang_primary_tnbc_promoted_to_residual_tnbc",
    ),
    (
        r"\bJiang2019Genomic\b.{0,260}\b(?:residual\s+TNBC|residual\s+triple-negative|post[- ]?NAC|after\s+neoadjuvant|50\s+residual|clonal\s+diversity|subclonal|emerg(?:ing|ed)|persist(?:ing|ed))\b",
        "s5_jiang_primary_tnbc_promoted_to_residual_tnbc",
    ),
    (
        r"\bIm(?:\s+and\s+colleagues)?\b.{0,220}\b(?:30\s+residual|30\s+cases?|whole[- ]?exome|WES|MYC|CCND1|copy[- ]?number\s+(?:alterations?|enrichment)|enriched\s+post[- ]?treatment)\b",
        "s5_im_mirinae_evidence_inflated",
    ),
    (
        r"\bIm2025Genomic\b.{0,260}\b(?:30\s+residual|30\s+cases?|whole[- ]?exome|WES|MYC|CCND1|copy[- ]?number\s+(?:alterations?|enrichment)|enriched\s+post[- ]?treatment)\b",
        "s5_im_mirinae_evidence_inflated",
    ),
]

S6_FORBIDDEN_ROUND12_CLAIMS = [
    (
        r"\bMcDonald(?:\s+and\s+colleagues)?\b.{0,260}\b(?:142\s+patients?|post[- ]?surgery|after\s+surgery|adjuvant\s+chemotherapy|lead\s*time|8[–-]10\s+months?|metastatic\s+recurrence|sensitivity\s*(?:~|approximately|about)?\s*\d+%)\b",
        "s6_mcdonald_tardis_promoted_to_recurrence_lead_time",
    ),
    (
        r"\bMcDonald2019Personalized\b.{0,300}\b(?:142\s+patients?|post[- ]?surgery|after\s+surgery|adjuvant\s+chemotherapy|lead\s*time|8[–-]10\s+months?|metastatic\s+recurrence|sensitivity\s*(?:~|approximately|about)?\s*\d+%)\b",
        "s6_mcdonald_tardis_promoted_to_recurrence_lead_time",
    ),
    (
        r"\bDong(?:\s+and\s+colleagues)?\b.{0,320}\b(?:50\s+patients?|50\s+.*TNBC|residual\s+tumou?r\s+transcriptomes?|matched\s+ctDNA|ctDNA\s+detection\s+(?:was\s+)?enriched|high[- ]risk\s+residual\s+gene[- ]expression|imperfect\s+concordance)\b",
        "s6_dong_residual_tnbc_ctdna_concordance_overframed",
    ),
    (
        r"\bDong2025Unraveling\b.{0,340}\b(?:50\s+patients?|50\s+.*TNBC|residual\s+tumou?r\s+transcriptomes?|matched\s+ctDNA|ctDNA\s+detection\s+(?:was\s+)?enriched|high[- ]risk\s+residual\s+gene[- ]expression|imperfect\s+concordance)\b",
        "s6_dong_residual_tnbc_ctdna_concordance_overframed",
    ),
    (
        r"\b(?:sensitivity|false[- ]negative|false negative)\b.{0,80}\b\d+(?:\.\d+)?\s*%",
        "s6_unsupported_ctdna_sensitivity_arithmetic",
    ),
    (
        r"\b(?:approximately\s+)?half\s+of\s+eventual\s+recurrences\b",
        "s6_unsupported_ctdna_sensitivity_arithmetic",
    ),
    (
        r"\bctDNA[- ]negative\b.{0,120}\b(?:half|50\s*%)\b",
        "s6_unsupported_ctdna_sensitivity_arithmetic",
    ),
]

S7_FORBIDDEN_CURRENT_STANDARD_PATTERNS = [
    r"\bcurrent\s+standard(?:s)?(?:\s+of\s+care)?\b",
    r"\bcurrent\s+one-size-fits-all\s+standards?\b",
]

S7_CURRENTNESS_STATUS_PATTERNS = [
    (
        r"\b(?:DESTINY[- ]Breast05|T[- ]DXd|trastuzumab\s+deruxtecan|NCT04622319|10\.1056/NEJMoa2514661|41370739)\b.{0,180}\b(?:FDA|approval|approved|reported|published|full\s+publication|May\s+15,\s+2026)\b",
        "s7_currentness_only_record_promoted_to_status_claim",
    ),
    (
        r"\b(?:FDA|approval|approved|reported|published|full\s+publication|May\s+15,\s+2026)\b.{0,180}\b(?:DESTINY[- ]Breast05|T[- ]DXd|trastuzumab\s+deruxtecan|NCT04622319|10\.1056/NEJMoa2514661|41370739)\b",
        "s7_currentness_only_record_promoted_to_status_claim",
    ),
]

S7_REGISTRY_DUPLICATE_BOUNDARY_TEXT = (
    "Registry-only grouping; no efficacy, safety, survival, approval, or comparative treatment-effect conclusion."
)

S7_EVIDENCE_MATURITY_MARKERS = [
    ("CREATE-X or Masuda", ("create-x", "masuda")),
    ("OlympiA or Geyer", ("olympia", "geyer")),
    ("initial KATHERINE or T-DM1", ("katherine", "t-dm1")),
    ("EA1131 or Mayer", ("ea1131", "mayer")),
    ("biomarker-risk bridge", ("biomarker-risk bridge", "prognostic bridge", "biomarker risk bridge")),
    ("registry-only hypotheses", ("registry-only", "registry only")),
    ("acquisition/currentness gaps", ("currentness", "acquisition")),
]

S3_PARK2025_FORBIDDEN_SEGMENT_PATTERNS = [
    (
        r"\b(?:residual\s+(?:tumou?rs?|tissue|disease)|post[- ]?neoadjuvant|post[- ]?NAC)\b",
        "s3_park2025_promoted_to_residual_tissue",
    ),
    (
        r"\b(?:direct\s+residual[- ]?spatial|residual[- ]?spatial|spatial\s+MRD)\b",
        "s3_park2025_promoted_to_direct_residual_spatial",
    ),
    (
        r"\b(?:recurrence[- ]?free\s+survival|relapse[- ]?free\s+survival|shorter\s+RFS|RFS|survival)\b",
        "s3_park2025_promoted_to_survival_or_prognosis",
    ),
    (
        r"\b(?:RCB[- ]?independent|independent\s+of\s+RCB|independent[- ]of[- ]RCB|RCB[- ]adjusted|residual[- ]burden[- ]independent)\b",
        "s3_park2025_promoted_to_rcb_independent_prognosis",
    ),
    (
        r"\b(?:profiled|profiling|study\s+of)\b.{0,80}\bresidual\b",
        "s3_park2025_promoted_to_residual_profiling",
    ),
    (
        r"\b(?:recurrence|prognostic|prognosis)\b.{0,120}\b(?:association|information|value|endpoint|evidence)\b",
        "s3_park2025_promoted_to_residual_prognosis",
    ),
]

S3_PARK2025_BOUNDARY_TERMS = [
    "adjacent",
    "pretreatment",
    "pre-treatment",
    "biopsy",
    "pcr versus non-pcr",
    "pcr vs non-pcr",
    "response-context",
    "response context",
    "not direct",
    "not residual",
    "not as residual",
    "not a residual",
    "must not",
    "cannot support",
    "does not support",
    "do not support",
    "no residual",
    "rather than",
]

S3_PARK2025_NEGATING_TERMS = [
    "not",
    "must not",
    "cannot support",
    "does not support",
    "do not support",
    "no ",
    "rather than",
]

S3_FERNANDEZ2025_FORBIDDEN_SEGMENT_PATTERNS = [
    (
        r"\b(?:direct\s+residual[- ]?spatial|residual[- ]?spatial|spatial\s+architecture|spatially\s+defined|spatial\s+profil(?:e|ing)|spatial\s+evidence)\b",
        "s3_fernandez2025_promoted_to_spatial_evidence",
    ),
    (
        r"\b(?:proteomic|proteomics|proteome|protein\s+profil(?:e|ing)|protein\s+spatial|spatial\s+proteomic)\b",
        "s3_fernandez2025_promoted_to_proteomic_evidence",
    ),
    (
        r"\b(?:GeoMx|DSP|digital\s+spatial\s+profiling|multiplex(?:ed)?\s+immunofluorescence|imaging\s+mass\s+cytometry)\b",
        "s3_fernandez2025_promoted_to_spatial_platform",
    ),
    (
        r"\b(?:387\s+(?:HER2|residual|patients?|cases?)|pertuzumab)\b",
        "s3_fernandez2025_unlicensed_cohort_or_treatment_detail",
    ),
    (
        r"\b(?:single[- ]cell|cellular\s+resolution|compartment[- ]level|compartmental|tumor\s+nest|invasive\s+margin|region(?:s)?\s+of\s+interest)\b",
        "s3_fernandez2025_promoted_to_compartment_or_single_cell_claim",
    ),
]

S3_FERNANDEZ2025_ALLOWED_TERMS = [
    "gene expression",
    "immune signature",
    "immune-related",
    "her2",
    "event-free survival",
    "efs",
    "residual disease",
    "rd samples",
    "paired baseline",
    "post-treatment",
]

S3_WANG2023_FORBIDDEN_SEGMENT_PATTERNS = [
    (
        r"\b(?:direct\s+residual[- ]?spatial|residual[- ]?spatial|residual\s+TNBC\s+specimens?|residual\s+tumou?rs?|residual\s+tissue)\b",
        "s3_wang2023_promoted_to_direct_residual_spatial",
    ),
    (
        r"\b(?:DSP|digital\s+spatial\s+profiling|multiplex\s+immunofluorescence|multiplex\s+IF)\b",
        "s3_wang2023_wrong_platform",
    ),
    (
        r"\b(?:pembrolizumab|chemo[- ]?pembrolizumab|chemotherapy\s+plus\s+pembrolizumab)\b",
        "s3_wang2023_wrong_treatment_context",
    ),
    (
        r"\b(?:CD8[-+– ]+PD[- ]?L1|PD[- ]?L1.*macrophage|macrophage[- ]restricted\s+PD[- ]?L1|CD8.*tumou?r\s+nest|immune\s+exclusion)\b",
        "s3_wang2023_unlicensed_residual_immune_claim",
    ),
    (
        r"\bno\s+pretreatment\s+biopsy\s+spatial\s+data\b|\bwithout\s+pretreatment\s+spatial\s+data\b",
        "s3_wang2023_wrong_sampling_boundary",
    ),
]

S3_NIMBALKAR2025_FORBIDDEN_SEGMENT_PATTERNS = [
    (
        r"\b(?:residual\s+TNBC|residual\s+tumou?rs?|residual\s+specimens?|residual\s+disease\s+showed|residual\s+immune)\b",
        "s3_nimbalkar2025_promoted_to_residual_evidence",
    ),
    (
        r"\b(?:matched\s+pretreatment|matched\s+pre[- ]?treatment|paired\s+pre|paired\s+baseline|pre[- ]?post|post[- ]?treatment)\b",
        "s3_nimbalkar2025_wrong_paired_design",
    ),
    (
        r"\b(?:35[- ]?plex|imaging\s+mass\s+cytometry|IMC|single[- ]cell\s+resolution|spatial\s+proteomic)\b",
        "s3_nimbalkar2025_wrong_platform",
    ),
    (
        r"\b(?:CD163\+?CD206\+?|Treg|regulatory\s+T|macrophage[- ]Treg|macrophage.*cluster|CD8\+?\s*T[- ]?cell\s+proximity|proximity\s+to\s+tumou?r)\b",
        "s3_nimbalkar2025_unlicensed_residual_immune_claim",
    ),
]

S_WANG_NIMBALKAR_BOUNDARY_TERMS = [
    "adjacent",
    "not residual",
    "not direct",
    "does not profile residual",
    "do not profile residual",
    "cannot support",
    "does not support",
    "treatment-naive",
    "treatment-naïve",
    "baseline",
    "early on-treatment",
    "post-treatment",
    "icb response",
    "menopausal",
    "response-context",
    "response context",
]

S4_DENKERT_ALLOWED_BOUNDARY_TERMS = [
    "pretreatment",
    "pre-treatment",
    "pretherapeutic",
    "pre-therapeutic",
    "core biopsy",
    "core biopsies",
    "not residual",
    "not direct",
    "cannot support",
    "does not support",
]

S4_DENKERT_FORBIDDEN_CONTEXT_PATTERNS = [
    (
        r"\b(?:direct\s+residual|residual[- ]specimen|residual\s+specimen|residual\s+TIL|post[- ]?NAC\s+residual|post[- ]?neoadjuvant\s+residual)\b",
        "s4_denkert2018_promoted_to_residual_specimen_evidence",
    ),
    (
        r"\b(?:nine\s+trials|9\s+trials|across\s+nine)\b",
        "s4_denkert2018_wrong_trial_count",
    ),
    (
        r"\b(?:RCB[- ]?adjusted|residual[- ]burden[- ]adjusted|adjust(?:ed|ment)\s+for\s+residual\s+cancer\s+burden)\b",
        "s4_denkert2018_wrong_residual_burden_adjustment",
    ),
]

S4_PINARD_FORBIDDEN_CONTEXT_PATTERNS = [
    (
        r"\b146\s+(?:TNBC\s+)?patients?\b",
        "s4_pinard2020_wrong_146_patient_claim",
    ),
    (
        r"\bHR\s*0\.32\b|\bhazard\s+ratio\s+(?:for\s+recurrence\s+)?(?:was\s+)?0\.32\b",
        "s4_pinard2020_wrong_hr_032_claim",
    ),
    (
        r"\bintermediate\s+RCB\s+(?:stratum|strata|class(?:es)?)\b",
        "s4_pinard2020_unlicensed_intermediate_rcb_interaction",
    ),
    (
        r"\bhigh\s+versus\s+low\s+TIL\b|\bhigh[- ]vs[- ]low\s+TIL\b",
        "s4_pinard2020_unlicensed_high_vs_low_til_claim",
    ),
]

S4_LUEN_ALLOWED_BOUNDARY_TERMS = [
    "residual tnbc",
    "tnbc residual",
    "rd til",
    "rd tils",
    "rcb",
    "rcb class ii",
]

S4_LUEN_FORBIDDEN_CONTEXT_PATTERNS = [
    (
        r"\b(?:3,?771|3771)\s+(?:patients?|samples?)\b",
        "s4_luen2019_wrong_denkert_sample_size",
    ),
    (
        r"\bHER2[- ]positive\b",
        "s4_luen2019_wrong_her2_positive_scope",
    ),
    (
        r"\bpooled\s+analysis\b.{0,80}\b(?:3,?771|3771)\b",
        "s4_luen2019_wrong_pooled_analysis_claim",
    ),
]

S4_LEJEUNE_FORBIDDEN_CONTEXT_PATTERNS = [
    (
        r"\b118\s+(?:residual\s+)?(?:TNBC\s+)?(?:specimens?|patients?|cases?)\b",
        "s4_lejeune2023_wrong_118_sample_size",
    ),
    (
        r"\bstromal\s+TILs?\b.{0,120}\b(?:10%\s+increment|per\s+10%)\b",
        "s4_lejeune2023_wrong_stromal_til_increment_claim",
    ),
    (
        r"\bRCB[- ]?adjusted\b|\badjust(?:ed|ing)\s+for\s+RCB\b",
        "s4_lejeune2023_wrong_rcb_adjusted_claim",
    ),
    (
        r"\bDFS\b|\bdisease[- ]free\s+survival\b|\bHR\s*0\.95\b|\bp\s*=\s*0\.04\b",
        "s4_lejeune2023_wrong_dfs_hr_p_claim",
    ),
]

S4_BLAYE_FORBIDDEN_CONTEXT_PATTERNS = [
    (
        r"\b146\s+(?:residual\s+)?(?:TNBC\s+)?(?:specimens?|samples?|tumou?rs?|cases?)\b",
        "s4_blaye2022_wrong_146_analyzed_claim",
    ),
    (
        r"\b12\s+immune[- ]related\s+genes?\b|\b12[- ]gene\s+signature\b",
        "s4_blaye2022_wrong_main_12_gene_signature",
    ),
    (
        r"\b(?:CD8A|GZMB|PRF1|CXCL9)\b",
        "s4_blaye2022_wrong_main_signature_genes",
    ),
    (
        r"\b91%\s+(?:versus|vs\.?)\s+56%\b|\b5[- ]year\s+distant\s+metastasis[- ]free\s+survival\b",
        "s4_blaye2022_unlicensed_dmfs_values",
    ),
    (
        r"\bindependent\s+of\s+RCB\b|\bRCB[- ]independent\b|\bremained\s+independent\b.{0,40}\bRCB\b",
        "s4_blaye2022_unlicensed_rcb_independence_claim",
    ),
]


@dataclass
class GateDecision:
    status: str
    hard_fail: bool
    failure_class: list[str] = field(default_factory=list)
    rewrite_instruction: str = ""
    score: CandidateScore = field(default_factory=CandidateScore)
    citekeys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scores"] = asdict(self.score)
        data.pop("score", None)
        return data


def _load_kernels(ws_dir: Path) -> dict[str, SectionKernel]:
    rows = read_jsonl(sidecars_dir(ws_dir) / "section-kernels.jsonl")
    kernels: dict[str, SectionKernel] = {}
    for row in rows:
        kernels[row["section_id"]] = SectionKernel(
            section_id=row["section_id"],
            title=row.get("title", row["section_id"]),
            controlling_claim=row.get("controlling_claim", ""),
            evidence_keys=row.get("evidence_keys", []),
            contrast=row.get("contrast", ""),
            forbidden_overclaim=row.get("forbidden_overclaim", ""),
            required_tables=row.get("required_tables", []),
            direct_evidence_keys=row.get("direct_evidence_keys", []),
            adjacent_evidence_keys=row.get("adjacent_evidence_keys", []),
            background_only_keys=row.get("background_only_keys", []),
            required_figures=row.get("required_figures", []),
            failure_test=row.get("failure_test", ""),
        )
    return kernels


def load_reference_boundary(ws_dir: Path) -> tuple[set[str], set[str]]:
    bib_keys = parse_bibtex_keys(read_text(ws_dir / "references.bib"))
    _refmap_keys, blocked_keys, _records = load_reference_policy(ws_dir / "reference-map.json")
    return bib_keys, blocked_keys


def _section_text_removed(text: str, section_id: str) -> str:
    pattern = (
        rf"^###\s+{re.escape(section_id)}\s*[:.].*?"
        rf"(?=^###\s+S\d+[A-Za-z0-9_-]*\s*[:.]|\Z)"
    )
    return re.sub(pattern, "", text, count=1, flags=re.DOTALL | re.MULTILINE)


def _missing_required_after_section_rewrite(text: str, ws_dir: Path, kernel: SectionKernel | None) -> list[str]:
    if not kernel:
        return []
    write_path = ws_dir / "write.md"
    ref_path = ws_dir / "reference-map.json"
    if not write_path.exists() or not ref_path.exists():
        return []
    manuscript = read_text(write_path)
    if "_Draft pending._" in manuscript:
        return []
    data = json.loads(read_text(ref_path))
    records = data.get("references", []) if isinstance(data, dict) else []
    section_relevant: set[str] = set(kernel.evidence_keys)
    required: set[str] = set()
    for record in records:
        citekey = record.get("citekey")
        if not citekey or record.get("citation_policy") != "must_cite":
            continue
        if kernel.section_id in (record.get("sections") or []) or citekey in section_relevant:
            required.add(citekey)
    outside_cites = set(extract_citekeys(_section_text_removed(manuscript, kernel.section_id)))
    candidate_cites = set(extract_citekeys(text))
    table_plan_path = ws_dir / "table-figure-plan.md"
    asset_cites = set()
    if table_plan_path.exists():
        table_plan = read_text(table_plan_path)
        asset_cites = {key for key in required if key in table_plan}
    return sorted(required - outside_cites - candidate_cites - asset_cites)


def evidence_gate(text: str, ws_dir: Path, kernel: SectionKernel | None = None) -> GateDecision:
    citekeys = extract_citekeys(text)
    bib_keys, blocked_keys = load_reference_boundary(ws_dir)
    unknown = sorted(set(citekeys) - bib_keys)
    blocked = sorted(set(citekeys) & blocked_keys)
    failures: list[str] = []
    missing_required = _missing_required_after_section_rewrite(text, ws_dir, kernel)
    if unknown:
        failures.append("unknown_citekey")
    if blocked:
        failures.append("blocked_citekey")
    if missing_required:
        failures.append("missing_must_cite_after_section_rewrite")
    if kernel and citekeys:
        direct = set(kernel.direct_evidence_keys or kernel.evidence_keys)
        adjacent = set(kernel.adjacent_evidence_keys) | set(kernel.background_only_keys)
        if direct and citekeys[0] in adjacent and not any(key in direct for key in citekeys[:2]):
            failures.append("adjacent_evidence_leads")
    if failures:
        return GateDecision(
            status="BLOCKED_BY_EVIDENCE_BOUNDARY",
            hard_fail=True,
            failure_class=failures,
            rewrite_instruction=(
                "Rewrite using only licensed citation keys and direct evidence for the section claim. "
                f"Preserve section-scoped must-cite coverage: {', '.join(missing_required)}."
            ),
            score=CandidateScore(evidence_fidelity=0, hard_fail=True, failure_class=failures),
            citekeys=citekeys,
        )
    return GateDecision(
        status="PASS",
        hard_fail=False,
        score=CandidateScore(evidence_fidelity=5, section_specificity=3, boundary_precision=3),
        citekeys=citekeys,
    )


def claim_license_gate(text: str) -> GateDecision:
    lowered = text.lower()
    failures = [term.strip() for term in FORBIDDEN_LEAPS if term in lowered]
    if failures:
        return GateDecision(
            status="BLOCKED_BY_EVIDENCE_BOUNDARY",
            hard_fail=True,
            failure_class=["l6_forbidden_leap"],
            rewrite_instruction="Remove L6 clinical or causal leaps and recast the claim at the licensed evidence level.",
            score=CandidateScore(boundary_precision=0, hard_fail=True, failure_class=["l6_forbidden_leap"]),
        )
    status = "PASS"
    score = CandidateScore(boundary_precision=4)
    return GateDecision(status=status, hard_fail=False, score=score)


def clinical_trial_boundary_gate(text: str, kernel: SectionKernel | None = None) -> GateDecision:
    if not kernel or kernel.section_id != "S7":
        return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(boundary_precision=4))
    lowered = text.lower()
    failures = []
    boundary_warning_terms = (
        "do not cite",
        "do not claim",
        "do not use",
        "cannot support",
        "not support",
        "not citable",
        "non-citable",
        "no os direction",
        "no efs",
        "no result",
        "no results",
        "not retained as citable",
        "abstract-only",
    )
    table_boundary_terms = (
        "currentness gap",
        "acquisition/currentness gap",
        "pcr-era retained paper endpoint context only",
        "registry endpoint context only",
    )
    for pattern, failure_id in S7_FORBIDDEN_CLINICAL_CLAIMS:
        for line in text.splitlines():
            if not re.search(pattern, line, flags=re.IGNORECASE):
                continue
            line_lower = line.lower()
            if failure_id == "keynote522_promoted_to_standard_claim" and (
                "no keynote-522" in line_lower
                or "without converting keynote-522" in line_lower
                or "must not support" in line_lower
                or "do not write" in line_lower
            ):
                continue
            if failure_id != "keynote522_promoted_to_standard_claim" and any(
                term in line_lower for term in boundary_warning_terms
            ):
                continue
            if line.lstrip().startswith("|") and any(term in line_lower for term in table_boundary_terms):
                continue
            if failure_id == "ea1131_registry_promoted_to_outcome" and "mayer2021randomized" in lowered:
                continue
            failures.append(failure_id)
    for pattern, failure_id in S7_CURRENTNESS_STATUS_PATTERNS:
        for line in text.splitlines():
            if line.lstrip().startswith("|"):
                continue
            if re.search(pattern, line, flags=re.IGNORECASE):
                failures.append(failure_id)
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        if line.count(S7_REGISTRY_DUPLICATE_BOUNDARY_TEXT) > 1:
            failures.append("s7_registry_table_boundary_duplicated")
    yau_misuse = (
        r"(?:\bYau2022Residual\b.{0,320}\b(?:I-SPY2|ctDNA|de-escalat(?:e|ion)|negative predictive value|molecular residual disease|MRD)\b)"
        r"|(?:\b(?:I-SPY2|ctDNA|de-escalat(?:e|ion)|negative predictive value|molecular residual disease|MRD)\b.{0,320}\bYau2022Residual\b)"
    )
    if re.search(yau_misuse, text, flags=re.IGNORECASE | re.DOTALL):
        failures.append("s7_yau_rcb_cited_for_ctdna_or_deescalation")
    missing_maturity = [
        label for label, markers in S7_EVIDENCE_MATURITY_MARKERS if not any(marker in lowered for marker in markers)
    ]
    if missing_maturity:
        failures.append("s7_missing_evidence_maturity_narrative")
    if failures:
        return GateDecision(
            status="BLOCKED_BY_EVIDENCE_BOUNDARY",
            hard_fail=True,
            failure_class=list(dict.fromkeys(failures)),
            rewrite_instruction=(
                "Rewrite S7 so S1418/EA1131-style records remain registry/design/status context, "
                "Schmid2020Pembrolizumab supports only KEYNOTE-522 pCR-era evidence, and prose ranks "
                "retained standards, retained negative evidence, biomarker-risk bridges, registry-only "
                "hypotheses, and acquisition/currentness gaps. Do not write FDA approval, publication, reported-status, "
                "or exact-date claims from DESTINY-Breast05/T-DXd currentness records in prose, and keep registry-family "
                f"table rows to one concise boundary cell. Missing maturity markers: {', '.join(missing_maturity)}."
            ),
            score=CandidateScore(boundary_precision=0, hard_fail=True, failure_class=failures),
        )
    return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(boundary_precision=4))


def stromal_boundary_gate(text: str, kernel: SectionKernel | None = None) -> GateDecision:
    if not kernel or kernel.section_id != "S5":
        return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(boundary_precision=4))
    failures = []
    for pattern, failure_id in S5_FORBIDDEN_CAF_CLAIMS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            matched_text = match.group(0).lower()
            if any(term in matched_text for term in S5_CAF_BOUNDARY_TERMS):
                continue
            failures.append(failure_id)
    if failures:
        return GateDecision(
            status="BLOCKED_BY_EVIDENCE_BOUNDARY",
            hard_fail=True,
            failure_class=list(dict.fromkeys(failures)),
            rewrite_instruction=(
                "Rewrite S5 so Cords2023Cancerassociated and Croizer2024Deciphering are adjacent CAF "
                "atlas/taxonomy/plasticity vocabulary only, with direct post-neoadjuvant residual CAF evidence "
                "described as sparse or not established by those sources."
            ),
            score=CandidateScore(boundary_precision=0, hard_fail=True, failure_class=failures),
        )
    return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(boundary_precision=4))


def spatial_boundary_gate(text: str, kernel: SectionKernel | None = None) -> GateDecision:
    if not kernel or kernel.section_id not in {"S3", "S4"}:
        return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(boundary_precision=4))
    failures = []
    segments = re.split(r"(?<=[.!?])\s+|\n+", text)
    paragraphs = re.split(r"\n\s*\n", text)
    if kernel.section_id == "S3":
        for segment in segments:
            if "Park2025Spatial" not in segment:
                continue
            lowered = segment.lower()
            has_boundary = any(term in lowered for term in S3_PARK2025_BOUNDARY_TERMS)
            has_negation = any(term in lowered for term in S3_PARK2025_NEGATING_TERMS)
            for pattern, failure_id in S3_PARK2025_FORBIDDEN_SEGMENT_PATTERNS:
                if not re.search(pattern, segment, flags=re.IGNORECASE | re.DOTALL):
                    continue
                if has_boundary and failure_id in {
                    "s3_park2025_promoted_to_residual_tissue",
                    "s3_park2025_promoted_to_direct_residual_spatial",
                    "s3_park2025_promoted_to_residual_profiling",
                }:
                    continue
                if has_negation:
                    continue
                failures.append(failure_id)
        for segment in segments:
            if "FernandezMartinez2025Prognostic" not in segment:
                continue
            lowered = segment.lower()
            has_negation = any(term in lowered for term in S3_PARK2025_NEGATING_TERMS)
            for pattern, failure_id in S3_FERNANDEZ2025_FORBIDDEN_SEGMENT_PATTERNS:
                if not re.search(pattern, segment, flags=re.IGNORECASE | re.DOTALL):
                    continue
                if has_negation:
                    continue
                failures.append(failure_id)
    if kernel.section_id == "S4":
        for paragraph in paragraphs:
            if "Denkert2018Tumourinfiltrating" not in paragraph:
                continue
            lowered = paragraph.lower()
            has_boundary = any(term in lowered for term in S4_DENKERT_ALLOWED_BOUNDARY_TERMS)
            for pattern, failure_id in S4_DENKERT_FORBIDDEN_CONTEXT_PATTERNS:
                if not re.search(pattern, paragraph, flags=re.IGNORECASE | re.DOTALL):
                    continue
                if has_boundary:
                    continue
                failures.append(failure_id)
        for paragraph in paragraphs:
            if "Pinard2020Residual" not in paragraph:
                continue
            lowered = paragraph.lower()
            has_negation = any(term in lowered for term in S3_PARK2025_NEGATING_TERMS)
            for pattern, failure_id in S4_PINARD_FORBIDDEN_CONTEXT_PATTERNS:
                if not re.search(pattern, paragraph, flags=re.IGNORECASE | re.DOTALL):
                    continue
                if has_negation:
                    continue
                failures.append(failure_id)
        for paragraph in paragraphs:
            if "Luen2019Prognostic" not in paragraph:
                continue
            for pattern, failure_id in S4_LUEN_FORBIDDEN_CONTEXT_PATTERNS:
                if not re.search(pattern, paragraph, flags=re.IGNORECASE | re.DOTALL):
                    continue
                failures.append(failure_id)
        for paragraph in paragraphs:
            if "Lejeune2023Prognostic" not in paragraph:
                continue
            for pattern, failure_id in S4_LEJEUNE_FORBIDDEN_CONTEXT_PATTERNS:
                if not re.search(pattern, paragraph, flags=re.IGNORECASE | re.DOTALL):
                    continue
                failures.append(failure_id)
        for paragraph in paragraphs:
            if "Blaye2022Immunological" not in paragraph:
                continue
            for pattern, failure_id in S4_BLAYE_FORBIDDEN_CONTEXT_PATTERNS:
                if not re.search(pattern, paragraph, flags=re.IGNORECASE | re.DOTALL):
                    continue
                failures.append(failure_id)
    for segment in segments:
        if "Wang2023Spatial" not in segment:
            continue
        lowered = segment.lower()
        has_boundary = any(term in lowered for term in S_WANG_NIMBALKAR_BOUNDARY_TERMS)
        has_negation = any(term in lowered for term in S3_PARK2025_NEGATING_TERMS)
        for pattern, failure_id in S3_WANG2023_FORBIDDEN_SEGMENT_PATTERNS:
            if not re.search(pattern, segment, flags=re.IGNORECASE | re.DOTALL):
                continue
            if has_boundary or has_negation:
                continue
            failures.append(failure_id)
    for segment in segments:
        if "Nimbalkar2025Spatial" not in segment:
            continue
        lowered = segment.lower()
        has_boundary = any(term in lowered for term in S_WANG_NIMBALKAR_BOUNDARY_TERMS)
        has_negation = any(term in lowered for term in S3_PARK2025_NEGATING_TERMS)
        for pattern, failure_id in S3_NIMBALKAR2025_FORBIDDEN_SEGMENT_PATTERNS:
            if not re.search(pattern, segment, flags=re.IGNORECASE | re.DOTALL):
                continue
            if has_boundary or has_negation:
                continue
            failures.append(failure_id)
    if failures:
        return GateDecision(
            status="BLOCKED_BY_EVIDENCE_BOUNDARY",
            hard_fail=True,
            failure_class=list(dict.fromkeys(failures)),
            rewrite_instruction=(
                "Rewrite S3 so Park2025Spatial is adjacent pretreatment-biopsy TNBC pCR-versus-non-pCR "
                "immune-spatial response-context evidence only, and FernandezMartinez2025Prognostic is "
                "HER2-positive residual disease gene-expression/immune-signature prognostic evidence only. "
                "Do not use Park for residual tumor profiling, recurrence-free survival, RCB-independent "
                "prognostic value, or direct residual-spatial claims. Do not use Fernandez-Martinez for "
                "spatial architecture, proteomic profiling, GeoMx/DSP, single-cell, compartment-level, "
                "or direct residual-spatial evidence. Do not use Wang2023Spatial as residual chemo-pembrolizumab "
                "DSP/multiplex-IF evidence or for unlicensed residual immune-exclusion claims. Do not use "
                "Nimbalkar2025Spatial as residual, paired, imaging-mass-cytometry, macrophage/Treg, or CD8-proximity "
                "evidence. In S4, keep Denkert2018Tumourinfiltrating as pretreatment/pretherapeutic core-biopsy "
                "neoadjuvant TIL context, not direct residual-specimen or residual-burden-adjusted evidence; keep "
                "Pinard2020Residual to the retained 186 TNBC / 109 residual disease RCB index plus CD4+ TIL DRFI "
                "license and avoid unsupported 146-patient, HR 0.32, or intermediate-RCB interaction claims. Keep "
                "Luen2019Prognostic as residual TNBC RD-TIL/RCB evidence only; keep Lejeune2023Prognostic as "
                "96-case residual TNBC TME marker evidence, not RCB-adjusted stromal-TIL DFS evidence; keep "
                "Blaye2022Immunological as 115-sample residual TNBC NanoString eight-gene signature evidence, with "
                "the 12-chemokine TLS score and extended 63-gene signature separated from the main signature."
            ),
            score=CandidateScore(boundary_precision=0, hard_fail=True, failure_class=failures),
        )
    return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(boundary_precision=4))


def round11_boundary_gate(text: str, kernel: SectionKernel | None = None) -> GateDecision:
    if not kernel or kernel.section_id not in {"S5", "S6"}:
        return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(boundary_precision=4))
    patterns = S5_FORBIDDEN_ROUND11_CLAIMS if kernel.section_id == "S5" else S6_FORBIDDEN_ROUND11_CLAIMS
    failures = []
    for pattern, failure_id in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            failures.append(failure_id)
    if failures:
        return GateDecision(
            status="BLOCKED_BY_EVIDENCE_BOUNDARY",
            hard_fail=True,
            failure_class=list(dict.fromkeys(failures)),
            rewrite_instruction=(
                "Rewrite the section from the evidence ledger and keep each named source inside the round-11 "
                "critic boundary for sample state, subtype, assay, endpoint, and comparison."
            ),
            score=CandidateScore(boundary_precision=0, hard_fail=True, failure_class=failures),
        )
    return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(boundary_precision=4))


def round12_boundary_gate(text: str, kernel: SectionKernel | None = None) -> GateDecision:
    if not kernel or kernel.section_id not in {"S5", "S6", "S7"}:
        return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(boundary_precision=4))
    failures = []
    if kernel.section_id == "S5":
        for pattern, failure_id in S5_FORBIDDEN_ROUND12_CLAIMS:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            matched_text = match.group(0).lower()
            if failure_id == "s5_jiang_primary_tnbc_promoted_to_residual_tnbc" and any(
                boundary in matched_text
                for boundary in (
                    "not residual",
                    "not a residual",
                    "not post",
                    "primary tnbc",
                    "primary triple-negative",
                )
            ):
                continue
            failures.append(failure_id)
    elif kernel.section_id == "S6":
        for pattern, failure_id in S6_FORBIDDEN_ROUND12_CLAIMS:
            if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
                failures.append(failure_id)
    elif kernel.section_id == "S7":
        if re.search(
            r"\bretained\s+initial\s+KATHERINE\s+T[- ]DM1\s+standard\b",
            text,
            flags=re.IGNORECASE,
        ):
            failures.append("s7_katherine_retained_initial_standard_wording")
        if re.search(r"\bestablished\s+standards\b", text, flags=re.IGNORECASE):
            failures.append("s7_established_standards_currentness_drift")
        for pattern in S7_FORBIDDEN_CURRENT_STANDARD_PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                prefix = text[max(0, match.start() - 60) : match.start()].lower()
                if any(term in prefix for term in ("retained", "locally retained", "pre-destiny", "local-corpus")):
                    continue
                if "no " in prefix or "not " in prefix or "do not " in prefix:
                    continue
                failures.append("s7_unqualified_current_standard_wording")
    if failures:
        return GateDecision(
            status="BLOCKED_BY_EVIDENCE_BOUNDARY",
            hard_fail=True,
            failure_class=list(dict.fromkeys(failures)),
            rewrite_instruction=(
                "Rewrite from the round-12 critic boundary: keep Jiang as primary-TNBC context only; keep Im "
                "inside MIRINAE residual TNBC evidence; keep McDonald inside TARDIS/NAT pathCR/residual-disease "
                "evidence; keep Dong as bounded stage II/III NAC multi-omic/ctDNA evidence; remove unsupported "
                "ctDNA sensitivity arithmetic; and use retained/pre-DESTINY-Breast05 wording for S7. In S7, "
                "write retained initial KATHERINE T-DM1 evidence/backbone, not standard, and replace established "
                "standards with retained treatment-positive evidence or locally retained escalation backbone."
            ),
            score=CandidateScore(boundary_precision=0, hard_fail=True, failure_class=failures),
        )
    return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(boundary_precision=4))


def anti_ai_gate(text: str) -> GateDecision:
    prose_text = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("|")
    )
    lowered = prose_text.lower()
    failures: list[str] = []
    banned_hits = 0
    for pattern in BANNED_PATTERNS:
        banned_hits += len(re.findall(pattern, lowered, flags=re.IGNORECASE | re.DOTALL))
    if banned_hits >= 2:
        failures.append("banned_pattern")
    if any(ending in lowered for ending in GENERIC_ENDINGS):
        failures.append("generic_validation_as_ending")
    framework_hits = sum(1 for noun in FRAMEWORK_NOUNS if noun.lower() in lowered)
    if framework_hits >= 3:
        failures.append("framework_noun_stack")
    if failures:
        return GateDecision(
            status="REWRITE_REQUIRED_STYLE",
            hard_fail=True,
            failure_class=list(dict.fromkeys(failures)),
            rewrite_instruction="Replace generic framework prose with section-specific adjudication grounded in evidence.",
            score=CandidateScore(anti_ai_penalty=5, hard_fail=True, failure_class=failures),
        )
    return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(anti_ai_penalty=0, human_move_score=3))


def cowardice_gate(text: str, kernel: SectionKernel | None = None) -> GateDecision:
    lowered = text.lower()
    failures: list[str] = []
    if not any(term in lowered for term in ADJUDICATIVE_TERMS):
        failures.append("no_adjudicative_claim")
    if kernel and kernel.failure_test:
        failure_test = kernel.failure_test.lower().strip()
        if failure_test in GENERIC_FAILURE_TESTS:
            has_failure_test = any(term in lowered for term in FAILURE_TEST_TERMS)
        else:
            has_failure_test = failure_test in lowered
        if not has_failure_test:
            failures.append("no_decisive_failure_test")
    if any(ending in lowered for ending in GENERIC_ENDINGS):
        failures.append("generic_validation_as_ending")
    if failures:
        return GateDecision(
            status="REWRITE_REQUIRED_COWARDICE",
            hard_fail=True,
            failure_class=failures,
            rewrite_instruction="Make the direct evidence lead and state what interpretation it defeats or constrains.",
            score=CandidateScore(claim_courage=0, human_move_score=0, hard_fail=True, failure_class=failures),
        )
    return GateDecision(status="PASS", hard_fail=False, score=CandidateScore(claim_courage=4, human_move_score=4))


def evaluate_candidate(text: str, ws_dir: Path, kernel: SectionKernel | None = None) -> GateDecision:
    decisions = [
        evidence_gate(text, ws_dir, kernel),
        claim_license_gate(text),
        clinical_trial_boundary_gate(text, kernel),
        stromal_boundary_gate(text, kernel),
        spatial_boundary_gate(text, kernel),
        round11_boundary_gate(text, kernel),
        round12_boundary_gate(text, kernel),
        anti_ai_gate(text),
        cowardice_gate(text, kernel),
    ]
    failures: list[str] = []
    for decision in decisions:
        failures.extend(decision.failure_class)
        if decision.hard_fail:
            decision.failure_class = list(dict.fromkeys(failures))
            decision.score.failure_class = decision.failure_class
            decision.score.hard_fail = True
            return decision
    citekeys = decisions[0].citekeys
    score = CandidateScore(
        evidence_fidelity=5,
        section_specificity=4,
        claim_courage=4,
        boundary_precision=4,
        anti_ai_penalty=0,
        human_move_score=4,
        hard_fail=False,
        failure_class=[],
    )
    return GateDecision(status="PASS", hard_fail=False, score=score, citekeys=citekeys)


def evaluate_section_candidates(ws_dir: Path, section_id: str, candidate_paths: list[Path]) -> list[dict[str, Any]]:
    kernel = _load_kernels(ws_dir).get(section_id)
    rows: list[dict[str, Any]] = []
    for path in candidate_paths:
        decision = evaluate_candidate(read_text(path), ws_dir, kernel)
        row = {"section_id": section_id, "candidate": path.name, **decision.to_dict()}
        rows.append(row)
    score_path = sidecars_dir(ws_dir) / "candidate-scores.jsonl"
    existing = [r for r in read_jsonl(score_path) if r.get("section_id") != section_id]
    write_jsonl(score_path, existing + rows)
    _write_reports(ws_dir, rows)
    _write_claim_license_ledger(ws_dir, rows)
    return rows


def _write_reports(ws_dir: Path, rows: list[dict[str, Any]]) -> None:
    anti = [r for r in rows if "banned_pattern" in r.get("failure_class", []) or r.get("status") == "REWRITE_REQUIRED_STYLE"]
    human = [r for r in rows if r.get("status") == "REWRITE_REQUIRED_COWARDICE"]
    write_text(
        sidecars_dir(ws_dir) / "anti-ai-report.md",
        "# Anti-AI Report\n\n" + "\n".join(f"- {r['section_id']} {r['candidate']}: {r['status']}" for r in anti) + "\n",
    )
    write_text(
        sidecars_dir(ws_dir) / "human-move-report.md",
        "# Human-Move Report\n\n" + "\n".join(f"- {r['section_id']} {r['candidate']}: {r['status']}" for r in human) + "\n",
    )


def _write_claim_license_ledger(ws_dir: Path, rows: list[dict[str, Any]]) -> None:
    path = sidecars_dir(ws_dir) / "claim-license-ledger.tsv"
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    if not existing:
        existing = "section_id\tcandidate\tlicense_level\tstatus\tfailure_class\n"
    lines = []
    for row in rows:
        failures = row.get("failure_class", [])
        level = "L6" if "l6_forbidden_leap" in failures else "L2"
        lines.append(
            f"{row['section_id']}\t{row['candidate']}\t{level}\t{row['status']}\t{','.join(failures)}"
        )
    write_text(path, existing.rstrip() + "\n" + "\n".join(lines) + "\n")
