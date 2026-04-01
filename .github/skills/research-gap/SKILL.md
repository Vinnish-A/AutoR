---
name: research-gap
description: Identify research gaps and open questions from the literature in a workspace. Combines topic clustering, citation analysis, and cross-paper comparison. Use when the user wants to find unexplored areas, formulate research questions, or assess where the field is heading.
---

# Research Gap Identification

Systematically discover research gaps and open questions from the literature in a workspace.

## Prerequisites

The user must specify a **workspace** (`--ws NAME`) containing a sufficient number of papers (10+ recommended).
Report language is specified by the user (English or Chinese).

## Execution Logic

### 1. Global Scan

```bash
autor ws show <name>                    # paper list
autor topics                             # topic clustering (if model already built)
```

Perform an L2 scan (title + abstract) on workspace papers to build a field map.

### 2. Multi-Dimensional Analysis

#### Dimension 1: Topic Coverage
```bash
autor topics                             # overall topic distribution
autor topics --topic <ID>                # papers in each topic
```
Are workspace papers concentrated in a few topics? Which related topics lack coverage?

#### Dimension 2: Temporal Trends
Tally workspace papers by year to identify:
- Directions with rapidly growing paper counts in recent years (hot topics)
- Directions where publication rates are declining (possibly matured or abandoned)
- Directions with early work but no recent follow-up (potential gaps)

Use Python to read `data/papers/*/meta.json` directly for statistical analysis.

#### Dimension 3: Methodological Comparison
Scan the methods sections of workspace papers (L3–L4) to construct a methodology matrix:
```bash
autor show <dir_name> --level 3          # conclusions often mention methods
```
- Which methods are widely used?
- Which method combinations have not yet been tried?
- A method that works for problem A — can it transfer to problem B?

#### Dimension 4: Citation Graph Holes
```bash
autor shared-refs "<id1>" "<id2>"        # shared references
autor refs "<id>"                        # reference list
autor citing "<id>"                      # papers that cite this one
```
- Which papers cite each other but reach contradictory conclusions? (unresolved disputes)
- Which heavily cited papers lack follow-up verification/replication?
- Which key references are absent from the workspace? (possible blind spots)

#### Dimension 5: Author-Stated Future Work
Load L3 (conclusion) of highly cited workspace papers and extract future directions the authors themselves proposed:
```bash
autor show <dir_name> --level 3
```
Have those future directions been addressed? Cross-search to verify:
```bash
autor usearch "<future work keywords>"
```

### 3. Output Report

Generate a structured research-gap report and save it to `workspace/<name>/research-gaps.md`.

Classify each identified gap by type:

| Gap Type | Meaning | Example |
|----------|---------|---------|
| **Knowledge gap** | A phenomenon/question no one has studied yet | "The X effect at high Re has not been measured" |
| **Methodological gap** | Existing conclusions but method has flaws or limitations | "All current studies use RANS; DNS validation is lacking" |
| **Contradiction gap** | Different studies reach contradictory conclusions | "Group A reports a positive effect; Group B reports a negative one" |
| **Transfer gap** | A method/finding has not been extended to a related domain | "This method works in 2D; 3D has not been attempted" |
| **Scale gap** | Only small-scale or restricted results exist | "Only low-Re data; not validated at engineering Re" |

Report structure:
1. **Field overview** (2–3 paragraphs)
2. **Identified research gaps** (ranked by priority)
   - Gap type + description
   - Supporting evidence (which papers hint at this gap)
   - Potential research questions
   - Feasibility assessment (are data / methods / resources accessible?)
3. **Unresolved disputes** (if any)
4. **Recommended next steps**

**Quantitative support**: when useful, write Python code to batch-extract data from meta.json, produce statistical charts (year distribution, method frequency, parameter-space coverage), and use visualizations to substantiate gap findings.

### 4. Interactive Discussion

After the report is generated, proactively discuss with the user:
- Which gaps are most relevant to their research direction?
- Are additional papers needed to validate a particular gap?
- Can a gap be refined into a specific research question and hypothesis?

## Examples

User says: "Find research gaps in the drag-review workspace."
→ Comprehensively scan the literature, multi-dimensional analysis, generate research-gap report

User says: "What future work directions did these papers mention? Has anyone followed up?"
→ Extract future-work statements from each paper's conclusion, then cross-search to verify
