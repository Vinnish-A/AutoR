---
name: write
description: Draft a fact-grounded review manuscript from the current workspace by following the `/plan` outputs, using seeded section openings, restrained Nature Reviews-style control, and DOCX-ready Markdown citations with CSL. Use this after planning when the user wants the full draft.
---

# Plan-Grounded Review Drafting

Use this skill after `/plan`. It turns a fixed outline and evidence base into manuscript prose. It is not for re-planning.

## Hard constraints

1. **Fact-grounded**: use only papers and evidence that already exist in the current workspace
2. **Plan-grounded**: follow the structure and section tasks produced by `/plan`
3. **Style-guided, not style-copying**: absorb register and structure, not phrases
4. **Seeded drafting**: vary argumentative entry points instead of writing every section from the same template
5. **DOCX-ready citations**: use Markdown citations plus a real CSL file

## Required inputs

The user must specify a workspace (`--ws NAME`).

Before drafting, read:

- `workspace/<name>/review-plan.md`
- `workspace/<name>/execution-tasks.md`
- `workspace/<name>/paper-classification.md`
- `workspace/<name>/section-evidence.md`
- `workspace/<name>/table-plan.md`

If these files are missing, stop and run `/plan` first.

## Workflow

### 0. Load plan files and style references

Read the plan artifacts first.

If the target style is **Nature Reviews** or **Springer Nature Reviews**, read these files before drafting:

- `.github/skills/polish/example/originals.md`
- `.github/skills/polish/example/excerpts.md`
- `.github/skills/polish/example/strategies.md`

Use them for:

- editorial compression
- paragraph rhythm
- argument control
- calibrated judgment
- conclusion design

Do not reuse:

- claims
- examples
- terminology that does not belong to the workspace
- phrasing
- metaphors

The point is to remember how the prose behaves, not what those papers say.

### 1. Lock the evidence boundary

Claims, comparisons, controversy judgments, and summary statements should come only from material inside the current workspace:

- papers already in the workspace
- evidence files produced by `/plan`
- trial outputs under `workspace/<name>/trials/` if present

Do not patch factual gaps from model memory. If a claim is not supported in the workspace:

- go back to `/plan` or `/search`
- or mark it as `[CITATION NEEDED IN WORKSPACE]`

Never invent citations.

### 2. Prepare citation assets first

#### 2.1 Export workspace references

```bash
autor ws export <name> -o workspace/<name>/references.bib
```

#### 2.2 Choose the CSL file

Use this order:

1. `workspace/<name>/style.csl`
2. any existing `*.csl` under `workspace/<name>/`
3. fetch the default CSL: `nature.csl`

Recommended path:

```text
workspace/<name>/csl/nature.csl
```

Source:

- `https://raw.githubusercontent.com/citation-style-language/styles/master/nature.csl`

#### 2.3 Use Markdown citations in the main text

Do not use plain-text citation placeholders such as `(Author, Year)`.

Use Pandoc / citeproc Markdown citations:

- single citation: `[@smith2021]`
- multiple citations: `[@smith2021; @wang2023]`

Recommended YAML header:

```yaml
---
bibliography: references.bib
csl: csl/nature.csl
link-citations: true
reference-section-title: References
---
```

### 3. Build a seed map before drafting

Do not begin by free-writing the introduction. First build **section seeds**.

A seed is not a title, theme, or conclusion. It is a precise argumentative entry point for a section.

Seed families:

| Seed family | Use when | Example move |
| --- | --- | --- |
| Misread -> correction | The field is commonly framed in a misleading way | "X is often treated as ..., but the evidence is tighter than that." |
| Boundary tightening | The topic is broad and needs scope control | "This review is not about all forms of X; it is about the subset that changes Y." |
| Pressure -> mechanism | A biological or clinical pressure organizes the section | "Cells at this stage do not face one problem but a specific pressure stack." |
| Failure mode | The section works best when organized around what breaks first | "The second step becomes necessary only after a distinct failure mode appears." |
| State switch | The section is about transition, not static classification | "The key change is not more X, but a shift from state A to state B." |
| Paradigm shift | New data changed an older consensus | "The older view treated X as ..., but newer evidence ties it to ..." |
| Decision point | Clinical or translational sections need choice logic | "The practical question is not whether to intervene, but when and on what basis." |
| Evidence gap | The honest move is to define what can and cannot yet be claimed | "The field has a usable model here, but not yet a complete causal chain." |

Seed rules:

1. A seed must be specific enough to generate a first paragraph
2. A seed must arise from workspace evidence, not generic rhetoric
3. A seed should open one problem, not the whole field
4. A seed should not already contain the final verdict
5. A seed should sound different from the seeds used in nearby sections

For the **introduction**, each **major section opening**, and the **conclusion**, draft **2-4 seeds from different families** before choosing one.

Then:

1. select one primary seed
2. keep one reserve seed only if needed
3. note which opening moves are already used

Do not generate three full section drafts by default. Generate several openings, choose one, then continue.

### 4. Draft section openings first

Before writing full sections, draft the opening paragraph for:

- the introduction
- each major body section
- the conclusion

This is where most sameness begins. Fix it here, not later.

Good section openings usually do one of these:

- define the real problem quickly
- narrow the scope
- install a mechanism or decision frame
- mark a shift in evidence or state
- expose a false equivalence in the literature

Weak section openings usually do this:

- generic scene-setting
- "In recent years..." framing
- paper listing
- telling the reader what the section will do
- repeating the same contrast formula used in the previous section

### 5. Draft the body section by section

By default, follow `execution-tasks.md`:

- core mechanism sections first
- controversy and limitation sections next
- introduction and conclusion after the body is stable

For each section:

1. read the retained-paper set in `paper-classification.md`
2. read the matching `Section Card` in `review-plan.md`
3. read the relevant evidence in `section-evidence.md`
4. check which tables from `table-plan.md` belong here
5. choose the section seed
6. write a short section thesis in 1-2 sentences
7. build paragraphs from claim -> explanation/evidence -> implication/boundary
8. confirm that every citation key exists in `references.bib`

### 6. Keep the register controlled

Aim for:

- fast openings, then narrowing
- explanation before display
- logic-driven transitions
- calm but definite judgment
- operational definitions
- conclusions that sharpen questions instead of dissolving into vague optimism

Avoid:

- generic background throat-clearing
- paper-by-paper recitation
- metanarrative such as "This section discusses..."
- connector stacking
- decorative balance with little selection
- repeating the same seed family across every section
- repeated "not X but Y" turns as a default sentence shape
- relying on a later polish pass to fix weak structure

Tables and figures should carry analytical load. Do not narrate document design in the main text.

### 7. Outputs

Write the default outputs to `workspace/<name>/`:

- `write.md`
- `references.bib`
- `csl/nature.csl` or another CSL file already chosen by the workspace

Optional outputs:

- `write.docx` if the user explicitly wants a rendered DOCX
- `sections/<nn>-<slug>.md` if the user wants each section saved separately
- `seed-map.md` only if the user wants process artifacts or if the team is iterating on style

### 8. Check before delivery

Do not stop when the draft is merely complete. Check at least:

1. **Factual consistency**: every judgment can be traced to workspace evidence
2. **Structural consistency**: the manuscript follows `review-plan.md`
3. **Evidence use**: paragraphs actually use `section-evidence.md`, not generic filler
4. **Citation coverage**: every retained paper appears at least once in the main text
5. **Citation consistency**: every `[@key]` exists in `references.bib`
6. **CSL consistency**: the YAML header points to a real CSL file
7. **Opening diversity**: the introduction and major sections do not all begin with the same move
8. **Paragraph control**: each paragraph solves one sub-problem and ends with a consequence, limit, or transition
9. **Terminology control**: terms are stable, defined, and not inflated
10. **Conclusion sharpness**: the ending closes the argument and names specific open questions

If the problem is factual or structural, revise the draft. If the problem comes from the plan, revise `/plan` first.

## Short examples

User says: "`/plan` is finished. Draft the review and keep the citations ready for DOCX export."

-> Read the plan files, prepare `references.bib` and the CSL, build seeds for the introduction and section openings, then draft section by section.

User says: "Write this as a Nature Reviews-style review, but avoid formulaic prose."

-> Read the exemplar files first, build multiple section seeds, choose distinct entry moves, and draft from those seeds rather than from one repeating template.
