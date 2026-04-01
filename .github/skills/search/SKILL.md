---
name: search
description: Search academic papers in the local autor knowledge base. Supports unified search (keyword + semantic fusion), keyword-only (FTS5), semantic-only (FAISS), author search, and top-cited ranking. Use when the user wants to find papers, look up literature, search by author, or explore research topics.
---

# Literature Search

Search for papers in the local library. Defaults to unified retrieval (keyword + semantic vector merged ranking), with individual modes also available.

## Execution Logic

1. Parse user input and determine the search mode:
   - If the user explicitly asks for "semantic search", "vector search", or "vsearch" → use `vsearch`
   - If the user explicitly asks for "keyword search", "full-text search", or "FTS" → use `search`
   - If the user explicitly wants to search by author (e.g. "find papers by X", "papers published by X") → use `search-author`
   - If the user asks to sort by citation count (e.g. "most cited", "classic papers", "top cited") → use `top-cited`
   - **Default: use `usearch` (unified retrieval)** — runs FTS5 keyword search and FAISS semantic search simultaneously, merges and deduplicates results. Papers matching both sources rank higher. Falls back to keyword-only when the vector index is unavailable.

2. Extract from user input:
   - **Query**: what the user wants to find
   - **Result count**: `--top N` if specified; otherwise use the default
   - **Year filter**: `--year 2023` (single year), `--year 2020-2024` (range), `--year 2020-` (from year onwards)
   - **Journal filter**: `--journal "Fluid Mechanics"` (fuzzy match)
   - **Type filter**: `--type review` (fuzzy match; common values: `review`, `journal-article`, `book-chapter`)

3. Run the search command:

**Unified retrieval (default):**
```bash
autor usearch "$ARGUMENTS" --top <N> [--year <Y>] [--journal <J>] [--type <T>]
```

**Keyword search:**
```bash
autor search "<query>" --top <N> [--year <Y>] [--journal <J>] [--type <T>]
```

**Semantic search:**
```bash
autor vsearch "<query>" --top <N> [--year <Y>] [--journal <J>] [--type <T>]
```

**Author search:**
```bash
autor search-author "<author name>" --top <N> [--year <Y>] [--journal <J>] [--type <T>]
```

**Top-cited ranking:**
```bash
autor top-cited --top <N> [--year <Y>] [--journal <J>] [--type <T>]
```

4. Present the search results to the user. Each unified-retrieval result is tagged with its match source:
   - `both`: matched by both keyword and semantic search (most relevant)
   - `fts`: keyword match only
   - `vec`: semantic match only

5. **Complex queries**: when CLI parameter combinations are insufficient (e.g. filtering by first-author initial, multi-condition intersections, custom sorting), read `data/papers/*/meta.json` directly in Python. Key JSON fields:

```
title, authors, first_author, first_author_lastname, year, doi, journal,
abstract, paper_type, citation_count (dict: crossref/semantic_scholar/openalex),
ids, toc, l3_conclusion
```

## Examples

User says: "Search for papers on turbulent boundary layers."
→ Run `usearch "turbulent boundary layer"`

User says: "Use semantic search to find literature on drag reduction; give me the top 5."
→ Run `vsearch "drag reduction" --top 5`

User says: "Find papers by Liao Z-M."
→ Run `search-author "Liao"`

User says: "What are the most-cited papers in my library?"
→ Run `top-cited --top 10`

User says: "Papers on drag reduction after 2020."
→ Run `usearch "drag reduction" --year 2020-`

User says: "Turbulence papers published in JFM."
→ Run `usearch "turbulence" --journal "Fluid Mechanics"`

User says: "Most-cited review articles in my library."
→ Run `top-cited --top 10 --type review`
