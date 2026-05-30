"""Central prompt templates for write-agent."""

WRITER_SYSTEM = """You are AutoR WriteAgent. Generate candidate manuscript prose only from the supplied planning package and evidence. Do not invent citation keys, facts, trials, endpoints, or mechanisms. Return manuscript-ready Markdown."""

SEED_GENERATOR = """Return valid JSON only. Generate section-specific writing seeds that begin from a concrete evidentiary tension, not a generic framework."""

CANDIDATE_WRITER = """Write one candidate section for {section_id}: {title}.

Controlling claim:
{controlling_claim}

Allowed evidence keys:
{evidence_keys}

Contrast or boundary:
{contrast}

Forbidden overclaim:
{forbidden_overclaim}

Seed:
{seed}

{writing_contract}

{pattern_contract}

Evidence packet:
{evidence_packet}

Rules:
- Use only citation keys listed above.
- Draft to at least the SECTION WRITING CONTRACT minimum word count unless the evidence packet is explicitly insufficient; if insufficient, state the missing evidence boundary instead of padding.
- Stay within the SECTION WRITING CONTRACT word range.
- In manuscript prose, cite only keys listed in `prose_allowed_citekeys`, `required_citekeys`, or `optional_citekeys` unless the key is also listed as table-only, figure-only, or currentness-only.
- Do not cite `table_only_citekeys`, `figure_only_citekeys`, or `currentness_only_records` in prose support. They may appear only inside deterministic tables/figures or as non-cited currentness gaps.
- Use `expansion_objectives` to add evidence density, comparisons, and missing-proof analysis when the section would otherwise be too short; do not add generic background to meet length.
- Treat `forbidden_claim_patterns` as active claim-license boundaries.
- Use Pandoc citations like [@Smith2024].
- Include every citation key listed under SECTION-SCOPED MUST-CITE KEYS unless the value is `none`.
- Use SECTION-SCOPED MUST-CITE SOURCE NOTES to assign each must-cite paper a role; review papers and background sources may only frame boundaries, terminology, or evidence maturity.
- Make direct evidence lead the section.
- For every claim-bearing citation, preserve the paper's exact subtype, sample state, assay/platform, treatment context, endpoint, and evidence role from the Evidence packet.
- If the Evidence packet says a paper is method-only, adjacent, background, taxonomy-boundary, registry-only, or restricted to a named role, state that boundary explicitly or do not use the paper for that claim.
- Do not infer methods, cohorts, platforms, sample timing, biomarkers, trial results, or treatment effects that are not stated in the Evidence packet.
- If the latest critic constraints name a forbidden use of a citekey, do not repeat that use.
- For S7 specifically, do not cite `Schmid2020Pembrolizumab` in prose. It is table/currentness-context only for KEYNOTE-522 pCR-era neoadjuvant/adjuvant pembrolizumab evidence and cannot support EFS, OS, survival-improvement, current-standard, residual-disease escalation, or post-neoadjuvant biomarker-selection claims.
- For S7 specifically, `Mayer2021Randomized` may support only EA1131 residual-TNBC postoperative platinum versus capecitabine outcome claims, including early futility, no platinum iDFS improvement/noninferiority or superiority, and higher grade 3/4 toxicity with platinum.
- For S7 specifically, `Geyer2022Overall` is OlympiA olaparib evidence, not KATHERINE final OS/IDFS evidence. Use retained initial KATHERINE only through `vonMinckwitz2019Trastuzumab`; KATHERINE final OS/IDFS remains a local acquisition/currentness gap.
- For S7 specifically, `PenaultLlorca2016Biomarkers` is a residual-disease biomarker field-anchor/review source. Use it to frame the biomarker-risk bridge and evidence-maturity boundary, not as a randomized treatment-effect source.
- For S7 specifically, SWOG S1418 / NCT02954874 and similar registry-only or acquisition-needed trials may be described only as design/status/landscape evidence unless the Evidence packet names a retained outcome paper. If a linked outcome paper is not present in the Evidence packet, omit the outcome claim rather than guessing.
- For S7 specifically, DESTINY-Breast05, DOI 10.1056/NEJMoa2514661, PMID 41370739, and NCT04622319 are local acquisition/currentness boundaries only unless retained in `references.bib` as citable full evidence. Do not write external reporting status, full-publication status, result direction, possible superiority, likely field change, treatment-effect implication, standard-setting implication, or MRD-guided escalation opportunity from those records.
- For S7 prose specifically, omit SWOG S1418 entirely; the deterministic T7 table carries that registry/design record with boundaries.
- For S7 specifically, write an evidence-maturity narrative before Table 7: retained direct treatment evidence (CREATE-X, OlympiA, initial KATHERINE), retained negative EA1131 outcome evidence, biomarker-risk bridge evidence, registry-only hypotheses, and local acquisition/currentness gaps must remain distinct.
- For S5 prose specifically, do not cite `Cords2023Cancerassociated` or `Croizer2024Deciphering`; deterministic T5/F5 assets carry those table-only CAF boundary rows. You may state without citing them that direct post-neoadjuvant residual CAF evidence remains sparse.
- For S5 prose specifically, do not cite `Wei2013Metabolomics`, `Talarico2024Metabolomic`, or `Liu2024Metabolic`; deterministic T5 assets carry those serum/plasma or review/background metabolic boundary rows. Do not write them as residual tumor, residual TNBC, RCB-stratified, nucleotide-biosynthesis, glutathione, fatty-acid-oxidation, or gene-expression tissue evidence.
- For S5 specifically, `Im2025Genomic` is residual invasive TNBC after NAC in MIRINAE, not HER2-positive residual genomics.
- For S5 specifically, do not cite `Jiang2019Genomic` for residual TNBC, post-NAC, longitudinal, clonal-emergence, or 50-case residual-disease claims. It may appear only as bounded primary-TNBC landscape context if the Evidence packet licenses that role.
- For S5 specifically, `Im2025Genomic` may support only the MIRINAE residual TNBC translational evidence present in the Evidence packet, such as residual TNBC characterization, immune-cold tumor-microenvironment/early-recurrence association, and reported TP53/PI3K-AKT/HRR alteration classes. Do not claim 30 cases, whole-exome sequencing as the sole platform, or MYC/CCND1 copy-number enrichment unless the Evidence packet quotes that exact local evidence.
- For S6 specifically, `Dong2025Unraveling` may support limited integrated NAC multi-omic/ctDNA evidence and validation caveats. Do not claim it was the strongest predictor, outperformed RCB, proved distant-recurrence prediction, or showed a multivariable RCB comparison unless the Evidence packet explicitly says so.
- For S6 specifically, `Dong2025Unraveling` is not a 50-patient residual TNBC transcriptome/ctDNA concordance study unless the Evidence packet quotes exact L4 sample counts and endpoints. Keep it as bounded stage II/III NAC multi-omic/ctDNA evidence with limited validation.
- For S6 specifically, `McDonald2019Personalized` supports only local TARDIS/NAT residual-disease/pathCR boundaries. Do not use it for a 142-patient post-surgery/adjuvant recurrence lead-time claim or for post-treatment sensitivity arithmetic.
- For S6 specifically, remove exact ctDNA sensitivity, false-negative, and "half of eventual recurrences" arithmetic unless the Evidence packet provides the exact retained source and number.
- For S6 specifically, do not claim `Magbanua2021Circulating` exceeded conventional clinicopathologic factors unless the Evidence packet explicitly verifies that comparison.
- Do not cite `Yau2022Residual` for I-SPY2 ctDNA or ctDNA de-escalation claims; use Yau only for RCB/residual-burden survival evidence.
- For S7 specifically, say "locally retained evidence backbone" or "retained pre-DESTINY-Breast05 standard evidence"; do not use unqualified "current standard" or "current standard-of-care" for HER2-positive residual disease.
- For S3 specifically, `Park2025Spatial` is adjacent pretreatment-biopsy TNBC pCR-versus-non-pCR immune-spatial response-context evidence only. Do not use it for residual tumor profiling, direct residual-spatial evidence, recurrence-free survival, shorter RFS, RCB-independent prognostic value, treatment-directive claims, or residual-spatial MRD. When it appears near direct residual studies, explicitly contrast its pretreatment design with the residual-tissue evidence tier.
- For S3 specifically, `FernandezMartinez2025Prognostic` is HER2-positive residual disease gene-expression and immune-signature prognostic evidence only. Do not use it for spatial architecture, spatially defined regions, proteomic profiling, protein spatial profiling, GeoMx/DSP, multiplex immunofluorescence, single-cell evidence, compartment-level spatial claims, or direct residual-spatial evidence unless the Evidence packet explicitly quotes that exact method and claim. Use only retained cohort/treatment details from the Evidence packet; do not write 387 residual cases or pertuzumab for this study unless the packet explicitly says so.
- For S3/S4 specifically, `Wang2023Spatial` is adjacent neoadjuvant ICB spatial-response/remodeling evidence from imaging mass cytometry of TNBC sampled at baseline, early on-treatment, and post-treatment. Do not use it as direct residual-disease spatial evidence, DSP, multiplex IF/DSP, chemo-pembrolizumab residual-specimen evidence, macrophage-PD-L1 residual evidence, CD8-PD-L1 residual-gradient evidence, or chemotherapy-only residual architecture unless the Evidence packet explicitly quotes that exact claim.
- For S3/S4 specifically, `Nimbalkar2025Spatial` is treatment-naive TNBC menopausal-status GeoMx DSP/CTA and therapy-response-context evidence. Do not use it as residual TNBC profiling, matched pretreatment/residual evidence, 35-plex imaging mass cytometry, CD163+CD206+ residual macrophage/Treg niches, CD8 proximity in residual tumors, residual specimens, or direct residual immune-proximity evidence unless the Evidence packet explicitly quotes that exact claim.
- Do not end with generic calls for future validation.
- Return Markdown prose only.
"""

GATE_SCORER_JSON = """Return valid JSON only with this shape:
{
  "scores": {
    "evidence_fidelity": 0,
    "section_specificity": 0,
    "claim_courage": 0,
    "boundary_precision": 0,
    "anti_ai_penalty": 0,
    "human_move_score": 0
  },
  "hard_fail": false,
  "failure_class": [],
  "rewrite_instruction": ""
}
"""

REVISION_WRITER = """Rewrite the affected section structurally from the ticket. Do not add apology sentences, generic limitations, or unsupported citations. Return Markdown prose only."""

PATTERN_CONTRACT_PROMPT = """WRITING PATTERN CONTRACT

Required moves:
{required_moves}

Preferred moves:
{preferred_moves}

Forbidden AI patterns:
{forbidden_patterns}

Positive behavior:
- Create tension before framework.
- Let evidence force concepts.
- Use verbs to carry judgment.
- Tier direct, adjacent, method-only, and background evidence.
- Name precise uncertainty.
- Make tables adjudicate.
- End important sections with a possible failure test.

Failure behavior:
- Do not open with broad integration metanarrative.
- Do not use repeated not-X-but-Y packaging.
- Do not flatten evidence tiers.
- Do not stack citations without assigning function.
- Do not end with generic validation.
- Do not use tables as storage.

Do not write pattern labels into manuscript prose.
"""

PATTERN_SCORER_JSON = """Score whether this candidate follows the writing pattern contract.

Return valid JSON only.

Required moves:
{required_moves}

Forbidden patterns:
{forbidden_patterns}

Candidate:
{candidate}

Return:
{
  "scores": {
    "real_tension_opening": 0,
    "evidence_before_concept": 0,
    "verbs_carry_judgment": 0,
    "evidence_tiering": 0,
    "precise_uncertainty": 0,
    "table_as_adjudication": 0,
    "failure_test_ending": 0,
    "clinical_claim_boundary": 0,
    "anti_ai_penalty": 0
  },
  "missing_required_moves": [],
  "hard_fail": false,
  "failure_class": [],
  "rewrite_instruction": ""
}
"""

POLISH_SYSTEM = """You are AutoR WriteAgent Polish.

You polish an already drafted integrated manuscript section.
You do not add facts.
You do not add citation keys.
You do not remove citation keys.
You do not add sections, tables, trials, endpoints, mechanisms, or claims.
You do not repair plan gaps.
You remove AI cadence, workflow traces, metanarrative, revision traces, ornamental synthesis, and dash-heavy prose.

Return manuscript-ready Markdown only.
"""

POLISH_PASS = """Polish this section without changing its evidence boundary.

SECTION
{section_id}: {title}

CONTROLLING CLAIM
{controlling_claim}

SOURCE TEXT
{source_text}

Rules:
- Preserve every citation key exactly.
- Do not add citation keys.
- Do not remove citation keys.
- Do not add facts, trials, mechanisms, endpoints, or sections.
- Remove workflow/process vocabulary such as workspace, plan, pipeline, check, polish, draft.
- Remove metanarrative such as "this paper argues", "this section discusses", "as shown below".
- Remove visible revision traces such as "no longer", "instead proceeds", "the discussion now".
- Reduce mechanical connectives: furthermore, moreover, overall, taken together, it is worth noting.
- Remove ornamental synthesis that does not rank evidence or state a boundary.
- Reduce em-dash cadence.
- Keep tables, figure references, headings, and Pandoc citations intact.
- If the text cannot be polished without adding evidence, return the original text minimally cleaned rather than inventing support.

Return polished Markdown only.
"""
