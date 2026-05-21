---
name: show
description: View paper content at different detail levels. L1 (metadata), L2 (abstract), L3 (paper-level conclusion card), L4 (full text). Use when the user wants to read a paper, see its abstract, L3 takeaway, or full content.
---

# View Paper Content

View the content of a specified paper in a layered structure. Supports four levels: L1 (metadata), L2 (abstract), L3 (paper-level conclusion card), and L4 (full text).

## Execution Logic

1. Parse user input and extract:
   - **paper-id**: the paper identifier (i.e. the directory name under `data/papers/`)
   - **layer**: the level to view (1–4); defaults to L1+L2 if not specified

2. If the user is unsure of the paper ID, use `/search` first to locate the target paper.

3. Run the view command:

```bash
autor show "<paper-id>" --layer <N>
```

4. Format the content and display it to the user. For L4 full text, if the content is very long, show the abstract first and ask the user whether they need the complete content.

## Level Overview

| Level | Content | Notes |
|-------|---------|-------|
| L1 | Metadata | title, authors, year, journal, doi |
| L2 | Abstract | abstract |
| L3 | Paper-level conclusion card | takeaway, key findings, quantitative signals, limitations, and provenance when available |
| L4 | Full text | complete Markdown |

## Examples

User says: "Show me the abstract of Smith-2023-TransformerSurvey."
→ Run `show "Smith-2023-TransformerSurvey" --layer 2`

User says: "Give me the full text of Zhang-2024-LLM."
→ Run `show "Zhang-2024-LLM" --layer 4`

User says: "What is the conclusion of this paper?" (paper ID already in context)
→ Run `show "<paper-id>" --layer 3`
