---
name: plan
description: Plan a literature review before drafting. Build a canonical autor planning package using references.bib citation keys, reference-map.json, review-plan.md, evidence-ledger.md, and table-figure-plan.md. Use when the user wants to prepare a review article before writing.
---

# Review Planning Before Drafting

Use this skill to turn a workspace, topic, outline, candidate paper list, or user framework into an evidence-bound writing plan. Do not draft manuscript prose.

## Canonical Workspace Contract

The current autor planning contract uses these core files:

```text
workspace/<name>/references.bib
workspace/<name>/reference-map.json
workspace/<name>/review-plan.md
workspace/<name>/evidence-ledger.md
workspace/<name>/table-figure-plan.md
workspace/<name>/acquisition-log.md        # only if retrieval, trials, or citation-network work occurred
workspace/<name>/sidecars/                 # raw JSON and large auxiliary outputs
```

`references.bib` is the canonical citation-key authority. Planning, writing, tables, figures, and revision artifacts should refer to papers by BibTeX citation key, not by a mixture of UUID, directory name, PMID, DOI, and ad hoc short names.

Older files such as `paper-classification.md`, `section-evidence.md`, `table-plan.md`, and `execution-tasks.md` are compatibility exports only. Create them only when an older tool requires them, and mark them as derived from the canonical files.

## Required Inputs

- workspace name
- review topic or title
- language and article type if known
- scope profile: `full_review`, `mini_review`, or `focused_review`
- user framework, outline, or hypothesis if supplied
- candidate papers, PMIDs, DOIs, or retrieved notes if supplied
- constraints: journal, word count, must-keep topics, exclusions, or external-retrieval policy

If any input is missing but can be inferred safely from the workspace or user notes, infer it and record the assumption in `review-plan.md`.

## Workflow

### 1. Diagnose the workspace

Inspect the current workspace and any existing plan files.

Useful commands:

```bash
autor ws show <name>
autor ws status <name> --papers
autor ws export-evidence <name> -o workspace/<name>/evidence.json
autor ws search <name> "<topic>"
autor show <dir_name> --level 2
autor show <dir_name> --level 3
```

Use local library search for orientation, not as proof of field completeness.
If L3 coverage is missing, use `autor enrich-l3 --workspace <name> --only-missing` or the MCP `workspace_enrich_l3` tool; do not run all-library enrichment for a single review workspace.

L3 is a paper-level conclusion card. It may be an explicit conclusion-section extraction or an inferred synthesis from abstract/results/discussion and table/caption text when a paper has no clear conclusion section. MinerU image attachments are not retained. When using L3 during planning, record its mode and do not treat an inferred L3 as a substitute for L4 evidence on controversial or quantitative claims.

### 2. Normalize references first

Before writing section cards, lock the paper identity layer.

1. Export or repair `references.bib`.
2. Ensure every retained paper has one stable citation key.
3. Create `reference-map.json` mapping each citation key to:
   - autor UUID
   - dir name
   - PMID
   - DOI
   - title
   - paper type
   - corpus layer
   - status
   - evidence role
   - bibliographic validity
   - review use
   - citation policy
   - section mapping
   - full-text status
4. Use trial registry IDs for trials, but link any published trial paper through its citation key.

For an initial scaffold, use `autor ws plan-package <name> --title "<title>" --criteria "<scope>"`. Treat the generated files as identity/evidence scaffolding and then revise section cards, corpus layers, and table plans manually against the evidence.

### 3. Decide the coverage mode

- `full_review`: coverage-first. Build a visible universe corpus before narrowing to working and core analytical corpora.
- `mini_review`: representative and current. Keep a smaller but defensible evidence set.
- `focused_review`: exhaustive inside the narrowed scope. Depth matters more than breadth outside scope.

For `full_review`, read `references/full-review-coverage-mode.md` for the additional coverage-first rules.

### 4. Audit the user framework

If the user supplies axes, pillars, section skeletons, or a hypothesis, treat them as first-class inputs. For each unit, record one action:

- keep
- merge
- split
- rename
- reposition
- defer as evidence-thin
- drop as unsupported

The final outline must show what survived and why.

### 5. Use external acquisition only when justified

For external paper acquisition, use the Records-backed `autodownload` workflow. Do not use Playwright as fallback.

External retrieval is justified when:

- full-review coverage must be calibrated externally
- the user supplied candidate identifiers that are not in the workspace
- a section, controversy, or table has a real evidence gap
- recent or landmark literature is likely missing

External retrieval is not justified when:

- the task is only local writing from an already approved plan
- the missing issue is structural rather than evidentiary
- the user forbids new literature

If retrieval occurs, record query branches, candidate flow, download status, ingest status, and final inclusion decisions in `acquisition-log.md`. Raw service outputs belong under `sidecars/`.

### 6. Build the planning files

#### `review-plan.md`

Must include:

- task brief
- scope and boundaries
- framework audit
- final outline with stable section IDs such as `S1`, `S1.1`
- section cards
- corpus summary
- evidence gaps and true research gaps
- writing contract
- final handoff status

Each section card should include:

- section ID and title
- role in the review
- core claim the evidence can support
- key question
- required evidence
- main citation keys
- trial evidence if relevant
- evidence-thin warning
- planned tables or figures
- writing dependencies

#### `evidence-ledger.md`

Single source of truth for classification and evidence.

Must include:

- corpus-layer table by citation key
- section evidence tables
- excluded and unresolved records with reasons
- trial evidence table if applicable

Recommended section-evidence columns:

```text
Citekey | Evidence type | Supports | Usable claim | Quantitative signal | Boundary / limitation | Evidence origin
```

Recommended corpus-layer columns include `L3 mode` so downstream writing can distinguish explicit author conclusions from inferred synthesis.

Set `bibliographic_validity`, `review_use`, and `citation_policy` for every reference-map row. A valid reference is a bibliographically citable record, not necessarily a paper that supports the final conclusion. Excluded-but-citable, conflicting, taxonomy-boundary, method, and background literature can count toward the valid-reference target when it has stable metadata and a citation key.

Allowed `bibliographic_validity` values:

- `citable`: can be formally cited.
- `needs_metadata_fix`: potentially citable but not stable enough for writing.
- `not_citable`: unresolved, duplicate-only, blocked-without-metadata, or otherwise unsuitable for formal citation.

Allowed `review_use` values:

- `included_main`
- `excluded_but_citable`
- `conflicting_evidence`
- `taxonomy_boundary`
- `background_only`
- `method_source`
- `unresolved_seed`

Set `citation_policy` for every citable retained paper:

- `must_cite`: core evidence that should appear in the manuscript.
- `cite_if_relevant`: retained supporting literature that may be omitted if no claim needs it.
- `background_only`: orientation or framing source, not claim support.
- `do_not_cite`: only for non-citable provenance, unresolved, duplicate-only, or blocked records. Do not use it merely because a citable paper is excluded, contradictory, or taxonomy-boundary.

#### `table-figure-plan.md`

Must include only assets that should carry real analytical load.

Figure budget is mandatory:

- `full_review` / large review: plan 7-8 figures unless the target journal explicitly forbids it.
- `mini_review` / focused review: plan 4-5 figures.
- Every planned figure must have `PlotEnhance = required`; no figure may be treated as a loose optional illustration once it is marked `ready`.
- Every planned figure must be generated through the simple `autor plot` CLI or `autor.plot.generate_plot()` interface. Do not create manual PIL/SVG/HTML drawing scripts as substitutes for the plotting interface.

Tables:

```text
Table ID | Title | Purpose | Section slot | Rows | Columns | Required citekeys | Trial IDs | Must answer | Status
```

Figures:

```text
Figure ID | Title | Type | Section slot | Visual thesis | Source sections | Required citekeys | Trial IDs | PlotEnhance | Status
```

#### `acquisition-log.md`

Required only if external retrieval, trials, or citation-network work occurred.

Must include:

- query matrix
- candidate counts
- download and ingest status
- trial runs if any
- citation-network summary if any

### 7. Trial and citation-network layers

Use `trials` when clinical-program, endpoint, phase, recruitment, or registry evidence matters. Trial records are parallel evidence, not paper substitutes.

For formal review planning, build the citation-network layer unless the task is explicitly marked `not_applicable` with a reason. Prefer `autor refetch --workspace <name>` when references are sparse, then rebuild the index and run `autor ws citation-network <name>`. Keep raw network JSON under `sidecars/` and summarize the intellectual lineages in `acquisition-log.md` or `review-plan.md`. Do not turn raw graph output into another core planning file.

### 8. Final consistency check

Before approving the plan, verify:

- every retained citekey exists in `references.bib`
- every retained citekey appears in `reference-map.json`
- every reference-map row has `bibliographic_validity` and `review_use`
- the valid-reference count equals the number of `bibliographic_validity=citable` rows and meets the requested threshold
- every retained citekey has `citation_policy`
- every `must_cite` paper maps to at least one section
- every working or core paper maps to at least one section
- every table and figure has source evidence
- the figure count satisfies the review-size budget or the exception is recorded
- every planned figure is marked for PlotEnhance before generation
- excluded and unresolved records have explicit reasons
- `CITATION_NETWORK_STATUS` is `COMPLETED` unless a justified `NOT_APPLICABLE` is recorded
- downstream drafting has an explicit citation policy and knows what it may and may not cite
- compatibility files, if present, are derived rather than independent fact sources

## Final Output

Return a concise handoff block:

```text
FRAME_STATUS: APPROVED | REPLAN_REQUIRED | BLOCKED
WORKSPACE: <name>
LANGUAGE: <language>
ARTICLE_TYPE: <type>
STYLE_BASELINE: <style>
REVIEW_SCOPE_PROFILE: <scope>
TRIALS_STATUS: COMPLETED | NOT_APPLICABLE | BLOCKED
CITATION_NETWORK_STATUS: COMPLETED | NOT_APPLICABLE | BLOCKED
VALID_REFERENCE_COUNT: <n citable references>
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
NEXT_ACTION: ready_for_manuscript_drafting | run_targeted_acquisition | return_to_user
```

If `FRAME_STATUS` is not `APPROVED`, do not permit downstream writing.
