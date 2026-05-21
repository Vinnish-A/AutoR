---
name: orchestrator
description: High-level orchestrator for iterative review planning and hypothesis evolution. Builds the current autor planning package, triggers targeted acquisition, maintains corpus layers, and stops before writing.
---

# Orchestrator: Iterative Research Planning

Use this skill for large or iterative review planning, especially when the user wants coverage checking, framework evolution, targeted acquisition, trial mapping, or independent verification before writing.

Do not draft manuscript prose.

## Canonical Outputs

The orchestrator must leave the workspace in the current planning format:

```text
workspace/<name>/references.bib
workspace/<name>/reference-map.json
workspace/<name>/review-plan.md
workspace/<name>/evidence-ledger.md
workspace/<name>/table-figure-plan.md
workspace/<name>/acquisition-log.md if acquisition, trials, or citation-network work occurred
workspace/<name>/sidecars/
```

`references.bib` citation keys are canonical across all downstream artifacts.

Compatibility exports (`paper-classification.md`, `section-evidence.md`, `table-plan.md`, `execution-tasks.md`, `corpus-ledger.md`, `query-matrix.md`) are optional derived files only.

## Core Rules

1. Treat the global library as orientation, not proof of completeness.
2. For full reviews, build a universe corpus before pruning to the working and core analytical corpora.
3. Use the user framework as a first-class input. Audit every unit as keep, merge, split, rename, reposition, defer, or drop.
4. Use Records-backed `autodownload` for justified external acquisition. Do not use Playwright fallback.
5. Ingest full PDFs before using new papers for major planning claims.
6. Maintain citation-key identity through `references.bib` and `reference-map.json`.
7. Keep trial records as a parallel evidence layer.
8. Stop at an approved plan; writing belongs to the `write` skill.

For full-review coverage-first work, read `references/full-review-coverage-mode.md`.

## Workflow

### 1. Diagnose

- inspect `workspace/<name>/papers.json`
- inspect existing canonical planning files
- run `autor ws status <name> --papers` and `autor ws export-evidence <name>` for a machine-readable completeness check
- run local workspace search and L2/L3 reading for orientation; preserve L3 mode (`explicit_section`, `inferred_synthesis`, etc.) when it affects evidence confidence
- identify current corpus layers, missing branches, and unresolved references
If L3 coverage is incomplete, use workspace-scoped enrichment (`autor enrich-l3 --workspace <name> --only-missing` or MCP `workspace_enrich_l3`) before planning claims that depend on paper-level conclusions.

### 2. Normalize identity

- export or repair `references.bib`
- create or update `reference-map.json`
- ensure retained papers have stable citation keys
- keep UUIDs, dir names, PMIDs, DOIs, and full-text status in `reference-map.json`
Use `autor ws plan-package <name>` for a fresh identity/evidence scaffold when these files are missing, then revise the generated plan into the current review framework.

### 3. Calibrate coverage

For full reviews, use landscape tools when available and/or external metadata retrieval to estimate:

- field size
- recent growth
- review saturation
- seminal papers
- branch structure
- identifier normalization problems

Build a query matrix when external coverage checking is performed, but store it inside `acquisition-log.md` unless a tool requires a sidecar.

### 4. Acquire and ingest when needed

Use `autodownload` only when a real gap or full-review coverage requirement justifies it.

Record:

- query branch
- candidate identifiers
- include/exclude decisions
- download status
- ingest status
- workspace attachment status

### 5. Re-plan

Run the planning logic after acquisition:

- update framework audit
- update section cards
- update corpus layers
- update section evidence
- update table and figure plan
- document evidence-thin and true research-gap areas

### 6. Trials and citation network

Use `trials` when clinically relevant. Save trial outputs under `workspace/<name>/trials/` and map retained trial IDs to sections.

If citation-network mapping is used, save raw graph data under `sidecars/` and summarize lineages or conceptual bridges in `acquisition-log.md` or `review-plan.md`.

### 7. Verify

Before approval, verify:

- every retained citation key exists in `references.bib`
- every retained key appears in `reference-map.json`
- every working/core paper maps to at least one section
- every major section has evidence support
- every table or figure has a source evidence set
- excluded and unresolved records have reasons
- external completeness judgments are not based only on local library density

Use an independent verification subagent when the task is large enough and subagents are available.

## Final Output

Return the same handoff block used by `plan`:

```text
FRAME_STATUS: APPROVED | REPLAN_REQUIRED | BLOCKED
WORKSPACE: <name>
LANGUAGE: <language>
ARTICLE_TYPE: <type>
STYLE_BASELINE: <style>
REVIEW_SCOPE_PROFILE: <scope>
TRIALS_STATUS: COMPLETED | NOT_APPLICABLE | BLOCKED
CITATION_NETWORK_STATUS: COMPLETED | NOT_APPLICABLE | BLOCKED
CORE_HYPOTHESIS: <1-2 sentences>
REFERENCE_POLICY: references.bib citation keys are canonical
CORPUS_COUNTS:
- universe: <n>
- working: <n>
- core: <n>
- excluded: <n>
- unresolved: <n>
HANDOFF_FILES:
- workspace/<name>/references.bib
- workspace/<name>/reference-map.json
- workspace/<name>/review-plan.md
- workspace/<name>/evidence-ledger.md
- workspace/<name>/table-figure-plan.md
- workspace/<name>/acquisition-log.md if applicable
OPEN_GAPS:
- <NONE or explicit list>
NEXT_ACTION: run_write | run_targeted_acquisition | return_to_user
```
