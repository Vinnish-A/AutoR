---
name: graph
description: Query citation graphs — view a paper's references, find which papers cite it, and analyze shared references between multiple papers. Use when the user asks about citation relationships, reference overlap, or bibliographic connections.
---

# Citation Graph Queries

View a paper's references, find which papers cite it, and identify shared references across multiple papers.

## Execution Logic

### View a Paper's References

```bash
autor refs "<paper-id>" [--ws NAME]
```

### Find Papers That Cite This Paper

```bash
autor citing "<paper-id>" [--ws NAME]
```

### Shared Reference Analysis

```bash
autor shared-refs "<id1>" "<id2>" [--min N] [--ws NAME]
```

Parameters:
- `--min N` — include only references cited by at least N papers (default 2)
- `--ws NAME` — limit scope to a specific workspace

## Prerequisites

Reference data comes from Semantic Scholar. It must be fetched first via:
- Automatic retrieval during ingestion
- Running `refetch --all --force` for existing papers
- Then running `index --rebuild` to update the citations table

## Examples

User says: "What papers does this paper cite?"
→ Run `refs "<paper-id>"`

User says: "Which papers cite this one?"
→ Run `citing "<paper-id>"`

User says: "What references do these two papers have in common?"
→ Run `shared-refs "<id1>" "<id2>"`
