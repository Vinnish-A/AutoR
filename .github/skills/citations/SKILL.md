---
name: citations
description: View top-cited papers ranking and refetch citation counts from APIs. Use when the user asks about highly cited papers, citation rankings, or wants to update citation data.
---

# Citation Count Queries

View highly cited paper rankings, or refetch citation count data for papers.

## Execution Logic

### View Top-Cited Paper Rankings

```bash
autor top-cited [--top N] [--year RANGE] [--journal NAME] [--type TYPE]
```

### Refetch Citation Counts

```bash
# Refetch all papers missing citation counts
autor refetch --all

# Force re-query all papers
autor refetch --all --force

# Refetch a single paper
autor refetch "<paper-id>"
```

## Examples

User says: "Which papers have the most citations?"
→ Run `top-cited --top 20`

User says: "Show highly cited papers in fluid mechanics journals."
→ Run `top-cited --journal "Fluid Mech"`

User says: "Refresh my citation counts."
→ Run `refetch --all`

User says: "Top review articles from 2020 onwards."
→ Run `top-cited --year 2020- --type review`
