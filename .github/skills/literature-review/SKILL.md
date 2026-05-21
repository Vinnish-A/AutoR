---
name: literature-review
description: Write an exploratory literature review based on papers in an autor workspace. For approved review-article workflows, defer to plan and write, which use the canonical references.bib / reference-map.json / evidence-ledger contract.
---

# Literature Review Writing

Use this skill for open-ended exploratory review writing, research summaries, thesis literature-review chapters, or early state-of-the-art sketches.

For formal review-article production, prefer:

1. `plan` to build the canonical planning package
2. `write` to draft from that approved package

## Canonical Plan Awareness

If the workspace contains:

```text
references.bib
reference-map.json
review-plan.md
evidence-ledger.md
table-figure-plan.md
```

then these files are hard constraints, not optional background. Do not rebuild the outline or evidence set during exploratory writing. If the user wants formal prose from that package, switch to `write`.

Older files such as `paper-classification.md`, `section-evidence.md`, `table-plan.md`, and `execution-tasks.md` are compatibility exports only. Trust the canonical files when conflicts exist.

## Prerequisites

The user should specify a workspace. If not:

1. run `autor ws list`
2. reuse an obvious active workspace or ask the user to choose

Write outputs under `workspace/<name>/`.

## Workflow

### 1. Clarify the task

Confirm or infer:

- topic or research question
- audience and output type
- language
- approximate length
- whether the task is exploratory or plan-grounded
- whether the canonical planning package already exists

### 2. Survey the workspace

```bash
autor ws show <name>
autor ws search <name> "<topic>"
autor show <dir_name> --level 2
```

Escalate core papers to L3/L4 only when needed:

```bash
autor show <dir_name> --level 3
autor show <dir_name> --level 4
```

L3 is a paper-level conclusion card. It may include an inferred synthesis when a paper lacks a clear conclusion section. Use it for orientation, but verify numerical or controversial claims against L4 or an approved evidence ledger.

Use citation graph tools for relationship checks:

```bash
autor refs "<id>"
autor citing "<id>"
autor shared-refs "<id1>" "<id2>"
```

### 3. Structure the review

If no canonical plan exists, propose an outline based on the workspace and user question.

If a canonical plan exists:

- follow `review-plan.md`
- use evidence from `evidence-ledger.md`
- use citation keys from `references.bib`
- respect roles and full-text status in `reference-map.json`
- use `table-figure-plan.md` for tables and figures

When the plan conflicts with new reading, return to `plan` instead of silently reshuffling the draft.

### 4. Draft

Writing principles:

- synthesize rather than enumerate papers
- identify contradictions, limitations, and boundary conditions
- distinguish authors' claims from established facts
- use citation keys from `references.bib` when the canonical package exists
- for informal early drafts without a canonical package, still avoid hallucinated citations and export references when possible

If drafting from an approved plan, the output should be handled by `write`, not this skill.

### 5. Save and check

Default output:

```text
workspace/<name>/literature-review.md
```

If citations are needed:

```bash
autor ws export <name> -o workspace/<name>/references.bib
```

Before delivery, check that:

- the text matches the requested scope
- citations are real and local to the workspace
- any deviation from a canonical plan is explicitly justified or routed back to `plan`

## Academic Attitude

- Paper conclusions are claims, not truth.
- High citation counts do not equal correctness.
- When papers disagree, explain possible causes rather than smoothing the disagreement away.
- Avoid turning review articles into substitutes for primary evidence.
