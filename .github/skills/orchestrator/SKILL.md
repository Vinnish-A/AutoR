---
name: orchestrator
description: High-level orchestrator for iterative research planning and hypothesis evolution. Evaluates workspace completeness, triggers targeted literature acquisition, refines review plans, and mandates independent subagent verification before concluding. Strictly stops before writing.
---

# Orchestrator: Iterative Research Planning & Hypothesis Evolution

This skill acts as the highest-level director for literature review preparation. Instead of just generating an outline once, the orchestrator implements a **closed-loop hypothesis evolution workflow**: it diagnoses the current workspace, finds evidence gaps, actively fetches missing literature (via AutoDownload), and continually revises the plan until the evidence is saturated and the hypothesis is robust. 

**CRITICAL CONSTRAINT: DO NOT PROCEED TO WRITING.** This skill is explicitly scoped to stop at the `plan` stage. You must **NEVER** invoke `write`, `paper-writing`, or any drafting skills. Your final output is a completely verified, evidence-saturated planning blueprint.

## Execution Rules & Philosophy

1.  **Strict Blocking on Literature Ingestion**: Downloading and processing PDFs (especially via MinerU) is extremely slow. **You must disable all fallbacks.** Do not mock data, do not attempt to proceed with partial data, and do not fall back to abstract-only reviews if full-text ingestion is underway. You must wait for the ingestion pipeline to complete fully.
2.  **Iterative Hypothesis Evolution**: A research plan is not static. As new papers are acquired, the original hypothesis must be re-evaluated, challenged, and refined based on the newly ingested evidence.
3.  **Independent Subagent Verification**: You cannot self-certify that the planning is complete. You must launch an independent subagent to review the final deliverables against the user's original objective. You may only exit this skill when the subagent officially approves the plan.
4.  **The Global Library Is Reference-Only**: The local knowledge base / total library is useful for orientation, terminology, and quick cross-checking, but it must never be treated as proof that the literature is complete.
5.  **External Metadata and Full-Text Acquisition Are the Reliable Basis**: When deciding whether coverage is sufficient, rely on AutoDownload-driven external database retrieval, the returned field metadata, and the downstream download + processing pipeline. Do not decide "the literature is complete" merely because the local library search looks dense.
6.  **Full-Text Fallback for Missing Conclusions**: If a key paper lacks a usable L3 conclusion, or if the paper is not yet present in the local library, obtain the full text through the acquisition pipeline. If the structured conclusion still cannot be extracted, expose the full text to a dedicated reading subagent and require it to output what the paper is about and what conclusions it supports.

## The Orchestrator Workflow

### Phase 1: Workspace Diagnosis & Gap Identification

1.  Inspect the current workspace (`autor ws show <name>`) and assess the existing themes (`autor topics` if available).
2.  Treat the current workspace and the total library only as a starting map. They can suggest what is already available locally, but they cannot certify coverage.
3.  Run the initial `plan` logic to generate the first draft of the structure, evidence classification, and claim-evidence mapping.
4.  For each major section, controversy, or thin area, test coverage against external databases through AutoDownload metadata search or REST retrieval. Do not answer "is the literature complete?" by searching only the local library.
5.  Critically analyze the output for **Evidence-Thin Areas**:
	    - Which subheadings lack sufficient high-quality papers?
	    - Are there critical mechanisms, competing theories, or recent advancements missing from the workspace?
	    - Is the current hypothesis too shallow because of missing literature?

### Phase 2: Directed Literature Acquisition (Strict Wait)

If Phase 1 identifies gaps (which is expected in early iterations):

1.  Formulate precise, targeted search queries to fill the specific gaps identified.
2.  Run those queries against external databases through AutoDownload metadata retrieval. Use the returned metadata to judge whether the missing literature is real, adjacent-but-out-of-scope, or simply absent from the local library.
3.  Directly invoke the literature acquisition workflow (`autodownload-expand` / `autor pipeline` / REST API calls) to fetch the missing papers and ingest them into the workspace.
4.  **WAIT.** This process is extremely slow. Monitor the background terminal. **Do not hallucinate progress, do not timeout prematurely, and do not skip this step.** Ensure the papers are fully ingested, indexed, and attached to the workspace before proceeding.

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
4.  Update all planning deliverables (`review-plan.md`, `paper-classification.md`, `section-evidence.md`, `table-plan.md`).
5.  If critical gaps *still* exist, loop back to Phase 2. Do not loop endlessly; if evidence cannot be found after rigorous search in external databases, document it as a "True Research Gap" rather than a missing paper.

### Phase 4: Independent Verification (Mandatory)

Once you (the orchestrator) believe the workspace is saturated and the plan is solid, you must submit it for independent review.

1.  Formulate a prompt containing the user's original research objective and the paths to the planning deliverables in the workspace.
2.  Invoke the `runSubagent` tool to summon an independent planning verification agent (e.g., `Explore` or a dedicated subagent).
	    - **Instructions for Subagent**: "Review the comprehensive review plan in `workspace/<name>/review-plan.md` and the evidence mapping in `section-evidence.md`. Evaluate if the evidence is truly saturated for the given topic, if the hypothesis is logically sound, and if the structure is ready for formal drafting. Confirm that completeness was judged against external database retrieval rather than local-library search alone, and that key papers missing L3 conclusions were resolved through full-text reading or a full-text reading subagent. Do not write the paper. Only output 'APPROVED' or a list of specific, fatal flaws that require another round of literature acquisition."
3.  If the subagent rejects the plan, you must address the flaws (returning to Phase 2 or 3).
4.  If the subagent approves, output a final summary of the evolved hypothesis and declare the orchestrator workflow successfully completed. **Stop completely.** Do not initiate writing.
