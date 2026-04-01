---
name: paper-writing
description: Assist with writing sections of a research paper (Introduction, Related Work, Method, Results, Discussion, Conclusion). Leverages workspace papers for citations and evidence. Use when the user wants help drafting or revising specific paper sections.
---

# Research Paper Writing Assistance

Help the user draft sections of a research paper, using the literature in a workspace for evidence and citations.

## Prerequisites

The user must specify a **workspace** (`--ws NAME`). If the user does not specify one:
1. Run `autor ws list` to show existing workspaces
2. Have the user choose one or create a new one

Write all output to `workspace/<name>/`.

## Workflow

### 1. Understand the writing request

Confirm the following with the user:
- **Which section to write**: Introduction / Related Work / Method / Results / Discussion / Conclusion / Abstract
- **Target journal or conference**: formatting requirements and length limits
- **Language**: Chinese / English
- **Existing material**: drafts, outlines, experimental data, figures
- **Style reference** (optional): the user may provide a paper from the same journal or field. Analyze its style—sentence structure, term choice, paragraph rhythm, citation habits, and level of formality—then write in that style

### 2. Section-specific strategies

#### Introduction
1. Start from the broader background and narrow gradually to the specific problem
2. Use workspace papers to establish the research context:
   ```bash
   autor ws search <name> "<background keywords>"
   autor show <dir_name> --level 2      # Abstract
   ```
3. Clearly identify the limitations of existing work (the research gap)
4. State the contribution of the current paper

#### Related Work
This is essentially a focused literature review; follow the `/literature-review` skill, but in a tighter form:
- Group work by how it relates to the current paper, rather than by topic alone, and make the similarities and differences explicit
- Clearly state how the present paper improves on prior work

#### Method
1. The user explains the method; you help turn it into a clear, well-structured narrative
2. Find comparable methods from papers in the workspace:
   ```bash
   autor ws search <name> "<method keywords>"
   autor show <dir_name> --level 4      # Read the full text for method details
   ```
3. Make sure notation is consistent and derivations are complete
4. **Formulas and figures**: read the mathematical derivations (LaTeX) and method diagrams (`images/`) in reference papers, compare them with the current method, and ensure the description is accurate

#### Results / Discussion
1. The user provides experimental data and/or figures
2. Retrieve comparable baselines from the workspace:
   ```bash
   autor ws search <name> "<experimental condition>"
   autor show <dir_name> --level 3      # Conclusion
   ```
3. **Figure-based comparison**: inspect result figures in the reference papers (`data/papers/<dir>/images/`) and compare them qualitatively or quantitatively with the user's results
4. **Code-based verification**: use Python for data analysis, statistical testing, and visualization so that Discussion claims are supported by actual computation
5. **Results**: describe the findings objectively and cite the relevant figures
6. **Discussion**: explain possible reasons, compare with the literature, and discuss limitations

#### Conclusion
- Summarize the main findings without introducing new material
- Briefly state limitations and future directions

#### Abstract
- Write it last, after the full paper is settled
- Include: one sentence of background, one sentence of problem, one sentence of method, two sentences of key results, and one sentence of significance
- Follow the target journal's word limit strictly

### 3. Citation management

- Match the in-text citation format to the target venue (often `\cite{key}` or `(Author, Year)`)
- **All citations must come from real papers already in the workspace**; never invent references
- If the workspace is missing a paper that needs to be cited, tell the user to add it:
  ```bash
  autor usearch "<keywords>"               # Search the full library for candidates
  autor ws add <name> <dir_name>           # Add to the workspace
  ```
- Final export:
  ```bash
  autor ws export <name> -o workspace/<name>/references.bib
  ```

### 4. Output

- Save each completed section under `workspace/<name>/` (for example, `introduction.md`, `related-work.md`)
- Or merge them into one full manuscript if the user requests it

## Writing principles

- **Citation integrity**: cite only papers that actually exist in the workspace. If a claim needs support but the library does not contain a matching paper, mark it as `[CITATION NEEDED]` instead of fabricating a reference. AI-generated text frequently hallucinates citations, so validate them with `/citation-check`
- **If a style reference is provided**: analyze the sample's sentence length, active/passive balance, term density, and paragraph structure, then imitate it closely
- **Avoid AI tics**: do not rely on stock phrases such as “it is worth noting that” or “in recent years, ... has garnered significant attention”; use specific, precise academic wording instead
- **Data-driven writing**: every claim in Results and Discussion should be backed by data or citations
- **Computational verification**: when the paper involves numerical results or mathematical derivations, write Python code to verify them independently rather than relying on intuition or hand calculation

## Pre-submission checklist

After the full manuscript is complete, check the following six items one by one:

1. **Structural completeness**: are all sections present, and does the logic hang together? Does the Introduction raise the question that the Conclusion ultimately answers?
2. **Citation consistency**: do in-text citations and the reference list match one-to-one, with nothing missing or extra? Validate with `/citation-check`
3. **Figure and table quality**: is every figure/table cited in the text, with clear legends and complete axis labels?
4. **Reproducibility**: is the method described in enough detail, and are all critical parameters listed?
5. **Language quality**: are terms consistent throughout, and are tenses used correctly? Use `/writing-polish` for final polishing if needed
6. **Formatting compliance**: does the manuscript meet the target venue's requirements for length, figures, and reference style?

## Examples

User says: "Help me draft the Introduction for workspace my-paper"
→ Scan `ws show my-paper`, understand the research direction, clarify the problem, and draft the Introduction

User says: "Write the Related Work section in the style of this JFM paper"
→ Analyze the user's sample and organize the Related Work in that style

User says: "I have experimental data—help me write the Results and Discussion"
→ Read the data, retrieve comparison papers from the workspace, and write the analysis
