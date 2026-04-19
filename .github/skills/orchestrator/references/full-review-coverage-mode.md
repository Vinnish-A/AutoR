# Full-Review Coverage-First Mode

Use this mode when the user wants a `full review`, `large review`, `comprehensive review`, or otherwise explicitly values **coverage** and field-level completeness rather than a compact, highly selective mini-review.

## Core policy

For a full review, the workflow must follow this order:

1. Build the **universe corpus** first.
2. Map that corpus onto the review framework.
3. Only then derive the **core analytical corpus** and the later **writing nucleus**.

Do **not** jump straight from a topic to an aggressively filtered “retained set”.

## Tooling sequence

If the current environment exposes literature-landscape MCP tools, use them before download:

- `estimate_subfield_scope`: estimate the rough field size
- `analyze_topic_trends`: identify acceleration years and branch timing
- `measure_review_saturation`: judge whether the space is sparse or already crowded with reviews
- `rank_seminal_papers`: identify field anchors
- `retrieve_topic_literature`: generate PubMed-first candidate sets
- `resolve_literature_identifiers`: normalize PMIDs / DOIs / titles
- `get_citation_neighborhood`: expand around anchor papers

Then use the Records-backed acquisition workflow to retrieve metadata, download PDFs, and ingest them into autor.

## Query-matrix rule

Do not rely on one broad query string. Build a query matrix across at least four axes:

1. **Platform axis**
   - `CAR-T`
   - `CAAR-T`
   - `CAR-Treg` / `engineered Treg`
   - `CAR-NK`
   - `CAR-M`
   - `in vivo CAR`
   - `allogeneic`
   - `iPSC`
2. **Disease axis**
   - the major autoimmune-disease buckets relevant to the topic
   - include both headline diseases and smaller but genuinely in-scope diseases
3. **Translational axis**
   - `toxicity`
   - `conditioning`
   - `manufacturing`
   - `persistence`
   - `relapse`
   - `immune reset`
   - `organ remodeling`
4. **Adjacent comparator axis**
   - near-neighbor non-autoimmune CAR literature only when needed to explain platform behavior, toxicity logic, manufacturing constraints, or product-form tradeoffs

## Framework-preservation rule

If the user supplies a framework, logical axes, supporting pillars, or an adjustable outline, do not treat it as disposable brainstorming text.

Instead:

1. preserve the framework as a first-class planning input
2. test each unit against the expanded evidence base
3. record whether each unit is kept, merged, split, renamed, repositioned, deferred as evidence-thin, or dropped as unsupported
4. carry surviving units forward into the final review architecture

The final plan should not simply output a new outline. It should also explain what happened to the user's original framework.

## Corpus layers

Maintain at least three explicit layers:

- `universe corpus`
  - all directly in-scope papers after deduplication, retraction filtering, and off-scope removal
- `working corpus`
  - the papers actually downloaded, ingested, and section-mapped
- `core analytical corpus`
  - the papers that carry the main claims, controversies, mechanistic comparisons, and clinical translation logic

For a full review, do **not** confuse the core analytical corpus with the whole field.

## Exclusion policy in full-review mode

Before the universe corpus is built, exclude only:

- exact duplicates
- retracted papers
- clearly off-scope records
- records that remain unusable after identifier normalization

Do **not** remove directly relevant papers merely because they are:

- not yet highly cited
- in a lower-impact journal
- methodologically narrow but still part of the field
- useful mainly for breadth rather than for the final core argument

Those papers may later move out of the **core analytical corpus**, but they should first be counted and mapped.

## Required artifacts

When full-review mode is active, the planning layer should leave behind:

- `review-plan.md`
- `paper-classification.md`
- `section-evidence.md`
- `table-plan.md`
- `execution-tasks.md`
- `download-report.md` if downloading occurred
- and, when possible, a searchable record of the acquisition boundary such as:
  - `query-matrix.md`
  - `corpus-ledger.md`
  - `search-scope.md`

If the user supplied a heavy framework process, the final artifacts should also preserve the requested choreography:

- staged planning outputs
- fixed artifact names when feasible
- explicit exclusion logic
- explicit trial-layer handling
- a machine-readable handoff block

## English prompt template

```text
You are running the Coverage-First Framework Process for a full review article. Your job is limited to Orchestrator + Plan + Trials. Do not draft manuscript prose.

Workspace: "<WS>"
Review title: "<TITLE>"
Language: English
Article type: Review
Style baseline: Nature Reviews / Springer Nature Reviews
Review scope profile: full_review

Primary objective:
Build a field-level, coverage-first evidence base for this topic before narrowing to a core analytical set. This is a large review, so completeness and citation breadth matter in addition to judgment quality.

User framework:
<PASTE THE USER'S AXES / PILLARS / OUTLINE HERE>

Framework handling rule:
- Do not silently discard the user-supplied framework.
- Audit each framework unit against the evidence.
- Record whether each unit is kept, merged, split, renamed, repositioned, deferred as evidence-thin, or dropped as unsupported.
- Preserve the surviving framework logic inside the final outline and planning artifacts.

Coverage policy:
1. First build a universe corpus of all directly in-scope papers from external databases.
2. Only after the universe corpus is mapped may you derive a core analytical corpus and later writing nucleus.
3. Do not use low-impact, non-essential, or not-core-enough filters to shrink the field before the universe corpus exists.
4. For directly relevant papers, exclude only duplicates, retractions, clearly off-scope records, and unresolved unusable records.

Required tooling sequence:
1. Use literature-landscape MCP tools when available to estimate subfield size, recent growth, review saturation, seminal papers, identifier normalization, and citation neighborhoods.
2. Build an explicit query matrix across platform, disease, translational, and adjacent-comparator axes.
3. Use the autodownload workflow / Records service to retrieve metadata, download PDFs, and ingest them into autor.
4. Re-run planning after ingestion and revise the framework against the expanded evidence base.
5. Run the trials layer if the topic has clinical relevance.
6. If any directly relevant paper enters a pending state, resolve it before approval. Duplicate-DOI items may be discarded, but missing-DOI items must be normalized and completed rather than silently dropped.
7. If the workflow explicitly uses subagents for verification or DOI/full-text resolution, use GPT-5.4 with xhigh reasoning.

Corpus requirements:
- Universe corpus: all directly in-scope papers after deduplication and retraction/off-scope filtering
- Working corpus: downloaded and ingested papers mapped to sections
- Core analytical corpus: the subset that anchors the main claims and controversies

Planning requirements:
- Ensure the framework covers the major branches of engineered cell therapy in autoimmune disease, not only the most famous clinical CAR-T papers.
- Ensure the plan reflects both breadth and structure: direct autoimmune engineered-cell papers first, then selectively add adjacent non-autoimmune CAR literature only where it informs platform logic, toxicity, manufacturing, persistence, or organ-remodeling concepts.
- Do not let early quality filtering erase legitimate branches of the field.

Deliverables:
- workspace/<WS>/review-plan.md
- workspace/<WS>/paper-classification.md
- workspace/<WS>/section-evidence.md
- workspace/<WS>/table-plan.md
- workspace/<WS>/execution-tasks.md
- workspace/<WS>/trials/<query-slug>/trials-summary.md if clinically relevant
- workspace/<WS>/download-report.md if download was conducted
- workspace/<WS>/query-matrix.md and/or workspace/<WS>/corpus-ledger.md whenever coverage checking was performed

Required planning choreography:
1. Diagnose the workspace and the current evidence boundary.
2. Run coverage-first search and identify missing landmark papers, missing branches, missing recent developments, and missing trial evidence.
3. Retrieve missing literature, wait for ingestion, and re-run planning. No fallback.
4. Run the trials layer if clinically relevant and keep it as a parallel evidence layer.
5. Build or update all planning artifacts in staged order.
6. Launch an independent verification subagent before approval.

Required planning content:
- review-plan.md must include:
  - revised outline
  - framework preservation / revision audit
  - section roles and core claims
  - structural revision reasons
  - coverage / recency / representativeness judgment
  - evidence-thin areas
  - trial-evidence integration notes
  - writing order and dependencies
- paper-classification.md must include:
  - retained literature by section
  - excluded literature with reasons
  - explicit note that every retained paper maps to at least one body section
- section-evidence.md must include:
  - section-wise L3 evidence
  - relevant trial evidence where applicable
- table-plan.md must include:
  - at least 3 planned tables
  - at least 1 trial-aware table if trials are relevant
- execution-tasks.md must include:
  - task cards with objective, evidence input, dependencies, expected output, constraints, acceptance criteria
- download-report.md must include:
  - search scope
  - retrieved PMIDs / identifiers
  - approximate field size
  - download success / failure / no-full-text status

Final output contract:
Return only a machine-readable handoff block:

FRAME_STATUS: APPROVED | REPLAN_REQUIRED | BLOCKED
WORKSPACE: <WS>
LANGUAGE: ENGLISH
ARTICLE_TYPE: REVIEW
STYLE_BASELINE: NATURE_REVIEWS
REVIEW_SCOPE_PROFILE: full_review
TRIALS_STATUS: COMPLETED | NOT_APPLICABLE | BLOCKED
CORE_HYPOTHESIS: <1-2 sentences>
UNIVERSE_CORPUS_COUNT: <n>
WORKING_CORPUS_COUNT: <n>
CORE_ANALYTICAL_CORPUS_COUNT: <n>
HANDOFF_FILES:
- workspace/<WS>/review-plan.md
- workspace/<WS>/paper-classification.md
- workspace/<WS>/section-evidence.md
- workspace/<WS>/table-plan.md
- workspace/<WS>/execution-tasks.md
- workspace/<WS>/trials/<query-slug>/trials-summary.md if applicable
- workspace/<WS>/download-report.md if applicable
- workspace/<WS>/query-matrix.md if applicable
- workspace/<WS>/corpus-ledger.md if applicable
OPEN_GAPS:
- <NONE or explicit list>
```
