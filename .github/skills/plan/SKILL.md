---
name: plan
description: Plan a literature review before drafting. Revises the section outline in a Springer Nature Reviews style, classifies workspace papers by heading, and designs fixed-structure tasks plus comparison/synthesis tables. Use when the user wants to prepare a review article before writing.
---

# Review Planning Before Drafting

Before formally starting a literature review, first revise the structure, classify the evidence, design the tables, and identify risks so you can produce an executable writing blueprint.

**Structural design baseline**: By default, use the **Springer Nature Reviews style** as the reference for title hierarchy, section pacing, review narrative structure, and table placement. Unless the user explicitly specifies another target journal/style, do not build the outline in an ad hoc “write whatever comes to mind” way.

The focus of this skill is not to write the main text directly, but to answer four prerequisite questions:

1. Is the section/subheading structure provided by the user reasonable? Which parts need to be revised based on reasoning and evidence?
2. Which section should each paper in the current workspace go into? Which papers are core evidence, which are supplementary, and which review articles should be retained as framing anchors?
3. What tables should be designed for the review? What should each table compare, how should it compare it, and which papers should go into it?
4. Before formal writing begins, what scope, evidence, and structural issues still need to be filled in?

## Prerequisites

- The user must specify a **workspace** (`--ws NAME`).
- Ideally, the user should also provide an **initial heading structure**. If they do not yet have one, first propose a candidate structure based on the papers in the workspace, then move into the revision workflow.
- Write outputs into the `workspace/<name>/` directory.
- By default, treat the **Springer Nature Reviews style** as the preferred reference framework; if the user later wants to target another journal, you can make a second round of adjustments on top of this baseline.
- Treat the local knowledge base / total library as **reference-only**. It is useful for local orientation, but it is not sufficient to prove that the literature is complete for a field or subtopic.
- When judging whether the literature is complete enough, rely on **Records-service external database retrieval and metadata**, not only on what already exists in the local library.
- If the user specifies `full_review`, `large review`, or otherwise signals that coverage breadth is essential, do not let early pruning collapse the field into a tiny “best papers only” set. Planning must preserve a visible coverage layer in addition to the later core analytical layer.

## Execution logic

### 1. Clarify the planning task

First confirm the following information:

- **Review type**: standalone review article, a literature review chapter in a thesis, a project report, or the Related Work section of a paper
- **Review scope profile**: `full_review`, `mini_review`, `focused_review`, or equivalent user wording
- **Language**: Chinese / English
- **User-provided framework / logical axes / supporting pillars**: which conceptual units must be preserved and which may be revised
- **User-provided subheadings**: which are non-negotiable and which may be adjusted
- **Target audience / publication target**: determines structural depth and table granularity
- **Whether to emphasize a systematic-review style**: if yes, later steps should record inclusion/exclusion logic and comparison criteria more strictly
- **Whether deviation from Springer Nature Reviews style is allowed**: by default it is not; if the user specifies another journal template, explain the differences
- **Whether the user supplied a fixed execution choreography**: for example `Orchestrator + Plan + Trials only`, fixed artifacts, staged output rules, exclusion rules, or a machine-readable handoff contract

Interpret the scope profiles as follows:

- `full_review`: coverage-first; first map the field broadly, then derive the core analytical corpus
- `mini_review`: representative rather than exhaustive; a smaller but still defensible corpus is acceptable
- `focused_review`: exhaustive within the narrowed boundary; depth matters more than breadth outside the scope

### 2. Revise the heading structure using both reasoning and evidence, with Springer Nature Reviews as the reference style

First perform a global scan of the workspace:

```bash
autor ws show <name>                    # paper list
autor topics                             # topic clusters (if already modeled)
autor show <dir_name> --level 2          # read abstracts paper by paper
```

This initial local scan is for orientation only. If a heading appears thin, missing, or suspiciously one-sided, verify coverage against external databases through the Records service metadata retrieval rather than concluding from the local library alone.

Evaluate each user-provided heading one by one. Do not change the structure based on intuition alone; you must explain the **evidence basis**:

If the user supplied a broader framework such as logical axes, supporting pillars, or a theory-driven scaffold, treat that framework as an explicit design prior rather than disposable prompt text. Audit each unit and record one of:

- **Keep**
- **Merge**
- **Split**
- **Rename**
- **Reposition**
- **Defer as evidence-thin**
- **Drop as unsupported**

It is recommended to leave a traceable framework-audit table:

| User framework unit | Action | Where carried forward | Evidence status | Reason |
|--------|------|--------|----------|----------|
| Axis / pillar / proposed section | Keep / Merge / Split / Rename / Reposition / Defer / Drop | Final section or note | Strong / medium / thin | Evidence-based explanation |

At the same time, use the common review-organizing logic of Springer Nature Reviews as the default framework for correcting the structure:

- **From the big question to subquestions**: begin by establishing field background, core concepts, and major points of controversy, then move into topic-specific discussion
- **Organize by theme/mechanism/question rather than simply listing year by year**: unless the user explicitly asks for a timeline-style review
- **Every main section should have a clear function**: define concepts, compare methods, explain mechanisms, synthesize controversies, or lead into future directions
- **Emphasize synthesis and critique within sections**: not “what paper A said, then what paper B said,” but organizing multiple studies into one argumentative unit
- **Reserve space for tables and figures**: at the structure-design stage, already consider which sections need comparison tables, evidence-summary tables, or mechanism diagrams
- **The ending should naturally lead into Outlook / Open questions**: the outline itself should leave a logical opening for later synthesis and future directions
- **Keep a controlled review layer**: besides primary studies, retain a small number of field-defining, near-neighbor, and section-local authoritative reviews so the manuscript can acknowledge prior syntheses and orient the reader

- Is there **enough literature** supporting this subheading? If it is backed by only 1–2 peripheral papers, it may need to be merged
- Are the **boundaries clear** between subheadings? Is there serious overlap or repetitive narration
- Is the **granularity balanced** across heading levels? Are some too broad while others are too narrow
- Does the order of the structure match the field’s usual logic: by problem, by method, by timeline, by controversy, or is it mixed together inconsistently
- Does it omit key themes, key methods, or key populations/experimental systems that recur repeatedly in the workspace
- Are there parts the user assumes are important, but for which the current evidence does not support a standalone section
- If a section looks sparse, is that because the field is actually sparse, or because the local library has not yet been expanded through external-database retrieval

For each subheading, choose one of the following actions:

- **Keep** (retain as-is)
- **Merge** (combine)
- **Split** (separate)
- **Rename** (retitle)
- **Reorder** (move)
- **Add** (introduce)
- **Drop / Demote** (remove or lower in prominence)

It is recommended to output a structure revision table:

| Original title | Action | New title | Evidence basis | Reason for revision |
|--------|------|--------|----------|----------|
| User's original subheading | Merge | New merged title | Representative papers supporting this part | Resolve overlap / insufficient evidence / imbalanced granularity |

### 3. Read through the current workspace and classify papers by subheading

Perform a **full scan** of the papers in the workspace, completing at least L2 (abstract) reading; for papers with unclear classification or high importance, continue to L3/L4:

```bash
autor ws show <name>
autor show <dir_name> --level 2          # full-pass abstract scan
autor show <dir_name> --level 3          # read conclusions when classification is ambiguous
autor show <dir_name> --level 4          # read the full text for core papers
```

The goal of classification is not to discard papers as quickly as possible, but to build a high-coverage classification result for **all scanned literature in the workspace**. As long as a paper’s **conclusion, method, subject, data condition, controversy, or limitation** is relevant to a heading, it should, as much as possible, be assigned to at least one category.

However, workspace coverage and total-library coverage are not the same thing. If an important section, controversy, or canonical paper seems absent, perform an external metadata check through the Records service before deciding that the field truly lacks evidence.

When classifying, do not simply “slot papers under headings”; instead, build an **evidence classification matrix**. At minimum, it is recommended to record the following fields:

- `primary_section`: main assigned section
- `related_sections`: all other relevant sections besides the primary assignment (can be multiple)
- `study_type`: experimental study / computational study / clinical study / methods paper / narrative review / systematic review / meta-analysis / guideline / data paper
- `model_or_population`: object, sample, population, model system
- `method_or_intervention`: core method, technical route, treatment condition
- `dataset_or_condition`: data source, experimental scenario, boundary condition
- `key_metrics`: evaluation metrics or key endpoints
- `main_finding`: main conclusion
- `limitation`: main limitation
- `evidence_strength`: strong / medium / weak (judged comprehensively based on sample size, study design, reproducibility, and adequacy of comparisons)

It is recommended to organize the classification output from a **section-centric perspective**, rather than forcing a deduplicated perspective in which “each paper appears only once.” When necessary, the same paper may **appear repeatedly** under multiple headings; do not sacrifice relevance merely for the sake of deduplication.

Reviews require a separate judgment layer. Do not treat all reviews as expendable background. Distinguish at least these roles when relevant:

- `field_anchor_review`: a broad, authoritative review from the parent field used to define the big question, historical positioning, or consensus baseline
- `near_neighbor_review`: a review from the most relevant adjacent subfield used to clarify boundaries, overlap, or what this manuscript is and is not trying to cover
- `section_anchor_review`: a section-local authoritative review used to acknowledge prior synthesis, stabilize terminology, or frame a controversy before moving into primary evidence

Retain such reviews sparingly and label their role explicitly. They should help the manuscript position itself in the field, not replace primary evidence where direct claims depend on original studies.

Pay special attention to the following cases during classification:

- **A paper may belong to multiple subheadings**: allow it to appear repeatedly in multiple categories; specify its primary assignment and other relevant assignments, but do not omit its relevant conclusions under other headings just because it has already been assigned once
- **Classification remains difficult after completing the L2 scan**: continue by escalating to L3; if it is still uncertain, then inspect L4. Only after completing this cascading scan, and still being unable to show a substantial connection to any heading, may the paper be left unclassified for the time being
- **Aim for full coverage as much as possible**: if a paper’s conclusions are relevant to a heading, try to place it into at least one category; the default goal is for every scanned paper in the workspace to appear in at least one category
- **Some papers do not fit any existing subheading**: this usually means the structure itself still needs revision
- **A heading contains many papers but the viewpoints are highly repetitive**: further split it into subcategories or keep only the core evidence
- **A heading contains few papers but addresses an important question**: label it as an “evidence-thin area”; keep the body coverage controlled and note that more literature needs to be added

#### Rules for retaining / removing literature after classification

Plan may retain/remove items from the **writing corpus for this specific review** based on classification results, relevance, and redundancy. But here, “remove” by default only means **excluding them from the body-writing corpus of this review**, not physically deleting them from the workspace.

Retention/removal rules must follow this priority:

1. **Explicit user instructions take priority**
2. **Only if the user has not specified anything may Plan decide on its own**

For `full_review`, use a layered retention policy instead of a single early retained set:

- `coverage corpus`: all directly relevant papers that define the field boundary
- `core analytical corpus`: the subset that anchors the review's main mechanistic, translational, and clinical arguments
- `writing nucleus`: the papers that each drafted section must actively use

In a full review, a paper may fall out of the `core analytical corpus` without being erased from the `coverage corpus`.

If the user has given pruning constraints, they must be followed strictly. For example:

- The user says “you must not remove more than 1/4”
- If the current total number of papers under evaluation is 100, then at most 25 papers may be removed

If the user gives a proportional upper bound, convert it to an integer according to the principle of **not exceeding the upper bound**; in other words, the maximum removable count should be rounded down.

Possible forms of user-provided constraints include:

- The maximum number of papers that may be removed
- The maximum proportion that may be removed
- The minimum number of papers that must be retained
- A certain category of papers may not be removed
- Highly cited papers / key papers must be retained

If the user **has not explicitly specified** any such constraint, Plan may decide the pruning extent on its own based on the current review objective, but it must satisfy two conditions:

- Explicitly record the total number of papers, retained count, removed count, and removal ratio
- Write down the reason for every removed paper, for example: peripherally relevant, highly redundant information, not directly relevant to the current review question, or clearly lower evidence quality without being a key counterexample

For `full_review`, do not remove a directly relevant paper from the coverage layer merely because it is low-impact or not central enough. Such papers may be downgraded from `core analytical corpus` to `coverage corpus`, but the field map should still show that they exist.

Regardless of whether the user set limits, **every paper retained in the final set must be assigned to at least one body section and must be cited at least once in the subsequent formal draft**. In other words, the retained set is the minimum citation-coverage set for subsequent `/write`.

By default, do **not** prune the writing corpus down to primary studies only. Unless the user explicitly requests otherwise, retain a controlled review layer:

- `1-3` field-anchor reviews for the introduction or framing sections
- `1-2` near-neighbor reviews for scope-setting, comparison, or boundary sections
- `0-2` section-anchor reviews for each major section when they are clearly the most relevant and authoritative prior synthesis

A retained review article should justify its place by doing at least one of the following:

- defining the field-level problem or consensus baseline
- marking a major shift in the field
- clarifying the boundary between this review and nearby review traditions
- summarizing a controversy that later sections will adjudicate with primary evidence
- serving as an explicit acknowledgment of a major prior synthesis that readers in the field would reasonably expect to see cited

If a review is retained, record both:

- why it is being kept
- what it is **not** allowed to substitute for in the later manuscript

For example, a retained review may anchor the introduction, but it should not replace direct mechanistic or causal evidence when those claims depend on original studies.

When a key paper is absent from the local library but clearly present in external-database retrieval, do not quietly proceed without it. Acquire it first through the Records service pipeline when feasible, then classify it with the rest of the evidence.

### 4. Extract at least L3-level conclusion evidence by category

Once classification is complete, do not jump immediately to writing or table construction. You should also build a directly reusable evidence layer for **every category / section**:

- For every paper included in that category, extract at least **L3 (conclusion)**-level information
- If L3 is missing, too short, or insufficient to support the category judgment, go back to L4 and supplement with relevant passages, but the output should still be organized as “conclusion evidence for this category”
- If the paper is not in the local library, or if the existing local record has no usable L3 conclusion, obtain the paper through the Records service download + processing workflow first whenever possible
- If full-text processing still fails to yield a usable L3 layer, expose the full text to a dedicated reading subagent and require it to produce a structured note covering:
  - what the article is mainly about
  - what conclusions the article supports
  - any quantitative results or boundary conditions that matter for the section
  - any limitations that change how strongly the article should be used
- Since the same paper may appear in multiple categories, its extracted conclusions may also appear repeatedly under multiple categories; when necessary, emphasize different relevant conclusions for different categories

During extraction, it is recommended to record at least the following for each evidence item:

- `paper`
- `category / section`
- `why_relevant`
- `l3_conclusion`: at least one conclusion relevant to this category
- `quantitative_result`: if there is a quantifiable conclusion, extract it where possible
- `limitation_or_boundary`
- `table_reuse_hint`: which table this conclusion would fit into
- `evidence_role`: direct evidence / framing review / consensus review / cautionary review
- `evidence_origin`: extracted_l3 / direct_fulltext_read / subagent_fulltext_summary

The purpose of this layer is that, when writing later, you do not need to return to the full text to figure out “what exactly does this paper support”; and when making tables later, you can also directly pull information from this category-organized conclusion layer.

### 5. Design review tables (at least 3)

A mature review article should have at least **3 tables** designed in advance. These tables should not be mere “decorative lists”; they must serve comparison and synthesis.

#### Table 1: Study design and conclusion comparison table (required)

Purpose: present the experimental design details, study subjects, and conclusions of different studies for side-by-side comparison.

Recommended fields:

| Authors | Year | Study type | Sample/model | Data/condition | Method/intervention | Metrics/endpoints | Main findings | Limitations |
|---------|------|------------|--------------|----------------|---------------------|-------------------|---------------|-------------|

Applicable scenarios:

- You need to compare differences in experimental design study by study
- Findings from different studies appear contradictory, and you first need to return to design conditions to explain them
- The user wants to highlight “why these studies cannot simply be compared directly”

#### Table 2: Quantitative summary table of technical characteristics (required)

Purpose: in a systematic-review style, quantitatively compare technical characteristics, method composition, data scale, performance metrics, or engineering features.

Recommended fields (choose as appropriate for the field):

| Method family | Core idea | Input/data modality | Scale | Benchmark/task | Quantitative result | Efficiency/cost | Code/data available | Notes |
|---------------|-----------|---------------------|-------|----------------|---------------------|-----------------|--------------------|-------|

Applicable scenarios:

- The review focuses on method comparison rather than phenomenon description
- The user wants to answer “which types of technical routes are suitable for which problems”
- You need to consolidate scattered results into a comparable technical lineage

#### Table 3: Evidence consistency / disagreement / gap table (recommended default third table)

Purpose: put supporting findings, conflicting findings, and unresolved issues into a single table to help the body develop a critical narrative.

Recommended fields:

| Subtopic | Supporting studies | Conflicting studies | Boundary conditions | Current consensus | Remaining gap |
|----------|--------------------|---------------------|---------------------|------------------|---------------|

Applicable scenarios:

- Contradictory conclusions exist around the same question
- You need to lead research gaps naturally into the ending of the review
- The user wants to write a “synthetic + critical” review rather than a list-style summary

#### Optional additional tables (add as needed for the field)

- **Dataset / benchmark comparison table**
- **Method-evolution timeline table**
- **Research subject / parameter-range coverage table**
- **Study quality / risk-of-bias table**
- **Clinical endpoint / engineering metric summary table**

#### Table design rules

- Keep row granularity consistent: choose either “single study” or “method family,” and do not mix them
- Keep comparison criteria consistent: unify units, metrics, and data ranges as much as possible
- For quantities that cannot be directly compared, explain them with explicit footnotes rather than forcing them into one column
- Mark missing information explicitly as `NR` / `NA`; do not leave blanks by default
- Define in advance for every table: **purpose, included items, fields, sorting rule, citation sources**
- At least **1 table** should emphasize study design/experimental details, and at least **1 table** should emphasize the systematic summary of technical characteristics

### 6. Additional planning steps that should also be included

Beyond the three core tasks above, the following items should usually also be completed before formal writing:

#### (a) Scope boundaries and inclusion/exclusion criteria

- What question exactly does this review answer, and what question does it not answer?
- Which types of studies are included in the main body narrative, and which appear only as background or are excluded entirely?
- If this is a systematic review, search terms, inclusion/exclusion criteria, and screening logic should also be defined in advance

#### (b) Terminology unification and synonym cleanup

- The same concept may be named differently across papers
- Standardize terminology before formal writing so that later headings, tables, and body text do not use inconsistent names

#### (c) Identification of key papers and anchor evidence

- Which papers are foundational works, representative works, highly cited works, or the latest breakthroughs
- Which papers, despite not being highly cited, are methodologically rigorous or have higher-quality data and therefore deserve to become primary evidence in the body

#### (d) Evidence-thin areas and reminders to add literature

- Which subheadings currently lack sufficient evidence in the workspace
- Which important controversies are missing key papers and require additional searching in external databases rather than only the local library:
  ```bash
  autor ws search <name> "<keyword>"
  autor usearch "<keyword>"
  ```
- When completeness matters, record what was checked through the Records service metadata retrieval and what remains absent even after external search

#### (e) Claim–evidence mapping

- Pre-list the core claim each section is meant to answer
- Assign supporting papers, counterexample papers, and limiting conditions to each claim
- Prevent situations in which a judgment is written first and then no supporting evidence can be found later

#### (f) Coordination between figures/tables and narrative

- Decide which section each table is meant to support
- Which places may also need figures (timelines, mechanism diagrams, evidence maps, topic-relation figures)
- Think through the division of labor between tables, figures, and the main text in advance to avoid redundant information

#### (g) Section weighting and writing order

- Which sections are the backbone, and which sections should serve only as brief background
- Writing the most evidence-solid parts first, then the more controversial and gap-heavy parts, can reduce later rework

### 7. Deliverables (fixed structure)

At the end of Plan, do not output only a loose outline. It is recommended to generate at least the following items, all saved to `workspace/<name>/`:

- `review-plan.md`: revised outline, reasons for structural adjustments, the core claim of each section, and the writing order
- `paper-classification.md`: a paper-classification matrix organized by section, allowing the same paper to appear repeatedly in multiple categories; only papers that truly cannot be classified should go into a separate `Unclassified papers` subsection with an explanation of why
- `section-evidence.md`: evidence summaries organized by category / section; for every paper within each category, organize at least L3-level conclusions so they can be reused directly for later drafting and table construction
- `table-plan.md`: design plans for at least 3 tables (purpose, fields, included papers, sorting rules)
- `execution-tasks.md`: list **all follow-up writing and supplementary tasks** using a fixed structure

When external completeness checking was needed, also record where that judgment came from: local reference only, Records service metadata retrieval, or downloaded full-text evidence. Put this note in `review-plan.md` or `search-gaps.md`.

If the user supplied a heavy framework process, the plan should also preserve the user's choreography. That means the artifact set and ordering should not be improvised away. Keep the user-requested staging and handoff discipline unless there is a concrete reason to revise it.

If the workspace is large or the goal is a high-quality systematic review, you may additionally provide:

- `evidence-map.md`: claim–evidence–counterevidence mapping
- `search-gaps.md`: suggested keywords and missing directions for supplementary search
- `query-matrix.md`: the external query matrix used to test field coverage
- `corpus-ledger.md`: the universe/working/core corpus counts and status log

#### Write Plan content in stages

Plan content **must not be completely written and output all at once**. The preceding reasoning and deliverables should be written out in stages so the user can inspect them progressively and so large-scale rework can be reduced later.

It is recommended to split the output into at least 4 rounds in the following order:

1. **Round 1**: first write the structure revision results
   - final outline (first version)
   - reasons for structural revision
   - structural issues the user should notice immediately
2. **Round 2**: then write the paper-classification results
   - `paper-classification.md`
   - highly ambiguous literature
   - `Unclassified papers`
3. **Round 3**: then write the category-organized evidence and table plans
   - `section-evidence.md`
   - `table-plan.md`
4. **Round 4**: finally write the task cards, dependencies, and overall handoff
   - `execution-tasks.md`
   - writing order and dependencies
   - handoff instructions for `/write`

If any round is still too long, continue splitting it by section or by task group, rather than dumping all results at once.

#### `review-plan.md` fixed structure

It is recommended that `review-plan.md` use the following structure consistently:

1. **Review task brief**
   - workspace
   - review topic
   - target audience / target journal
   - review scope profile
   - language
   - user framework summary
   - structural style baseline (default: Springer Nature Reviews)
   - retained review-layer policy
   - corpus-layer policy
   - execution choreography summary
   - external coverage-check status
2. **Final outline (revised)**
   - provide the final chapter/subheading tree
   - mark changes relative to the user’s original outline
3. **Reasons for structural revision**
   - explain Keep / Merge / Split / Rename / Reorder / Add / Drop by heading
   - provide the evidence basis for every item
4. **Framework preservation / revision audit**
   - show how the user-provided framework units were kept, merged, split, repositioned, deferred, or dropped
5. **Section Cards**
   - expand every main section using the same template
6. **Table plan**
   - at least 3 tables
   - the purpose, fields, included items, sorting rules, and corresponding section of each table
7. **Evidence-thin areas and supplementary search suggestions**
8. **Writing order and dependencies**

#### `paper-classification.md` fixed structure

It is recommended that `paper-classification.md` contain at least the following parts:

1. **Explanation of classification principles**
     - which scan level has been completed (L2 / L3 / L4)
     - review scope profile
     - whether duplicate classification is allowed (default: yes)
     - classification coverage target (default: cover all scanned literature as much as possible)
     - corpus-layer policy if full-review mode is active
     - whether external-database completeness checking was performed
2. **Retention / removal rules and statistics**
    - total number of papers evaluated
    - user-provided pruning constraints (if any)
    - maximum allowed removals / minimum required retained count
    - actual retained count
    - actual removed count
    - removal ratio
    - reasons for adopting this retention plan
3. **Retained literature list classified by section**
    - list relevant papers under each section
    - the same paper may appear repeatedly under multiple sections
    - each entry should at least explain why it is relevant to that section
    - for every retained paper, indicate at least which body section it will be cited in
4. **Retained review layer**
    - field-anchor reviews
    - near-neighbor reviews
    - section-anchor reviews
    - why each one is retained
    - where each one will be cited
    - what each one is not allowed to replace
5. **Removed literature**
    - list removed papers one by one
    - explain the reason for removal
    - check whether the number removed complies with the user’s limit
6. **Highly ambiguous literature**
    - record papers that can fit multiple headings but whose boundaries are not fully stable
7. **Unclassified papers**
    - retain here only papers that still cannot be assigned to any heading after completing L2 and escalating to L3/L4 as needed
    - explain for every unclassified paper why classification was abandoned

#### `section-evidence.md` fixed structure

It is recommended that `section-evidence.md` be organized by **section / category**, and that each category contain at least:

1. **Category summary**
   - what question this category is meant to answer
   - how many papers this category contains
   - the overall tendency of the evidence (support / disagreement / gap)
2. **Paper-level evidence entries**
   - `Paper`
   - `Why in this category`
   - `L3 conclusion`
   - `Quantitative result` (if any)
   - `Limitation / boundary`
   - `Potential table usage`
   - `Evidence role`
   - `Evidence origin`

If the same paper appears repeatedly in multiple categories, it should be allowed to extract the conclusion most relevant to that category separately under each category, rather than keeping only one generic summary.

#### Fixed template for section cards

It is recommended that every section in `review-plan.md` be written using the following template:

- `Section title`: the title of the section
- `Section role`: the function of this section in the overall review
- `Key question`: the core question this section is meant to answer
- `Scope / boundary`: what is included and what is not
- `Core papers`: the main evidence papers
- `Anchor reviews / framing reviews`: the review articles kept on purpose for positioning, acknowledgment, or consensus framing
- `Conflicting / cautionary papers`: conflicting evidence or papers that require cautious interpretation
- `Planned tables / figures`: which tables/figures this section uses
- `Expected takeaway`: what conclusion the reader should take away after finishing this section

#### `execution-tasks.md` fixed structure

At the end of Plan, write **all follow-up tasks** as fixed-format task cards. Task types may include section drafting, table construction, supplementary searching, terminology unification, controversy checking, citation strengthening, etc.

Use the following template for every task:

```md
## Task <ID>: <task name>
- Type:
- Target section / table:
- Objective:
- Evidence input:
- Dependencies:
- Expected output:
- Constraints:
- Acceptance criteria:
```

Among them:

- `Constraints` should specify at minimum whether Springer Nature Reviews style must be followed, whether a particular table must be reused, and whether only a specific evidence set may be used
- `Acceptance criteria` should be written as executable standards so that later body writing does not turn into “write until it feels done”

### 8. Check the generated content

After all Plan deliverables have been generated, you must perform one **explicit check**. Do not generate them and hand them directly to `/write` without review.

At minimum, check the following:

1. **Structure check**
   - Does the final outline still conform to the Springer Nature Reviews style
   - Do the headings match the available evidence
   - Are there still serious overlaps, imbalanced granularity, or omitted themes
2. **Classification check**
   - Have the scanned papers in the workspace, as much as possible, all been assigned to at least one category
   - Are unclassified papers truly impossible to classify, with sufficient justification
   - Have multiply classified papers retained the necessary place under all relevant sections
   - Has a deliberate review layer been retained, rather than accidentally pruning away all major prior syntheses
   - In `full_review` mode, is the coverage layer still visibly broader than the core analytical layer
3. **Evidence check**
   - Has every category accumulated at least L3-level conclusion evidence
   - Are the evidence entries sufficient to support later body writing and tables
   - Are retained review articles labeled clearly as framing/consensus inputs rather than direct substitutes for primary evidence
   - If L3 was unavailable, was the gap resolved through full-text reading or a full-text-reading subagent rather than left vague
4. **Table check**
   - Have at least 3 tables been designed
   - Is every table tied to a clear section and a clear purpose
5. **Task check**
   - Does `execution-tasks.md` cover the tasks needed for subsequent writing
   - Are dependencies and expected outputs clear
   - If the user supplied a fixed choreography, was it preserved rather than silently replaced
6. **Staged-output check**
   - Has the content already been written out in stages rather than dumped all at once
   - If any round was too large, was it split further
7. **Pruning-constraint check**
   - If the user provided a pruning limit, does the actual number removed stay within that limit
   - If the user did not provide a limit, have pruning statistics and reasons been explicitly recorded
   - Has every retained paper already been mapped to at least one body section and at least one follow-up citation task
8. **Coverage-source check**
   - Were completeness judgments made against external database retrieval rather than local-library density alone
   - If a key paper was absent locally, was it fetched or at least explicitly logged as externally found but not yet processed
   - In `full_review` mode, was the field first mapped broadly before strong pruning decisions were made

Only after this review step passes should formal writing begin.

### 9. Handoff to formal writing

Once the user has confirmed the revised structure, classification results, category-organized L3 conclusion evidence, table plan, and fixed task list, switch to `/write` by default to begin formal body drafting.

If the user instead wants a more open-ended, exploratory review-writing workflow, `/literature-review` may also be used; but the **standard pipeline** should preferably be:

```text
/plan -> /write
```

The advantages of this are:

- The body draft is less likely to overturn the outline halfway through writing
- Every section has a clear evidence pool
- Every section already has at least an L3-level conclusion-evidence layer, so there is no need to re-search paper by paper while drafting
- If L3 extraction originally failed, the planning layer has already resolved it through direct full-text reading or a subagent-produced full-text summary
- Tables can be designed first, and the body can develop around tables and evidence instead of adding tables afterward
- `/write` can treat `review-plan.md`, `section-evidence.md`, and `execution-tasks.md` as a writing contract rather than improvising freely again

## Academic attitude

- Structural revision must be **evidence-based**, not changed just because it “looks nicer”
- Paper conclusions are the authors’ claims; when classifying and designing tables, pay attention to experimental conditions and limitations
- A highly cited paper should not automatically be placed in the most central position
- Authoritative review articles should not automatically displace primary evidence, but they should also not be stripped away reflexively if they are needed for framing, acknowledgment, or field positioning
- The total library is a convenience layer, not a completeness guarantee; completeness claims must come from external-database retrieval and the downstream acquisition pipeline
- If a critical paper has no usable L3 conclusion, do not hide behind missing structure; read the full text or assign the full text to a dedicated reading subagent
- If a heading lacks evidence in the current workspace, explicitly tell the user to add literature rather than force the section into the draft

## Examples

User says: "I already have a review outline. Don’t write the main text yet. Help me check whether the structure is reasonable, classify the papers in the workspace by section, and then design the tables."

→ Enter `/plan`: revise the structure, classify the papers, and output the table plan

User says: "I’m preparing to write a systematic review and want to first see which headings should be merged and which studies should go into the same comparison table."

→ Enter `/plan`: emphasize inclusion/exclusion criteria, quantitative technical-feature tables, and evidence-consistency tables
