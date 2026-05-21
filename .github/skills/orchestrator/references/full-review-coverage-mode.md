# Full-Review Coverage-First Mode

Use this reference when the user asks for a `full_review`, large review, comprehensive review, field map, or coverage-first planning process.

## Core Policy

For a full review, do the work in this order:

1. Build the universe corpus.
2. Map the universe onto the user framework and review scope.
3. Derive the working corpus.
4. Derive the core analytical corpus.
5. Only then approve writing.

Do not jump directly from a topic to a narrow retained set of famous papers.

## Canonical Outputs

Full-review planning must still use the current workspace contract:

```text
workspace/<WS>/references.bib
workspace/<WS>/reference-map.json
workspace/<WS>/review-plan.md
workspace/<WS>/evidence-ledger.md
workspace/<WS>/table-figure-plan.md
workspace/<WS>/acquisition-log.md
workspace/<WS>/sidecars/
```

`references.bib` citation keys are canonical. Store UUIDs, dir names, PMIDs, DOIs, corpus layers, and full-text status in `reference-map.json`.

Compatibility exports such as `query-matrix.md`, `corpus-ledger.md`, `paper-classification.md`, `section-evidence.md`, `table-plan.md`, and `execution-tasks.md` may be generated only when needed by legacy tools. They must be derived from the canonical files.

## Coverage Calibration

When available, use literature-landscape tools before or during external retrieval:

- `estimate_subfield_scope`
- `analyze_topic_trends`
- `measure_review_saturation`
- `rank_seminal_papers`
- `retrieve_topic_literature`
- `resolve_literature_identifiers`
- `get_citation_neighborhood`

If those tools are unavailable, use Records-service metadata retrieval and local autor checks. Do not certify completeness from local-library density alone.

## Query Matrix

For full reviews, build a query matrix across the dimensions that fit the topic. For engineered-cell or biomedical platform reviews, typical axes are:

- platform terms
- disease or indication terms
- translational terms
- adjacent comparator terms

Record the query matrix in `acquisition-log.md`.

For each query branch, keep:

- branch ID
- axis
- query or source logic
- objective
- direct or adjacent relevance
- outcome
- notes

## Corpus Layers

Maintain at least:

- `universe`: all directly in-scope records after deduplication, retraction filtering, and clear off-scope removal
- `working`: papers downloaded/ingested or otherwise usable and mapped to sections
- `core`: papers that carry main claims, comparisons, controversies, and translational logic

Additional useful statuses:

- `coverage_support`
- `review_layer`
- `excluded`
- `unresolved`

Do not remove directly relevant records from the universe only because they are low impact, narrow, recent, or not part of the core argument.

## Framework Preservation

If the user supplies a framework, preserve it as a design prior and audit every unit:

- keep
- merge
- split
- rename
- reposition
- defer as evidence-thin
- drop as unsupported

Record the audit in `review-plan.md`.

## Acquisition Rules

Use Records-backed `autodownload` for external acquisition. Do not use Playwright fallback.

Before downloading, screen metadata and build inclusion/exclusion decisions. After downloading, ingest PDFs into autor before using them as full evidence.

Record candidate flow, download status, ingest status, and unresolved records in `acquisition-log.md` and `reference-map.json`.

## Trial and Citation-Network Layers

Use `trials` if clinical-program evidence is relevant. Keep trial outputs under:

```text
workspace/<WS>/trials/<query-slug>/
```

Map retained trial IDs to sections in `reference-map.json` and `evidence-ledger.md`.

If citation-network mapping is used, store raw JSON under `sidecars/` and summarize lineages, branches, convergence, and weakly integrated directions in `acquisition-log.md` or `review-plan.md`.

## Full-Review Approval Gate

Before approving writing, verify:

- field-size and branch estimates were externally calibrated
- the universe corpus was built before aggressive pruning
- major branches and controversies are represented or explicitly marked thin
- every working/core citekey exists in `references.bib`
- every working/core citekey appears in `reference-map.json`
- every planned section and table/figure has evidence support
- unresolved full-text or identifier problems are visible

## Handoff

Use the standard `plan` / `orchestrator` handoff block:

```text
FRAME_STATUS: APPROVED | REPLAN_REQUIRED | BLOCKED
WORKSPACE: <WS>
REFERENCE_POLICY: references.bib citation keys are canonical
CORPUS_COUNTS:
- universe: <n>
- working: <n>
- core: <n>
- excluded: <n>
- unresolved: <n>
HANDOFF_FILES:
- workspace/<WS>/references.bib
- workspace/<WS>/reference-map.json
- workspace/<WS>/review-plan.md
- workspace/<WS>/evidence-ledger.md
- workspace/<WS>/table-figure-plan.md
- workspace/<WS>/acquisition-log.md if applicable
OPEN_GAPS:
- <NONE or explicit list>
NEXT_ACTION: run_write | run_targeted_acquisition | return_to_user
```
