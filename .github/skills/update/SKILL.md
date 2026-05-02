---
name: update
description: Revise a manuscript under reviewer or editor comments with traceable, fit-for-comment edits. Preserves unaffected content by default, but escalates to true rewrites and targeted literature reacquisition when reviewer intent requires it.
license: MIT
---

# Reviewer-Driven Manuscript Update

Use this skill when the user wants to **revise the manuscript itself** under reviewer or editor feedback.

The goal is **not** to rewrite the whole paper blindly. The goal is to produce a controlled revision package that:

- preserves valid original structure, tone, and contribution boundaries where they still work
- distinguishes minor fixes from true section-level failures
- escalates to real rewrites, new subsections, or new tables when patching cannot satisfy reviewer intent
- reacquires and rereads literature when rewritten text outgrows the current evidence support
- keeps every edit traceable to a specific reviewer request

## Core operating principles

This skill follows seven non-negotiable principles:

1. **Reviewer-driven, not rewrite-driven**
2. **Minimum sufficient change, not minimum visible change**
3. **Preserve valid original content**
4. **Detect section-level failure modes early**
5. **Evidence-gated expansion**
6. **Full-text reacquisition before major rewrites**
7. **Structured outputs**

Hard rules:

- Sections not materially touched by reviewer comments should remain unchanged by default
- Do **not** let a minimum-change discipline force an inadequate response to a major reviewer criticism
- If one sentence solves the issue, do not rewrite a paragraph
- If one paragraph solves the issue, do not rewrite a section
- If the reviewer is rejecting the current analytical logic, systematic coverage, mechanistic framing, or section architecture, do **not** respond with only bridge sentences
- If a comment requires a dedicated comparison framework, systematic clinical coverage, a new mechanistic branch, or broad disease-by-disease justification, treat the affected unit as a **rewrite package**, not as a sentence patch
- Any major rewrite or new subsection must be supported by retained **full-text** papers and/or retained trial records actually loaded into autor
- Title-only ingest, abstract-only substitution, or model-memory synthesis are not acceptable support for major rewrites
- If outside evidence is used, record the trigger, search target, acquisition path, insertion point, and retain/exclude decision
- Do not hand over only a final manuscript; always include the revision rationale and mapping

## When to use this skill

Typical use cases:

- reviewer-driven revision of SCI, SSCI, biomedical, methods, or original research manuscripts
- editor comments, external review, or joint reviewer feedback that requires targeted manuscript changes
- revisions where some comments are minor but others demand true section rebuilding
- revisions where outside literature, clinical-trial records, or guideline updates may be needed, but only in a tightly scoped way

## When not to use this skill

- **Freeform whole-manuscript polishing** -> use `polish` or `writing-polish`
- **Point-by-point response letter only** -> use `review-response`
- **A new review manuscript or section drafted from scratch** -> use `plan`, `write`, `literature-review`, or `paper-writing`
- **Unbounded literature expansion around the topic** -> use `autodownload` or `explore` as a separate evidence-building workflow

## Workspace and output location

Prefer binding the task to a **workspace** (`--ws NAME`) so the manuscript, revision table, evidence log, and any auxiliary outputs stay together.

If the user does not provide a workspace but the revision is clearly part of an ongoing project, reuse that workspace.
If no suitable workspace exists, create one first:

```bash
autor ws init <name>
```

Write outputs under:

```text
workspace/<name>/revision/
```

Always provide:

- `original-manuscript-copy.<ext>`
- `revised-manuscript.md`
- `revision-mapping-table.md`

Recommended:

- `manuscript-structure-summary.md`
- `reviewer-intent-summary.md`
- `rewrite-assessment.md`
- `evidence-gap-ledger.md`
- `external-evidence-log.md`
- `response-letter.md`
- `unresolved-issues.md`

Hard requirement:

- If any comment escalates to `SECTION_REWRITE`, `ADD_SUBSECTION`, `ADD_SECTION`, or `FRAME_REPLAN`, create `rewrite-assessment.md`
- If outside evidence is acquired or rejected during revision, create `external-evidence-log.md`

If the user needs a `.docx` deliverable, first finish the revision in Markdown, then use `document` to produce or inspect the final Office file.

## Inputs

Required:

- **Original manuscript**: docx, pdf, markdown, or plain text
- **Reviewer comments**: structured list or free text

Optional:

- **Editor comments** or decision letter
- **Author constraints**, for example:
  - do not change the main conclusion
  - do not add new experiments
  - do not exceed the journal length limit
  - do not change the section structure unless required
  - preserve the author's established writing voice
- **Journal constraints**, for example:
  - word limit
  - figure/table limit
  - reference style
  - response-letter template
- **Workspace name**
- **allow_major_rewrite**: default `true`
- **allow_external_literature**: default `auto_if_required_by_rewrite`
- **external_search_scope**: `none`, `minimal_gap_fill`, `targeted_update_only`, or `full_targeted_search`
- **output_style**: deliverables only, or deliverables plus worklog

## Adjacent skills and when to call them

| Skill | Use it when |
| --- | --- |
| `search`, `show`, `graph`, `citations` | First-pass evidence retrieval inside the current workspace or the local library |
| `workspace` | Newly retained papers should be added to the active workspace for section-level use |
| `ingest` | Downloaded PDFs or new markdown files must be processed into autor before the rewritten section is finalized |
| `trials` | Reviewer comments ask for clinical-trial phase, status, recruitment, location, or registry evidence |
| `autodownload` | Outside literature is justified and must be acquired through the Records service REST API |
| `review-response` | The manuscript revision is done and the user now needs a point-by-point response letter |
| `citation-check` | New citations were added and must be verified before submission |
| `polish`, `writing-polish` | Structural revision is complete and the user wants final language cleanup |
| `document` | The final deliverable must be generated or inspected as DOCX/PPTX/XLSX |

## Decision policy

### First principle

First understand **what the manuscript is already saying**.
Then understand **what the reviewer is actually rejecting or asking for**.
Then decide whether the problem is local wording, missing evidence, failed analysis, broken structure, or missing coverage.

Only after that should you choose the edit size.

### Decision order

For each reviewer comment:

1. Decide whether it truly triggers a manuscript change
2. Infer the underlying failure type
3. Classify the required revision intensity
4. Decide whether the current manuscript and local library can absorb the request internally
5. Decide whether outside evidence or trial records are necessary
6. Choose the **smallest edit that fully resolves the comment**, not merely the smallest visible change

### No-change conditions

Choose **NO_CHANGE** when:

- the manuscript already covers the point adequately
- the reviewer misread the text but the manuscript already states the needed clarification clearly
- the requested addition would break the manuscript's main line without being essential
- the requested expansion is genuinely outside scope

In that case, do **not** silently ignore the comment. Record the rationale in the revision mapping table.

## Failure types

Classify each comment into one or more failure types before editing:

| Failure type | Meaning | Typical consequence |
| --- | --- | --- |
| `CLARITY_GAP` | The point exists but is not stated clearly enough | micro insert or paragraph expansion |
| `LOGIC_GAP` | The section says facts but does not make the intended analytical link | local rewrite or section rewrite |
| `EVIDENCE_GAP` | The current support is too thin or outdated for the requested claim | targeted literature refresh |
| `STRUCTURE_GAP` | The current section organization cannot carry the requested answer | add subsection or section rewrite |
| `COVERAGE_GAP` | The manuscript is missing a branch, table, comparison axis, or disease class | add table, subsection, or section |
| `TRIAL_GAP` | Reviewer wants registry-grounded translational evidence | run `trials` and integrate as a parallel evidence layer |
| `POSITIONING_GAP` | The manuscript does not position itself against existing reviews or competing platforms | local rewrite plus targeted evidence update |

## Edit levels

Start from the smallest edit level and escalate only when a lower level cannot satisfy the request.

| Code | Meaning | Typical use |
| --- | --- | --- |
| `NO_CHANGE` | Do not change the body text; explain the decision in the mapping table | Reviewer concern already covered or clearly out of scope |
| `MICRO_INSERT` | Add 1-2 sentences | Clarification, caveat, definition, bridge sentence |
| `PARAGRAPH_EXPANSION` | Expand one paragraph without rebuilding the subsection | Add missing context, evidence, or comparison |
| `LOCAL_REWRITE` | Rewrite a specific paragraph while keeping the subsection intact | Fix a flawed explanation or align a paragraph to reviewer intent |
| `SECTION_REWRITE` | Rewrite an entire subsection or section while keeping the surrounding manuscript stable | The current section is descriptive, outdated, analytically weak, or patchy |
| `ADD_SUBSECTION` | Add a focused subsection | A systematic concern cannot be handled by isolated sentence edits |
| `ADD_SECTION` | Add a new section or major branch | A missing topic or comparison axis cannot be housed inside existing sections |
| `ADD_TABLE` | Add a comparison, summary, clinical, or platform table | Structured comparison is better than broad body-text expansion |
| `REFERENCE_UPDATE` | Add or replace citations with limited body-text change | Evidence refresh, latest review, guideline update |
| `FRAME_REPLAN` | Re-outline the affected manuscript branch before revising prose | Multiple comments expose a broken local architecture |

### Major-rewrite triggers

Escalate to a major rewrite package when one or more of the following apply:

- the reviewer says the manuscript is **descriptive rather than analytical**
- the reviewer asks for **systematic coverage** that the current section does not contain
- the reviewer requests a **dedicated comparison framework**, **new clinical-status table**, or **new mechanistic branch**
- multiple disease subsections all lack the same mechanistic or translational justification
- the affected section would otherwise become patchwork through multiple inserts
- the current local evidence is insufficient and the section must be rebuilt around newly acquired papers

## Workflow

### 1. Intake and boundary setting

Read the materials and establish the task boundary:

- identify the manuscript topic, main line, structure, core claims, and already mature sections
- split reviewer comments into executable comment units
- merge editor comments and author constraints into the same working boundary

Recommended outputs:

- `manuscript-structure-summary.md`
- `reviewer-intent-summary.md`

### 2. Infer reviewer intent

Do not respond only to the surface wording of a comment. Infer what the reviewer is actually trying to achieve.

Common reviewer-intent classes:

- concept clarification
- mechanistic strengthening
- structural optimization
- evidence update
- tabulation or comparison
- clinical translation
- positioning against existing reviews
- language or presentation cleanup

Then decide whether the reviewer is asking for:

- a clearer explanation
- more evidence
- a different organization format
- a new section-level analytical frame
- or a justified no-change response

### 3. Map each comment to manuscript locations

Build an explicit mapping from each comment unit to one or more manuscript locations:

- section
- subsection
- paragraph
- figure legend
- table
- references

Do **not** skip this step and jump straight to revising the text.

### 4. Classify revision intensity and evidence need

For each comment unit, record:

- failure type
- affected manuscript unit
- edit level
- whether the problem is local or section-level
- whether local evidence is sufficient
- whether `trials` is needed
- whether outside literature acquisition is needed

If any unit escalates to `SECTION_REWRITE`, `ADD_SUBSECTION`, `ADD_SECTION`, or `FRAME_REPLAN`, create `rewrite-assessment.md`.

Recommended columns:

| Column | Meaning |
| --- | --- |
| `reviewer_comment_id` | Stable comment ID |
| `failure_type` | One or more of the defined failure types |
| `affected_unit` | Section, subsection, paragraph, table, or references |
| `edit_level` | One of the defined edit-level codes |
| `local_evidence_status` | `sufficient`, `thin`, or `insufficient` |
| `literature_refresh_required` | `Yes` or `No` |
| `trial_layer_required` | `Yes` or `No` |
| `planned_output` | patch, rewrite, table, subsection, section, or no change |

### 5. Internal evidence sweep

Before going outside, screen the following in order:

1. the original manuscript
2. the current workspace
3. the local autor library

Use `search`, `show`, `graph`, and `citations` first.

If the reviewer request is still under-supported, continue to the acquisition gate.

### 6. External evidence gate and acquisition loop

Outside evidence is optional for minor edits but often mandatory for major rewrite packages.

#### If `allow_external_literature = none` or `false`

Do **not** expand through outside acquisition.

Revise only from:

- the original manuscript
- the user's supplied materials
- the current workspace
- the already ingested local library

If a major rewrite is required under this constraint and the local evidence is insufficient, record the limitation explicitly in `unresolved-issues.md` and do not fake completeness.

#### If outside evidence is allowed

Apply the scope strictly:

- `minimal_gap_fill`: fill one clearly defined evidence hole
- `targeted_update_only`: add only the latest, clinical, mechanistic, platform, or comparison evidence needed by the comment
- `full_targeted_search`: conduct a broader but still reviewer-scoped search on the exact requested branch

#### Localized rule for autor: use REST, not MCP, for literature acquisition

When outside literature acquisition is justified:

- use the **Records-backed AutoDownload service** as the RESTful acquisition layer
- do **not** describe the acquisition step as an MCP workflow
- prefer `autodownload` for the service boundary and endpoint choice

Recommended sequence:

1. screen internally first with `search`, `show`, `graph`, and `citations`
2. formulate a **comment-scoped query set**, not a whole-field search, unless the reviewer explicitly demands systematic coverage
3. if the gap remains, use the Records service REST endpoints for candidate generation or identifier resolution:
   - `/retrieve`
   - `/lookup`
   - `/resolve`
4. retain only candidates that directly support the rewrite package
5. only after screening retained candidates, use `/download` or the task API to acquire PDFs
6. ingest the downloaded PDFs into autor
7. add retained papers to the active workspace
8. reread the retained papers at L2/L3/L4 before writing the rewritten section

Hard rules:

- title-only ingest is not an acceptable substitute for full PDF-based acquisition
- abstract-only support is not acceptable for `SECTION_REWRITE`, `ADD_SUBSECTION`, or `ADD_SECTION`
- when the reviewer asks for clinical-trial phase, status, or pipeline coverage, use `trials` in parallel rather than forcing everything through papers

#### Triggers for outside evidence

Outside evidence is justified when:

- the reviewer explicitly asks for updated literature, clinical developments, or current statistics
- the current manuscript lacks enough evidence to support the requested addition
- a new systematic table or new subsection is needed and the current material is incomplete
- the reviewer asks for a more systematic comparison than the manuscript currently contains
- a section has been classified as a major rewrite package and the local evidence is thin

Outside evidence is **not** justified when:

- the problem can be solved by reorganizing existing material
- the issue is mainly wording, structure, or logic flow without an evidence deficit
- the reviewer wants a clearer explanation rather than more evidence
- the author explicitly forbids outside acquisition

Whenever outside evidence is used, record at least:

- trigger comment ID
- reason for the search
- search question
- search scope
- acquisition path
- include / exclude decision
- manuscript insertion point

Write this to `external-evidence-log.md`.

### 7. Execute the revision

Revise according to the mapping and edit levels:

- preserve original wording whenever possible for untouched or still-valid passages
- revise only at mapped locations
- keep new content tightly aligned to the corresponding reviewer comment
- if a new table is added, use the body text mainly to introduce and interpret it, not to repeat it
- if multiple nearby comments reveal the same weak subsection, merge them into one coherent rewrite package
- for `SECTION_REWRITE`, `ADD_SUBSECTION`, and `ADD_SECTION`, rewrite the affected unit from retained evidence rather than stacking sentence patches onto the old prose
- update local transitions and cross-references when the rewritten unit changes the nearby text flow

### 8. Package the revision traceability set

Before delivery:

- complete the revision mapping table
- complete `rewrite-assessment.md` if any major rewrite package was triggered
- record the reason and evidence basis for every meaningful change
- mark comments that were answered without body-text changes
- keep the original manuscript copy alongside the revised manuscript

## Revision mapping table schema

`revision-mapping-table.md` must contain at least these columns:

| Column | Meaning |
| --- | --- |
| `reviewer_comment_id` | reviewer comment number or stable ID |
| `reviewer_request_summary` | surface request in concise form |
| `inferred_reviewer_intent` | what problem the reviewer is actually trying to solve |
| `failure_type` | one or more failure-type codes |
| `manuscript_location` | section, subsection, paragraph, table, or references touched |
| `edit_level` | one of the defined edit-level codes |
| `action_taken` | what was changed in practice |
| `rationale` | why this edit size and placement were chosen |
| `external_evidence_used` | `Yes` or `No` |
| `evidence_source_note` | source type and use note if outside evidence was used |
| `status` | `Done`, `Partially Done`, `Not Applicable`, or `Explained but Not Changed` |

## Quality checks

### Structural checks

- Are revisions concentrated only at mapped locations?
- Were untouched mature sections left intact?
- Did comments classified as major rewrite packages receive real rewrites rather than sentence patches?
- Is there any unrelated expansion?

### Logical checks

- Did every reviewer comment receive a response path?
- Does each action actually match reviewer intent?
- Did the revision become broader than necessary?
- Were descriptive or weak sections genuinely rebuilt when the reviewer asked for analytical strengthening?

### Evidence checks

- Was outside evidence used only when justified?
- If it was used, was it recorded in `external-evidence-log.md`?
- If a major rewrite required fresh evidence, were the PDFs downloaded, ingested, and reread before the text was rewritten?
- If new citations were added, were they passed through `citation-check`?

### Deliverable checks

- Is the original manuscript copy included?
- Is the revised manuscript included?
- Is the revision mapping table included?
- Can every meaningful change be traced back to a reviewer request?

## Common failure modes and how to handle them

- **Minimum-change bias produces a cosmetically edited but still inadequate section**
  - reclassify the section as `SECTION_REWRITE` and rebuild it
- **Reviewer comments are too vague**
  - infer intent first, then split them into executable action items
- **The manuscript already partly addresses the concern**
  - prefer clarification and local strengthening over rewrite
- **A systematic addition is needed but large-scale body expansion is not appropriate**
  - add a table or focused subsection
- **Outside acquisition is forbidden but the reviewer asks for more literature**
  - state the evidence constraint explicitly and keep the revision conservative
- **The reviewer misread the manuscript**
  - use `NO_CHANGE` if appropriate, and explain clearly in the mapping table
- **Downloaded papers were collected but not truly integrated**
  - reread the retained set and revise the affected section from the retained evidence, not from the candidate list

## Minimal execution example

If the user allows outside literature with `external_search_scope = targeted_update_only`, the expected behavior is:

- do not rewrite the whole manuscript
- localize edits to the affected sections and paragraphs
- classify each comment into minor or major revision intensity
- handle conceptual comments through micro inserts or paragraph expansions only when the local section is otherwise sound
- handle descriptive-versus-analytical criticisms, systematic coverage requests, or new comparison frameworks through section rewrites, new subsections, or tables as needed
- use the Records service REST API or `trials` only for evidence gaps that cannot be closed internally
- ingest and reread retained full-text papers before any major rewrite
- deliver the original manuscript copy, revised manuscript, revision mapping table, and the relevant evidence / rewrite logs

## Example prompts

- "Use `/update` to revise my manuscript under these reviewer comments. Preserve unaffected sections, but allow real section rewrites where the comments show the current section is inadequate."
- "Revise this review article for resubmission. Minor comments should stay local, but comments requiring new comparison frameworks or systematic clinical coverage should trigger major rewrites plus targeted literature acquisition."
- "Handle these reviewer comments conservatively where possible, but do not answer major analytical criticisms with cosmetic edits. You may add outside literature only for the exact rewrite packages that require it."
- "Use `/update` first for the manuscript revision, then use `/review-response` to draft the response letter."
