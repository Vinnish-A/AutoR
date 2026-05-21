---
name: update
description: Revise a manuscript under reviewer or editor comments with traceable, fit-for-comment edits. Uses the current autor citation-key contract and compact revision package; preserves unaffected content but escalates to true rewrites when reviewer intent requires it.
license: MIT
---

# Reviewer-Driven Manuscript Update

Use this skill to revise an existing manuscript under reviewer or editor feedback. Do not rewrite the whole manuscript unless the comments expose a section-level or framework-level failure.

## Canonical Contract

Use the current workspace package when it exists:

```text
workspace/<name>/references.bib
workspace/<name>/reference-map.json
workspace/<name>/review-plan.md
workspace/<name>/evidence-ledger.md
workspace/<name>/table-figure-plan.md
workspace/<name>/acquisition-log.md if present
```

All revised manuscript citations must use citation keys from `references.bib`.

If the manuscript predates this package, build the minimum reference infrastructure before revising:

- export or repair `references.bib`
- create `reference-map.json`
- map existing manuscript citations to citation keys
- record unresolved references

## Required Inputs

- original manuscript
- reviewer comments
- workspace name if available

Optional:

- editor comments
- author constraints
- journal constraints
- external-evidence policy
- response-letter request

## Revision Principles

1. Reviewer-driven, not rewrite-driven.
2. Minimum sufficient change, not minimum visible change.
3. Preserve valid original content.
4. Escalate when patching would leave a weak or incoherent section.
5. Major rewrites need retained full-text papers and/or retained trial records.
6. External evidence must be justified, logged, and mapped to citation keys.
7. Every meaningful change must trace back to a comment.

## Revision Codes

Use exactly these edit levels:

- `NO_CHANGE`
- `MICRO_INSERT`
- `PARAGRAPH_EXPANSION`
- `LOCAL_REWRITE`
- `ADD_TABLE`
- `REFERENCE_UPDATE`
- `SECTION_REWRITE`
- `ADD_SUBSECTION`
- `ADD_SECTION`
- `FRAME_REPLAN`

Failure types:

- `CLARITY_GAP`
- `LOGIC_GAP`
- `EVIDENCE_GAP`
- `STRUCTURE_GAP`
- `COVERAGE_GAP`
- `TRIAL_GAP`
- `POSITIONING_GAP`

Major-rewrite packages are `SECTION_REWRITE`, `ADD_SUBSECTION`, `ADD_SECTION`, and `FRAME_REPLAN`.

## Evidence Policy

Local-first order:

1. original manuscript
2. current workspace plan and evidence package
3. local autor library
4. external retrieval only if the user permits it and a real evidence gap remains

Use `autodownload` / Records REST for justified paper acquisition. Do not use Playwright as a paper-acquisition fallback.

Use `trials` when comments ask for clinical program status, phase, recruitment, endpoints, or registry coverage. Trial records are a parallel evidence layer, not paper substitutes.

L3 is a paper-level conclusion card, not simply a copied conclusion section. Use L3 to triage whether a cited paper can address a reviewer comment, but check its mode. For `inferred_synthesis`, verify numerical, clinical, mechanistic, or disputed claims against source spans, `evidence-ledger.md`, or L4 before adding manuscript text.

When new papers enter the revision:

- ingest full PDFs before major rewrite use
- assign citation keys
- update `references.bib`
- update `reference-map.json`
- update `evidence-ledger.md` if the evidence boundary changes
- record the change in `revision/evidence-delta.md`

## Compact Revision Package

Write outputs under:

```text
workspace/<name>/revision/
```

Required:

```text
original-manuscript-copy.md
revision-plan.md
revised-manuscript.md
```

Conditional:

```text
evidence-delta.md       # if evidence changed, retrieval occurred, trials were added, or citation keys changed
response-letter.md      # if requested
```

Legacy files such as `revision-mapping-table.md`, `rewrite-assessment.md`, `evidence-gap-ledger.md`, `external-evidence-log.md`, and `unresolved-issues.md` are compatibility exports only. If created, mark them as derived from `revision-plan.md` or `evidence-delta.md`.

## `revision-plan.md` Schema

Include:

```text
Task brief
Manuscript boundary
Comment matrix
Major rewrite packages
Minor edits
Quality gate
```

The comment matrix must include:

```text
Comment ID | Reviewer request | Inferred intent | Failure type | Manuscript location | Edit level | Minor/Major | Evidence status | Action planned | Status
```

Major rewrite packages must include:

```text
Package ID | Trigger comments | Affected unit | Why patching is insufficient | Evidence needed | Planned output | Status
```

## `evidence-delta.md` Schema

Required when evidence changes. Include:

```text
Reference updates
Targeted searches
Trial updates
Citation verification
Plan or evidence-ledger updates
```

For each new or replaced citation, record the trigger comment and why the citation is allowed.

## Revision Workflow

1. Copy the original manuscript.
2. Split reviewer/editor comments into stable comment IDs.
3. Infer intent and failure type for each comment.
4. Map each comment to manuscript locations.
5. Classify edit level.
6. Check whether current evidence is sufficient.
7. For minor packages, revise locally.
8. For major packages, run a section-scoped evidence audit and targeted acquisition only if justified.
9. Update citation infrastructure if evidence changes.
10. Revise only mapped locations unless `FRAME_REPLAN` is required.
11. Run `citation-check` on new, replaced, or suspicious citations.
12. Preserve mature untouched sections.
13. Draft `response-letter.md` only if requested.

## Stop Conditions

Return `MORE_EVIDENCE_REQUIRED` when a major rewrite is needed but retained evidence is insufficient.

Return `BLOCKED` when required inputs are missing, citation keys cannot be reconciled, or user constraints make a valid revision impossible.

## Final Output

```text
REVISE_STATUS: APPROVED | MORE_EVIDENCE_REQUIRED | BLOCKED
WORKSPACE: <name>
LANGUAGE: <language>
ARTICLE_TYPE: <type>
STYLE_BASELINE: <style>
REVISION_SCOPE_PROFILE: <scope>
REFERENCE_POLICY: references.bib citation keys used throughout
MINOR_PACKAGE_COUNT: <n>
MAJOR_PACKAGE_COUNT: <n>
EXTERNAL_EVIDENCE_USED: YES | NO
TRIALS_STATUS: COMPLETED | NOT_APPLICABLE | BLOCKED
HANDOFF_FILES:
- workspace/<name>/revision/original-manuscript-copy.md
- workspace/<name>/revision/revision-plan.md
- workspace/<name>/revision/revised-manuscript.md
- workspace/<name>/revision/evidence-delta.md if applicable
- workspace/<name>/revision/response-letter.md if requested
UPDATED_CORE_FILES:
- workspace/<name>/references.bib if changed
- workspace/<name>/reference-map.json if changed
- workspace/<name>/evidence-ledger.md if changed
- workspace/<name>/table-figure-plan.md if changed
OPEN_GAPS:
- <NONE or explicit list>
NEXT_ACTION: finalize_revision | run_targeted_retrieval_and_retry | return_control_to_user
```
