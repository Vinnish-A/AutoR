---
name: literature-review
description: Write a literature review based on papers in a workspace. Covers topic organization, narrative structure, gap identification, and BibTeX export. Use when the user wants to draft a literature review, survey a research area, or summarize the state of the art.
---

# Literature Review Writing

Write a structured literature review based on the papers in a workspace.

## Prerequisites

The user must specify a **workspace** (`--ws NAME`). If the user does not specify one:
1. Run `autor ws list` to list existing workspaces
2. Have the user choose one or create a new one

Write the review output to `workspace/<name>/`.

If the user is still in the pre-writing planning stage—for example, they already have a rough subsection structure and want to revise it first, classify workspace papers by section, or design review tables in advance—switch to `/plan` first. After `/plan` is complete, return to this skill to start drafting the main text.

If the user has already completed `/plan` and wants to produce formal prose **strictly following the `/plan` structure**, **strictly grounded in the current workspace facts**, and using **DOCX-ready citations in Markdown + CSL**, switch to `/write` first. This skill is better suited to open-ended, exploratory review writing where the structure evolves through discussion.

If `workspace/<name>/review-plan.md` already exists, it is not optional reference material—it is a **hard constraint** on drafting the main text. Before writing, you must read:

- `workspace/<name>/review-plan.md`
- `workspace/<name>/execution-tasks.md`
- `workspace/<name>/paper-classification.md`
- `workspace/<name>/section-evidence.md`
- `workspace/<name>/table-plan.md`

If these files exist, the overall structure, section order, core question of each section, primary evidence pool, at least the L3 conclusion-evidence layer, and table placement must defer to them first; if changes are needed, go back to `/plan` to revise them before continuing.

## Workflow

### 1. Clarify the writing task

Confirm with the user:
- **Review topic**: What research question is the review centered on?
- **Target audience**: The Related Work section of a journal article? The literature review chapter of a thesis? A standalone review article?
- **Language**: Chinese / English
- **Length**: Approximate word count or page count
- **Style reference** (optional): The user may provide a sample paper or existing text. Analyze its structure, narrative style, citation density, and paragraph organization, then emulate it

If `/plan` artifacts already exist, the main purpose of this step is to **verify** whether the user's current request is consistent with `review-plan.md`; if not, update the plan first instead of skipping the plan and revising the main text directly.

### 2. Survey the literature scope

```bash
autor ws show <name>                    # List papers in the workspace
autor ws search <name> "<topic>"         # Search within the workspace scope
autor topics                             # Topic clustering overview (if already modeled)
```

Do a quick L1-L2 scan of the papers in the workspace (title + abstract) to build a high-level picture:
```bash
autor show <dir_name> --level 2          # Scan abstracts paper by paper
```

### 3. Build the review structure

Based on the literature, propose a grouping scheme (by method, timeline, research question, or theoretical tradition) and turn it into a section outline. Show the outline to the user for confirmation.

If the user has already completed `/plan`, you must directly reuse the confirmed outline in `review-plan.md`, the section cards, the paper classification results, the at-least-L3 conclusion evidence organized by category in `section-evidence.md`, and the table design. Do not rebuild the structure from scratch or reshuffle sections without explanation. If the user has made it clear that they want to use `/plan` without drafting the main text yet, then only build the framework based on `/plan`

There are only two cases where you may deviate from the plan:

1. The user explicitly asks to change the structure
2. Further L3/L4 reading shows that the plan clearly conflicts with the evidence

In either case, go back to `/plan` to update the structure and task cards before continuing with the main draft.

Common organizing patterns:
- **Thematic**: Group by research subquestion (most common)
- **Chronological**: Trace the field by stage of development
- **Methodological**: Compare technical approaches
- **Controversy-driven**: Organize arguments around competing viewpoints

### 4. Read key papers in depth

Load L3 (conclusion) or L4 (full text) for the core papers in each section:
```bash
autor show <dir_name> --level 3          # Conclusion
autor show <dir_name> --level 4          # Full text (key papers only)
```

**Multimodal analysis** (papers parsed by MinerU retain figures and formulas):
- Read the key figures and tables in each paper (`data/papers/<dir>/images/`) to help interpret experimental results and method workflows
- Analyze the mathematical formulas (LaTeX) in the papers to compare differences in modeling approaches across studies
- When needed, write Python code for quantitative comparisons (for example, extract reported numerical results from multiple papers and build comparison tables)

Use the citation graph to discover relationships:
```bash
autor shared-refs "<id1>" "<id2>"        # Shared reference analysis
autor refs "<id>"                        # References
autor citing "<id>"                      # Citing papers
```

### 5. Draft the review

Draft section by section following the confirmed outline. Writing principles:

- **Follow the Plan strictly**: The section order, the question each section must answer, the core evidence set, at least the L3 conclusion-evidence layer, table placement, and the functional role of each section must align with `review-plan.md`, `section-evidence.md`, and `execution-tasks.md`
- **Synthesize, don't enumerate**: Each paragraph should organize multiple papers around one argument rather than summarizing papers one by one
- **Maintain a critical perspective**: Point out methodological limitations, contradictory conclusions, and differences in experimental conditions
- **Use explicit transitions**: Ensure clear logical connections between sections
- **Citation format**: Use `(Author, Year)` or `Author (Year)` in the main text, corresponding to the BibTeX key
- **If a style reference is provided**: Closely follow the user-supplied exemplar's narrative rhythm, citation density, paragraph length, and terminology habits

If `/plan` has already set the table of contents in a Springer Nature Reviews style, use that structure by default rather than creating a separate writing framework.

By default, start by pulling the category-organized L3 conclusions from `section-evidence.md` to draft paragraphs and tables, then return to L4 for close reading as needed.

After finishing each section, pause for user review before continuing to the next one.

### 6. Finalize

- Write the opening of the review (research background + review scope + organizing logic) and the ending (current-state summary + research gaps + future directions)
- Export the references:
```bash
autor ws export <name> -o workspace/<name>/references.bib
```
- Save the main review text to `workspace/<name>/literature-review.md` (or the filename specified by the user)
- Finally check whether the main text outline, section-level evidence usage, table placement, and section emphasis are consistent with `review-plan.md`, `section-evidence.md`, `execution-tasks.md`, and `table-plan.md`

## Academic Attitude

- Paper conclusions are the authors' claims, not truth. The review should reflect balanced, critical thinking.
- When multiple papers reach different conclusions on the same question, proactively point out the disagreement and analyze the possible reasons.
- High citation counts ≠ correctness. Evaluate them together with methodological quality, experimental conditions, and reproducibility.
- Clearly distinguish between "conclusions supported by experimental evidence" and "the authors' speculation/interpretation".

## Examples

User says: "Help me write a literature review on turbulent drag reduction based on the drag-review workspace"
→ Check `ws show drag-review`, scan the papers, propose an outline, and draft section by section

User says: "I have a sample passage—help me write in this style"
→ Analyze the sample's structure and narrative features, then organize the writing in that style
