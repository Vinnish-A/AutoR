---
name: search
description: Search academic papers in the local autor knowledge base. Uses auditable node-level FTS5 evidence search, evidence bundles, author search, and top-cited ranking. Use when the user wants to find papers, look up literature, search by author, or explore research topics.
---

# Literature Search

Search for papers in the local library. Defaults to auditable node-level FTS5 retrieval over metadata plus `paper.md` chunks. For complex questions, generate a bundle with trace/verify artifacts.

## Execution Logic

1. Parse user input and determine the search mode:
   - If the user explicitly asks for "semantic search", "vector search", or "vsearch" → explain that this project no longer has vector search and use `search` or `research`
   - If the user explicitly asks for "keyword search", "full-text search", "FTS", or ordinary paper search → use `search`
   - If the user asks a question that needs answer-time provenance → use `research`
   - If the user explicitly wants to search by author (e.g. "find papers by X", "papers published by X") → use `search-author`
   - If the user asks to sort by citation count (e.g. "most cited", "classic papers", "top cited") → use `top-cited`
   - **Default: use `search`** for paper retrieval, or `research` when answer-time provenance is needed.
   - Do not look for an embedding refresh command; vector and FAISS storage has been removed.

2. Extract from user input:
   - **Query**: what the user wants to find
   - **Result count**: `--top N` if specified; otherwise use the default
   - **Year filter**: `--year 2023` (single year), `--year 2020-2024` (range), `--year 2020-` (from year onwards)
   - **Journal filter**: `--journal "Fluid Mechanics"` (fuzzy match)
   - **Type filter**: `--type review` (fuzzy match; common values: `review`, `journal-article`, `book-chapter`)

3. Run the search command:

**Auditable search (default):**
```bash
autor search "$ARGUMENTS" --top <N> [--year <Y>] [--journal <J>] [--type <T>]
```

**Keyword search:**
```bash
autor search "<query>" --top <N> [--year <Y>] [--journal <J>] [--type <T>]
```

**Evidence bundle:**
```bash
autor research "<query>" --top <N> --run-dir workspace/runs/<case>
```

**Author search:**
```bash
autor search-author "<author name>" --top <N> [--year <Y>] [--journal <J>] [--type <T>]
```

**Top-cited ranking:**
```bash
autor top-cited --top <N> [--year <Y>] [--journal <J>] [--type <T>]
```

4. Present the search results to the user. Each result may include `evidence` snippets with `node_id`, `section`, `snippet`, and `ref_path`. For `research`, answer only from the generated bundle and preserve the `## References` section.

5. **Complex queries**: when CLI parameter combinations are insufficient (e.g. filtering by first-author initial, multi-condition intersections, custom sorting), read `data/papers/*/meta.json` directly in Python. Key JSON fields:

```
title, authors, first_author, first_author_lastname, year, doi, journal,
abstract, paper_type, citation_count (dict: crossref/semantic_scholar/openalex),
ids, toc, l3
```

## Examples

User says: "Search for papers on turbulent boundary layers."
→ Run `search "turbulent boundary layer"`

User says: "Use semantic search to find literature on drag reduction; give me the top 5."
→ Say vector search is deprecated, then run `search "drag reduction" --top 5`

User says: "Find papers by Liao Z-M."
→ Run `search-author "Liao"`

User says: "What are the most-cited papers in my library?"
→ Run `top-cited --top 10`

User says: "Papers on drag reduction after 2020."
→ Run `search "drag reduction" --year 2020-`

User says: "Turbulence papers published in JFM."
→ Run `search "turbulence" --journal "Fluid Mechanics"`

User says: "Most-cited review articles in my library."
→ Run `top-cited --top 10 --type review`
