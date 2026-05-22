---
name: write
description: Draft a fact-grounded review manuscript from an approved autor planning package. Uses references.bib citation keys, reference-map.json, review-plan.md, evidence-ledger.md, and table-figure-plan.md; use after plan is approved.
---

# Plan-Grounded Review Drafting

Use this skill after planning is approved. It turns the canonical planning package into manuscript prose. It is not for re-planning, adding new papers, or silently filling evidence gaps from memory.

Hard constraint for manuscript prose: writing prose may be delegated only to `autor write-agent`. No other external LLM calls, external translation services, or custom prose-generation scripts are allowed. Deterministic scripts are allowed only for formatting, citation checks, figure-status checks, DOCX export, and document inspection.

Do not use a section-file merge workflow. The canonical manuscript is one integrated file at `workspace/<name>/write.md`. `variants/` are non-canonical candidates only. Subagents may provide bounded advisory text or critique when explicitly authorized, but the responsible writing agent must integrate and revise the manuscript directly. MCP/client-side concatenation or scripted merging of `sections/` files is prohibited. Do not promote to `final.md` before external Critic and Check pass.

## Required Inputs

The user must specify a workspace. Before drafting, read:

```text
workspace/<name>/references.bib
workspace/<name>/reference-map.json
workspace/<name>/review-plan.md
workspace/<name>/evidence-ledger.md
workspace/<name>/table-figure-plan.md
workspace/<name>/acquisition-log.md if present
workspace/<name>/trials/** if referenced by the plan
```

If any of the first five files is missing or contradictory, stop and return to `plan`.

Older files such as `paper-classification.md`, `section-evidence.md`, `table-plan.md`, and `execution-tasks.md` are compatibility files only. If they conflict with the canonical files, trust the canonical files and report the conflict.

## Evidence Boundary

Hard rules:

1. Use only citation keys with `bibliographic_validity=citable` and retained trial records from the planning package.
2. Do not cite unresolved, duplicate-only, blocked-without-metadata, `needs_metadata_fix`, or `not_citable` records.
3. Excluded-but-citable, conflicting, taxonomy-boundary, adjacent, method, and background literature may be cited only for the role assigned in `reference-map.json` or `evidence-ledger.md`; do not use them as support for the central conclusion unless the plan explicitly assigns that role.
4. Follow `citation_policy`: `must_cite` papers must appear in the manuscript; `cite_if_relevant` papers may be omitted only when no drafted claim needs them; `background_only` papers cannot carry claim support; `do_not_cite` records must never appear as manuscript citations.
5. Trial records support program landscape, endpoint design, recruitment, phase, and safety-context claims. They do not replace paper evidence.
6. If a claim, table, or figure cannot be supported by the plan files, stop with a plan-gap note.
7. Use Pandoc citations such as `[@Smith2024]`; every key must exist in `references.bib`.
8. L3 is an orientation layer. If the plan marks an L3 as `inferred_synthesis`, use it for paper-level understanding but ground numerical, clinical, mechanistic, or controversial claims in the ledger's quantitative signals or L4-backed evidence.
9. Do not draft from an approved plan if it required a citation-network layer but `CITATION_NETWORK_STATUS` is not `COMPLETED`.
10. Preserve the valid-reference accounting: the manuscript citation universe is the `bibliographic_validity=citable` set, not merely the retained/supportive subset.

## Citation Assets

Ensure the manuscript starts with a valid YAML header:

```yaml
---
bibliography: references.bib
csl: csl/nature.csl
link-citations: true
reference-section-title: References
---
```

Use an existing CSL under the workspace when available. For Nature Reviews / Springer Nature Reviews style, use `workspace/<name>/csl/nature.csl`.

## Drafting Workflow

### 1. Run WriteAgent preflight and build

When writing is requested:

```bash
autor write-agent preflight <name>
autor write-agent build <name>
autor write-agent run <name>
autor write-agent critic-context <name> --round <N>
```

Then launch an external GPT-5.5 thinking high Critic subagent using `workspace/<name>/sidecars/critic-context.md`. If rejected, run:

```bash
autor write-agent revise <name> --ticket workspace/<name>/qa/round-<N>/critic-ticket.md
```

### 2. Draft as one integrated manuscript

`autor write-agent` generates section kernels, seed candidates, internal gate reports, and anchor replacements inside `workspace/<name>/write.md`. The writing agent may inspect these sidecars, but must not concatenate candidate files or promote a candidate from `variants/` directly.

Dash discipline:

- Do not use em dashes as the default device for contrast, clarification, or dramatic compression.
- Target no more than one em dash pair or dash break in a paragraph, and no more than two dash breaks per 1,000 words in the integrated manuscript.
- If adjacent paragraphs both rely on em dashes, rewrite at least one of them.
- Prefer a period, semicolon, colon, comma, parenthetical phrase, or a recast causal/contrastive sentence when the dash is only creating cadence.
- Keep a dash only when it marks a genuinely useful interruption, appositive clarification, or high-value contrast that would be weaker in ordinary syntax.

The integrated manuscript belongs at:

```text
workspace/<name>/write.md
```

Do not create `workspace/<name>/sections/` as the canonical drafting surface. Do not concatenate section files to form the final draft.

### 3. Integrated revision and polish

Revise the integrated manuscript as one coherent article:

- preserve approved section order
- normalize terms
- remove overlap
- preserve table and figure IDs
- resolve contradictions by following the plan and evidence ledger
- do not add new evidence
- scan for overused em dashes (`—` and sentence-level `--`); if a paragraph contains more than one, or the manuscript exceeds roughly two dash breaks per 1,000 words, revise before QA

Use `polish` only after the integrated draft exists, and only for language, rhythm, transitions, and removal of AI/process traces. Polish must not add facts, citations, sections, or hidden claims.

### 4. Quality gates

For substantial manuscripts, run `critic` and `check`.

Run citation coverage before promotion to `final.md` or export:

```bash
autor ws citation-coverage <name> --manuscript workspace/<name>/write.md --require must_cite --fail-if-missing
```

For full-review audits, also inspect citable coverage without `--fail-if-missing` and record why omitted `cite_if_relevant`, background, boundary, conflicting, or excluded-but-citable papers were not used.

Critic should check:

- plan fidelity
- citation-key validity
- bibliographic-validity compliance
- unsupported claims
- non-citable literature leakage
- misuse of excluded-but-citable, conflicting, or taxonomy-boundary records as positive support
- corpus-layer violations
- trial integration if relevant
- analytical value of tables and figures
- overclaiming from weak evidence
- overuse of em dashes or double-hyphen sentence breaks as an AI-like cadence crutch

Check should assess through-line, section progression, clinical/mechanistic hierarchy, evidence-thin honesty, and final prose quality.

If the failure is a plan gap, return to `plan` rather than patching the manuscript.

### 5. Figures and export

Generate every figure marked `ready` or required in `table-figure-plan.md`. A full review should normally complete 7-8 figures; a mini or focused review should normally complete 4-5 figures. If the plan records a smaller figure budget, preserve the exception and report it.

If figures are generated:

- use `plot-enhance` before every scientific image-generation call
- generate the image only through `autor plot` or `autor.plot.generate_plot()` from `autor/plot.py`
- do not hand-draw figure files with PIL, SVG, HTML canvas, slide shapes, or ad hoc scripts
- source each figure from the planned citation keys and section evidence
- save files under `workspace/<name>/figure/`
- write `workspace/<name>/figure/figure-manifest.json`

Before final export, run:

```bash
autor ws figure-status <name> --fail-if-missing
```

Do not promote or export the manuscript while planned figures are missing.

Only after QA passes, promote:

```text
workspace/<name>/write.md -> workspace/<name>/final.md
```

Export with Pandoc when requested:

```bash
cd workspace/<name> && pandoc final.md --citeproc -o final.docx
```

## Final Output

Return:

```text
CONTENT_STATUS: APPROVED | REWRITE_FROM_WRITE | RETURN_TO_ORCHESTRATOR | BLOCKED_BY_PLAN | EXPORT_BLOCKED
WORKSPACE: <name>
FAILED_STAGE: none | preflight | write | polish | critic | check | figure | export
CAUSE_CLASS: none | missing_input | plan_gap | evidence | structure | style | citation | figure_failure | export_failure
REFERENCE_POLICY: references.bib citation keys used throughout
MANUSCRIPT_FILES:
- workspace/<name>/write.md
- workspace/<name>/final.md if created
- workspace/<name>/final.docx if created
QA_FILES:
- workspace/<name>/qa/round-<N>/critic-ticket.md if created
- workspace/<name>/qa/round-<N>/check-report.md if created
OPEN_GAPS:
- <NONE or explicit list>
NEXT_ACTION: stop | rerun_write | return_orchestrator | export_after_user_approval
```
