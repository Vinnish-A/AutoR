---
name: orchestrator
description: High-level orchestrator for iterative research planning and hypothesis evolution. Evaluates workspace completeness, triggers targeted literature acquisition, refines review plans into section-level judgment kernels, and mandates independent subagent verification before concluding. Strictly stops before writing.
---

# Orchestrator: Iterative Research Planning & Hypothesis Evolution

This skill acts as the highest-level director for literature review preparation. Instead of just generating an outline once, the orchestrator implements a **closed-loop hypothesis evolution workflow**: it diagnoses the current workspace, finds evidence gaps, actively fetches missing literature (via the Records-backed AutoDownload service), and continually revises the plan until the evidence is saturated and the hypothesis is robust.

**CRITICAL CONSTRAINT: DO NOT PROCEED TO WRITING.** This skill is explicitly scoped to stop at the `plan` stage. You must **NEVER** invoke `write`, `paper-writing`, or any drafting skills. Your final output is a completely verified, evidence-saturated planning blueprint.

## Execution Rules & Philosophy

1.  **Strict Blocking on Literature Ingestion**: Downloading and processing PDFs (especially via MinerU) is extremely slow. **You must disable all fallbacks.** Do not mock data, do not attempt to proceed with partial data, and do not fall back to abstract-only reviews if full-text ingestion is underway. You must wait for the ingestion pipeline to complete fully.
2.  **Iterative Hypothesis Evolution**: A research plan is not static. As new papers are acquired, the original hypothesis must be re-evaluated, challenged, and refined based on the newly ingested evidence.
3.  **Independent Subagent Verification**: You cannot self-certify that the planning is complete. You must launch an independent subagent to review the final deliverables against the user's original objective. You may only exit this skill when the subagent officially approves the plan.
4.  **The Global Library Is Reference-Only**: The local knowledge base / total library is useful for orientation, terminology, and quick cross-checking, but it must never be treated as proof that the literature is complete.
5.  **External Metadata and Full-Text Acquisition Are the Reliable Basis**: When deciding whether coverage is sufficient, rely on Records-service external database retrieval, the returned field metadata, and the downstream download + processing pipeline. Do not decide "the literature is complete" merely because the local library search looks dense.
6.  **Full-Text Fallback for Missing Conclusions**: If a key paper lacks a usable L3 conclusion, or if the paper is not yet present in the local library, obtain the full text through the acquisition pipeline. If the structured conclusion still cannot be extracted, expose the full text to a dedicated reading subagent and require it to output what the paper is about and what conclusions it supports.
7.  **Full-Review Coverage Comes Before Quality Pruning**: When the user explicitly asks for a `full review`, `large review`, `comprehensive review`, or otherwise emphasizes citation breadth, first build an external-database-backed **universe corpus** of all directly in-scope papers. Do not let early filters such as “low impact”, “non-essential”, or “not core enough” shrink the field before the coverage map exists.
8.  **Use Layered Corpora Instead of One Early Retained Set**: In full-review mode, maintain at least three layers:
	    - `universe corpus`: all directly in-scope papers after deduplication, retraction removal, and off-scope removal
	    - `working corpus`: the papers actually processed into autor and mapped to sections
	    - `core analytical corpus`: the papers that carry the main mechanistic, translational, or clinical argument
	Only the third layer should be strongly selective. The first layer should be broad.
9.  **Prefer Landscape MCPs for Scope Calibration When Available**: Before or during external retrieval, use literature-landscape MCPs if they are available in the current environment. Prefer a sequence such as:
	    - `estimate_subfield_scope` to get the rough field size
	    - `analyze_topic_trends` to see when the field accelerated
	    - `measure_review_saturation` to distinguish a sparse subfield from a crowded one
	    - `rank_seminal_papers` and `get_citation_neighborhood` to identify anchor works and citation branches
	    - `retrieve_topic_literature` and `resolve_literature_identifiers` to normalize candidate PMIDs / DOIs before download
	Do not run multiple litmap MCP tools concurrently against the same server. Execute them serially, and if a timeout occurs, verify the MCP connection is still healthy before making another litmap call.
10. **User-Supplied Framework Is a First-Class Input**: If the user provides a framework, logical axes, supporting pillars, or a section skeleton, do not silently replace it with a generic review outline. Treat it as an explicit design prior. The task is to audit it against the evidence, preserve what survives, and only revise it with recorded reasons.
11. **Heavy Planning Choreography Belongs to the Framework Process**: If the user specifies an execution choreography such as `Orchestrator + Plan + Trials only`, fixed artifacts, staged outputs, exclusion rules, or a machine-readable handoff contract, treat those as part of the framework process rather than optional prompt decoration.
12. **Subagent Output Integrity Is Mandatory**: Every delegated file-writing task must declare exact output paths and acceptance criteria. After the subagent returns, verify that each required file exists and is non-empty before downstream planning uses it.
13. **Classify Against Explicit Criteria**: Paper classification prompts must include inclusion/exclusion criteria and the workspace-specific scope definition, not only paper names. Use `dir_name`, title, abstract, DOI/PMID, and available L2/L3 context before labeling a paper off-topic.
14. **Check Local Workspace Before External Lookup**: Before calling external identifier tools for seed papers, scan `workspace/<name>/papers.json` and local `dir_name`/PMID/DOI matches first. Only unresolved identifiers should trigger external lookup.

If the user is asking for a large, comprehensive review, read `references/full-review-coverage-mode.md` before proceeding.

## The Orchestrator Workflow

### Phase 1: Workspace Diagnosis & Gap Identification

1.  Inspect the current workspace (`autor ws show <name>`) and assess the existing themes (`autor topics` if available).
2.  Treat the current workspace and the total library only as a starting map. They can suggest what is already available locally, but they cannot certify coverage.
3.  In full-review mode, calibrate the likely field size and branch structure before pruning. Use landscape MCPs if available, or otherwise external metadata search, to estimate:
	    - approximate total paper count
	    - major platform branches
	    - major disease branches
	    - recent acceleration years
	    - whether the subfield is already review-saturated
4.  Build an explicit **query matrix** rather than relying on one broad query. At minimum, include:
	    - platform terms (`CAR-T`, `CAAR-T`, `CAR-Treg`, `CAR-NK`, `CAR-M`, `engineered Treg`, `in vivo CAR`, `allogeneic`, `iPSC`)
	    - disease buckets (the major autoimmune diseases relevant to the topic)
	    - translational/supporting topics (`toxicity`, `manufacturing`, `conditioning`, `persistence`, `immune reset`, `organ remodeling`)
	    - adjacent non-autoimmune comparator queries when needed to explain platform behavior
5.  Run the initial `plan` logic to generate the first draft of the structure, evidence classification, and claim-evidence mapping.
6.  If the user supplied a framework, audit every major framework unit explicitly. For each axis, pillar, or proposed section, record one of:
	    - keep
	    - merge
	    - split
	    - rename
	    - reposition
	    - defer as evidence-thin
	    - drop as unsupported
	Do not discard a user framework unit without a stated evidence-based reason.
7.  For each major section, controversy, or thin area, test coverage against external databases through the Records service metadata search or REST retrieval. Do not answer "is the literature complete?" by searching only the local library.
8.  Critically analyze the output for **Evidence-Thin Areas**:
	    - Which subheadings lack sufficient high-quality papers?
	    - Are there critical mechanisms, competing theories, or recent advancements missing from the workspace?
	    - Is the current hypothesis too shallow because of missing literature?

### Phase 2: Directed Literature Acquisition (Strict Wait)

If Phase 1 identifies gaps (which is expected in early iterations):

1.  Formulate precise, targeted search queries to fill the specific gaps identified.
2.  In full-review mode, do not stop at “gap filling”. Also run the broad query matrix needed to construct the field-level universe corpus. The first acquisition pass should be breadth-seeking, not only gap-repairing.
3.  Run those queries against external databases through the Records service metadata retrieval. Use the returned metadata to judge whether the missing literature is real, adjacent-but-out-of-scope, or simply absent from the local library.
4.  Before download, build a traceable candidate ledger containing at least the query source, PMID/DOI, title, branch (`platform`, `disease`, `toxicity`, `manufacturing`, `adjacent comparator`), and provisional status (`retain for download`, `metadata only`, `exclude`).
5.  In full-review mode, exclude from the universe corpus only:
	    - exact duplicates
	    - retracted papers
	    - clearly off-scope papers
	    - records with unusable metadata that cannot be resolved after identifier normalization
	Do not exclude a directly relevant paper merely because it is not “high impact” enough before the field map is complete.
6.  Directly invoke the literature acquisition workflow (`autodownload` / `autor pipeline` / REST API calls) to fetch the missing papers and ingest them into the workspace.
7.  **WAIT.** This process is extremely slow. Monitor the background terminal. **Do not hallucinate progress, do not timeout prematurely, and do not skip this step.** Ensure the papers are fully ingested, indexed, and attached to the workspace before proceeding.

### Phase 3: Hypothesis Evolution & Re-planning

Once new literature is successfully integrated:

1.  Re-run the `plan` sequence internally to reassess.
2.  Compare the new evidence against the old hypothesis:
	    - Does the new literature contradict the previous assumptions? (If yes, update the hypothesis and the controversy table).
	    - Do the new papers necessitate splitting a heading or adding a new technical mechanism?
3.  For every key paper, check whether usable conclusion evidence exists. If L3 extraction failed, is empty, or is too weak for the needed claim, open the full text. If the local system still cannot produce a usable conclusion layer, expose the full text to a reading subagent and require a structured output containing:
	    - what the paper is mainly about
	    - the main conclusions relevant to the review question
	    - quantitative findings or boundary conditions if available
	    - uncertainties or limitations that affect how the paper should be cited
4.  Update all planning deliverables (`review-plan.md`, `paper-classification.md`, `section-evidence.md`, `table-plan.md`). Each major section should leave behind enough structure for judgment-led drafting: what the retained evidence supports most strongly, what remains contested or thin, and what the section should refuse to overclaim.
5.  If the user supplied a framework or planning choreography, ensure the deliverables preserve it in transformed form. The plan should show:
	    - which parts of the original framework survived intact
	    - which parts were reframed
	    - which parts became evidence-thin notes rather than body sections
	    - how the user-requested execution choreography maps onto the final artifact set
6.  In full-review mode, explicitly distinguish:
	    - coverage gaps: a branch of the literature was not yet searched or downloaded
	    - evidence gaps: the branch exists but is thin or weak
	    - true research gaps: the branch appears genuinely sparse after rigorous external search
7.  Record the corpus layering in the planning artifacts. The user should be able to see how many papers are in the universe corpus, how many entered the working corpus, and which subset forms the core analytical corpus.
8.  If critical gaps *still* exist, loop back to Phase 2. Do not loop endlessly; if evidence cannot be found after rigorous search in external databases, document it as a "True Research Gap" rather than a missing paper.

### Phase 4: Independent Verification (Mandatory)

Once you (the orchestrator) believe the workspace is saturated and the plan is solid, you must submit it for independent review.

1.  Formulate a prompt containing the user's original research objective and the paths to the planning deliverables in the workspace.
2.  Invoke the `runSubagent` tool to summon an independent planning verification agent (e.g., `Explore` or a dedicated subagent).
	    - **Instructions for Subagent**: "Review the comprehensive review plan in `workspace/<name>/review-plan.md` and the evidence mapping in `section-evidence.md`. Evaluate if the evidence is truly saturated for the given topic, if the hypothesis is logically sound, and if the structure is ready for formal drafting. Confirm that completeness was judged against external database retrieval rather than local-library search alone, that full-review mode (if requested) built a universe corpus before aggressive pruning, and that key papers missing L3 conclusions were resolved through full-text reading or a full-text reading subagent. Do not write the paper. Only output 'APPROVED' or a list of specific, fatal flaws that require another round of literature acquisition."
3.  If the subagent rejects the plan, you must address the flaws (returning to Phase 2 or 3).
4.  If the subagent approves, output a final summary of the evolved hypothesis and declare the orchestrator workflow successfully completed. **Stop completely.** Do not initiate writing.
