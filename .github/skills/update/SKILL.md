---
name: update
description: Revise a manuscript under reviewer or editor comments with minimum-necessary, traceable edits. Uses local evidence first, AutoDownload REST only for justified literature gaps, and `trials` for registry evidence.
license: MIT
---

# Reviewer-Driven Manuscript Update

Use this skill when the user wants to **revise the manuscript itself** under reviewer or editor feedback.

The goal is **not** to rewrite the whole paper. The goal is to produce a controlled revision package that:

- preserves the valid structure, tone, and contribution boundary of the original manuscript
- changes only the locations genuinely triggered by reviewer comments
- keeps every edit traceable to a specific reviewer request
- adds outside evidence only when the revision truly requires it

## Core operating principles

This skill follows six non-negotiable principles:

1. **Reviewer-driven, not rewrite-driven**
2. **Minimum necessary change**
3. **Preserve valid original content**
4. **Traceable edits**
5. **Evidence-gated expansion**
6. **Structured outputs**

Hard rules:

- Sections not materially touched by reviewer comments should remain unchanged by default
- If one sentence solves the issue, do not rewrite a paragraph
- If one paragraph solves the issue, do not rewrite a section
- If a table or focused subsection solves the issue, prefer that over broad body-text expansion
- Any new content must serve a concrete reviewer request rather than enlarging the manuscript scope
- If outside evidence is used, record the trigger, search target, insertion point, and use decision
- Do not hand over only a final manuscript; always include the revision rationale and mapping

## When to use this skill

Typical use cases:

- reviewer-driven revision of SCI, SSCI, biomedical, methods, or original research manuscripts
- editor comments, external review, or joint reviewer feedback that requires targeted manuscript changes
- revisions where the user wants an agent to keep a **minimum-change** discipline
- revisions where outside literature, clinical-trial records, or guideline updates may be needed, but only in a tightly scoped way

## When not to use this skill

- **Freeform whole-manuscript polishing** -> use `polish` or `writing-polish`
- **Point-by-point response letter only** -> use `review-response`
- **A new review manuscript or section drafted from scratch** -> use `plan`, `write`, `literature-review`, or `paper-writing`
- **Unbounded literature expansion around the topic** -> use `autodownload-*` or `explore` as a separate evidence-building workflow

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

At minimum, provide:

- `original-manuscript-copy.<ext>`
- `revised-manuscript.md`
- `revision-mapping-table.md`

Optional but recommended:

- `manuscript-structure-summary.md`
- `reviewer-intent-summary.md`
- `external-evidence-log.md`
- `response-letter.md`
- `unresolved-issues.md`

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
  - do not change the section structure
  - preserve the author's established writing voice
- **Journal constraints**, for example:
  - word limit
  - figure/table limit
  - reference style
  - response-letter template
- **Workspace name**
- **allow_external_literature**: default `false`
- **external_search_scope**: `none`, `minimal_gap_fill`, `targeted_update_only`, or `full_targeted_search`
- **output_style**: deliverables only, or deliverables plus worklog

## Adjacent skills and when to call them

| Skill | Use it when |
| --- | --- |
| `search`, `show`, `graph`, `citations` | First-pass evidence retrieval inside the local library or workspace |
| `trials` | Reviewer comments ask for clinical-trial phase, status, recruitment, location, or registry evidence |
| `autodownload-overview` | Outside literature is justified and must be acquired through AutoDownload's REST API |
| `review-response` | The manuscript revision is done and the user now needs a point-by-point response letter |
| `citation-check` | New citations were added and must be verified before submission |
| `polish`, `writing-polish` | Structural revision is complete and the user wants final language cleanup |
| `document` | The final deliverable must be generated or inspected as DOCX/PPTX/XLSX |

## Decision policy

### First principle

First understand **what the manuscript is already saying**. Then understand **what the reviewer is actually asking for**. Only then edit the overlap between the two.

### Decision order

For each reviewer comment:

1. Decide whether it truly triggers a manuscript change
2. Decide what object needs to change: sentence, paragraph, subsection, table, or references
3. Decide whether the manuscript can absorb the request internally
4. Decide whether outside evidence is necessary
5. Choose the smallest edit that satisfies the request

### No-change conditions

Choose **NO_CHANGE** when:

- the manuscript already covers the point adequately
- the reviewer misread the text but the manuscript already states the needed clarification clearly
- the requested addition would break the manuscript's main line without being essential
- the requested expansion is outside scope

In that case, do **not** silently ignore the comment. Record the rationale in the revision mapping table.

## Edit levels

Start from the smallest edit level and escalate only when a lower level cannot satisfy the request.

| Code | Meaning | Typical use |
| --- | --- | --- |
| `NO_CHANGE` | Do not change the body text; explain the decision in the mapping table | Reviewer concern already covered or clearly out of scope |
| `MICRO_INSERT` | Add 1-2 sentences | Clarification, caveat, definition, bridge sentence |
| `PARAGRAPH_EXPANSION` | Expand one paragraph without rebuilding the subsection | Add missing context, evidence, or comparison |
| `LOCAL_REWRITE` | Rewrite a specific paragraph while keeping the subsection intact | Fix a flawed explanation or align a paragraph to reviewer intent |
| `ADD_SUBSECTION` | Add a focused subsection | A systematic concern cannot be handled by isolated sentence edits |
| `ADD_TABLE` | Add a comparison, summary, clinical, or platform table | Structured comparison is better than broad body-text expansion |
| `REFERENCE_UPDATE` | Add or replace citations with minimal body-text change | Evidence refresh, latest review, guideline update |

## Workflow

### 1. Intake and boundary setting

Read the materials and establish the task boundary:

- identify the manuscript topic, main line, structure, core claims, and already mature sections
- split reviewer comments into executable comment units
- merge editor comments and author constraints into the same working boundary

Recommended outputs:

- `manuscript-structure-summary.md`
- `reviewer-intent-summary.md` or an equivalent structured note

### 2. Infer reviewer intent

Do not respond only to the surface wording of a comment. Infer what the reviewer is actually trying to achieve.

Common reviewer-intent classes:

- concept clarification
- mechanistic strengthening
- structural optimization
- evidence update
- tabulation or comparison
- clinical translation
- language or presentation cleanup

Then decide whether the reviewer is asking for:

- a clearer explanation
- more evidence
- a different organization format
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

Assign an edit level to each mapped item.

### 4. Assess whether the current manuscript can absorb the comment internally

Distinguish among:

- already present but not clear enough
- fully missing
- present but better expressed as a table or structured comparison

At this stage, decide whether a table is the better answer and whether outside evidence is genuinely required.

### 5. External evidence gate

Outside evidence is optional and must be justified. The default revision loop is:

1. manuscript itself
2. current workspace
3. local autor library
4. outside acquisition only if a real evidence gap remains

#### If `allow_external_literature = false`

Do **not** expand through outside acquisition. Revise only from:

- the original manuscript
- the user's supplied materials
- the current workspace
- the already ingested local library

If the reviewer asks for new literature under this constraint, record the limitation explicitly and make the most conservative internal revision possible.

#### If `allow_external_literature = true`

Apply the scope strictly:

- `minimal_gap_fill`: search only to fill a clearly defined evidence hole
- `targeted_update_only`: add only the latest, clinical, platform, or comparison evidence needed by the comment
- `full_targeted_search`: conduct a broader but still reviewer-scoped search on the exact requested topic

#### Localized rule for autor: use REST, not MCP, for literature acquisition

When outside literature acquisition is justified:

- use **AutoDownload as a RESTful service**
- do **not** describe the acquisition step as an MCP workflow
- prefer `autodownload-overview` for the service boundary and endpoint choice

Recommended sequence:

1. screen internally first with `search`, `show`, `graph`, and `citations`
2. if the gap remains, use AutoDownload REST endpoints for candidate generation or identifier resolution:
   - `/retrieve`
   - `/lookup`
   - `/resolve`
3. only after screening retained candidates, use `/download` to acquire PDFs
4. ingest the downloaded PDFs into autor and add retained papers to the workspace

Hard rule:

- title-only ingest is not an acceptable substitute for full PDF-based acquisition in this revision workflow

#### Use `trials` for trial-registry evidence

If the reviewer asks for:

- clinical-trial phase
- trial status
- recruiting status
- location
- registry-based treatment landscape

use `trials` rather than treating the request as a normal paper-only literature search.

#### Triggers for outside evidence

Outside evidence is justified when:

- the reviewer explicitly asks for updated literature, clinical developments, or current statistics
- the current manuscript lacks enough evidence to support the requested addition
- a new systematic table is needed and the current material is incomplete
- the reviewer asks for a more systematic comparison than the manuscript currently contains

Outside evidence is **not** justified when:

- the problem can be solved by reorganizing existing material
- the issue is mainly wording, structure, or logic flow
- the reviewer wants a clearer explanation rather than more evidence
- the author explicitly forbids outside acquisition

Whenever outside evidence is used, record at least:

- trigger comment ID
- reason for the search
- search question
- search scope
- inclusion decision
- manuscript insertion point

Write this to `external-evidence-log.md`.

### 6. Execute the revision

Revise according to the mapping and edit levels:

- preserve original wording whenever possible
- revise only at mapped locations
- keep new content tightly aligned to the corresponding reviewer comment
- if a new table is added, use the body text mainly to introduce and interpret it, not to repeat it

### 7. Package the revision traceability set

Before delivery:

- complete the revision mapping table
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
- Is there any unrelated expansion?

### Logical checks

- Did every reviewer comment receive a response path?
- Does each action actually match reviewer intent?
- Did the revision become broader than necessary?

### Evidence checks

- Was outside evidence used only when justified?
- If it was used, was it recorded in `external-evidence-log.md`?
- If new citations were added, were they passed through `citation-check`?

### Deliverable checks

- Is the original manuscript copy included?
- Is the revised manuscript included?
- Is the revision mapping table included?
- Can every meaningful change be traced back to a reviewer request?

## Common failure modes and how to handle them

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

## Minimal execution example

If the user allows outside literature with `external_search_scope = minimal_gap_fill`, the expected behavior is:

- do not rewrite the whole manuscript
- localize edits to the affected sections and paragraphs
- handle conceptual comments mainly through micro-inserts or paragraph expansions
- handle systematic comments mainly through a table or focused subsection
- use AutoDownload REST or `trials` only for evidence gaps that cannot be closed internally
- deliver the original manuscript copy, revised manuscript, revision mapping table, and optional evidence log

## Example prompts

- "Use `/update` to revise my manuscript under these reviewer comments, but keep changes minimal and traceable."
- "Revise this review article for resubmission. Do not change the structure unless the comments force it."
- "Handle these reviewer comments conservatively. You may add outside literature only for the latest clinical evidence."
- "Use `/update` first for the manuscript revision, then use `/review-response` to draft the response letter."
