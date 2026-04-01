---
name: write
description: Draft a fact-grounded review manuscript from the current workspace by strictly following the outputs of /plan, using humanized Springer Nature Reviews-style prose and DOCX-ready Markdown citations with CSL. Use this when the user wants the formal writing stage after planning.
---

# Formal Writing Based on the Plan

This skill is the **formal writing stage** after `/plan`. It is not for revisiting the outline or redoing classification; it turns the structure, evidence layers, table plan, and task cards finalized in `/plan` into actual review prose.

This skill has five hard constraints:

1. **Fact-grounded**: use only papers, evidence files, and retrieval artifacts that already exist in the current workspace
2. **Plan-grounded**: follow the structure and section tasks produced by `/plan` by default
3. **De-AI style**: the prose should follow the Humanize / `humanizer` principles and avoid obvious AI writing patterns
4. **Close to Springer Nature Reviews style**
5. **Use a DOCX-ready Markdown + CSL citation workflow**

## Prerequisites

The user must specify a **workspace** (`--ws NAME`).

Before drafting, you must check for and read the following `/plan` artifacts:

- `workspace/<name>/review-plan.md`
- `workspace/<name>/execution-tasks.md`
- `workspace/<name>/paper-classification.md`
- `workspace/<name>/section-evidence.md`
- `workspace/<name>/table-plan.md`

If these files are missing, go back to `/plan` first. Do not skip planning and jump straight into drafting.

## Where this skill fits

- `/plan`: set the structure, classify papers, design tables, and consolidate evidence
- `/write`: draft the formal review text from that fixed structure and evidence base
- `/literature-review`: more open-ended, exploratory review writing; if the user has already completed `/plan` and wants the draft to follow it strictly, prefer `/write`

## Workflow

### 1. Lock the fact boundary first

Claims, comparisons, controversy judgments, and summaries in the main text should by default come only from **real material inside the current workspace**:

- papers already in the workspace
- evidence-organizing files produced by `/plan`
- trial retrieval outputs under `workspace/<name>/trials/` (if present)

Do not cite papers outside the workspace just to patch a sentence, and do not fill factual gaps from common knowledge or model memory if those facts do not appear in the workspace.

If a claim lacks evidence in the current workspace:

- go back to `/plan` or `/search` first
- or explicitly mark it as `[CITATION NEEDED IN WORKSPACE]`

Never fabricate citations.

### 2. Follow the Plan structure strictly

Treat `review-plan.md` as the default **writing contract**:

- follow the final section order
- let each section answer only its own `Key question`
- draw the primary evidence for each section from the matching `Section Cards` and `section-evidence.md`
- place tables according to `table-plan.md`
- follow the writing priority and dependency order defined in `execution-tasks.md`
- **every paper retained in the final Plan** inside `paper-classification.md` must appear at least once in the main text; papers explicitly removed by the Plan do not need to be mentioned

There are only two valid reasons to deviate from the plan:

1. the user explicitly asks to change the structure
2. writing reveals a clear conflict between `/plan` and the evidence

If deviation is required, go back to `/plan`, revise it, and only then continue. Do not silently rewrite the draft around the plan.

### 3. Prepare the citation assets first: BibTeX + CSL + Markdown citations

#### 3.1 Export workspace references

First make sure the workspace has a BibTeX file:

```bash
autor ws export <name> -o workspace/<name>/references.bib
```

#### 3.2 Determine the CSL file

Choose the CSL in this order:

1. prefer `workspace/<name>/style.csl`
2. if that does not exist, look for any existing `*.csl` under `workspace/<name>/`
3. if none exists, **automatically fetch the default CSL**

Default CSL:

- **`nature.csl`**
- original source: `https://raw.githubusercontent.com/citation-style-language/styles/master/nature.csl`

Why:

- for Markdown/Pandoc workflows, `nature.csl` is the closest broadly usable style to the Springer Nature Reviews family

Recommended save path:

```text
workspace/<name>/csl/nature.csl
```

#### 3.3 The main text must use DOCX-ready Markdown citations

Do not use fake plain-text citations such as `(Author, Year)`. Use Pandoc / citeproc-compatible Markdown citations instead, for example:

- single citation: `[@smith2021]`
- multiple citations: `[@smith2021; @wang2023]`
- for narrative citations, write the author into the sentence and then attach the citation key

Recommended YAML header for the main Markdown file:

```yaml
---
bibliography: references.bib
csl: csl/nature.csl
link-citations: true
reference-section-title: References
---
```

This allows direct rendering to DOCX later, for example:

```bash
pandoc workspace/<name>/write.md -o workspace/<name>/write.docx
```

### 4. Write section by section from task cards

Do not free-write the whole review in one pass. By default, follow the task order in `execution-tasks.md`:

- write the core sections first
- then the controversy and limitation sections
- then the introduction, conclusion, and outlook

For each section, use this minimal workflow:

1. Read the final retained-paper set from `paper-classification.md` and build a citation-coverage checklist mapping retained papers to target sections
2. Read the matching `Section Card` in `review-plan.md`
3. Read the L3 evidence for that section in `section-evidence.md`
4. Check which tables from `table-plan.md` belong in this section
5. Draft a fact-grounded paragraph skeleton
6. Refine it for de-AI style and journal style
7. Confirm that every citation key exists in `references.bib`

### 5. Language style: close to Springer Nature Reviews

The goal is not to produce “something that sounds like an AI review,” but something closer to Springer Nature Reviews:

- establish the background quickly without generic scene-setting
- keep each section **argument-driven**, not paper-by-paper
- use natural paragraph transitions without piling up connectors
- stay critical about controversies and limitations
- keep the narrative rhythm tight and avoid mechanically symmetrical paragraphs
- let the conclusion transition naturally into open questions / outlook

### 6. De-AI style: follow the Humanize / `humanizer` principles

When drafting, use Humanize / `humanizer` as the default style reference. At minimum, avoid:

- hollow openings such as “In recent years, X has attracted widespread attention”
- template-like connector stacking such as repeated “Furthermore,” “It is worth noting that,” or “In summary”
- metanarrative with no information gain, such as “This section will discuss ...”
- inflated but vague praise such as “of great theoretical and practical significance”
- overly uniform paragraph lengths that feel template-generated
- the familiar three-part parallelism common in AI prose

Recommended practice:

- write the facts clearly first, then humanize the prose
- keep authorial judgment, but make the expression more natural and concrete
- if the environment supports it, call `/humanizer` or `/writing-polish` on section drafts for the final de-AI pass

### 7. Outputs

Write the default outputs to `workspace/<name>/`:

- `write.md`: the main Markdown manuscript
- `references.bib`: exported workspace references
- `csl/nature.csl` or another CSL specified by the current workspace

Optional add-ons:

- `write.docx`: if the user explicitly wants a rendered DOCX
- `sections/<nn>-<slug>.md`: if the user wants each section saved separately

### 8. Check the generated text

After the draft is generated, you must perform an **explicit check** rather than stopping as soon as writing finishes.

Before delivery, check at least the following:

1. **Factual consistency**: can every judgment be traced back to evidence inside the workspace?
2. **Structural consistency**: does the text follow `review-plan.md` strictly?
3. **Evidence consistency**: do the paragraphs genuinely use the L3 evidence in `section-evidence.md`?
4. **Citation coverage**: does every paper retained in the final Plan inside `paper-classification.md` appear at least once as a `[@key]` citation?
5. **Citation consistency**: can every `[@key]` be found in `references.bib`?
6. **CSL consistency**: does the `csl:` entry in the YAML header point to a real file inside the workspace?
7. **De-AI style**: does the text still contain boilerplate, mechanical transitions, or vague conclusions?
8. **Journal-style consistency**: does the overall manuscript feel close to Springer Nature Reviews?

If the check reveals factual, structural, citation, or style problems, revise the text before handing it over; if the problem comes from `/plan` itself, revise `/plan` first.

## Examples

User says: "`/plan` is finished. Now help me formally write the review based on the facts in the current workspace, and make sure the Markdown citations can be converted directly to DOCX."

→ Enter `/write`: read the `/plan` artifacts, prepare `references.bib` + `nature.csl`, and draft section by section from the task cards

User says: "Turn this workspace into a review that feels close to Springer Nature Reviews, and make sure the language doesn't sound AI-generated."

→ If `/plan` is already complete, go straight to `/write`; otherwise go to `/plan` first
