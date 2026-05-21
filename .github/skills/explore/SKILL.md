---
name: explore
description: Explore literature by fetching papers from OpenAlex with multi-dimensional filters (ISSN, concept, author, institution, keyword, etc.) and searching the isolated explore library with SQLite FTS5. Use when the user wants to survey a journal, explore a research field, analyze an author's output, or do landscape analysis.
---

# Multi-Dimensional Literature Exploration

Fetch literature from OpenAlex with multi-dimensional filters. Explore data is
isolated in `data/explore/<name>/` and searched with deterministic FTS5.

## Fetch Papers

```bash
autor explore fetch --issn <ISSN> --name <name> [--year-range <start-end>]
autor explore fetch --concept <OpenAlex-concept-ID> --name <name>
autor explore fetch --author <OpenAlex-author-ID> --name <name>
autor explore fetch --institution <OpenAlex-institution-ID> --name <name>
autor explore fetch --keyword "acoustic metamaterial" --name <name>
autor explore fetch --issn 0022-1120 --name jfm --incremental
```

Useful filters:

- `--issn`
- `--concept`
- `--topic-id`
- `--author`
- `--institution`
- `--keyword`
- `--source-type`
- `--oa-type`
- `--min-citations`
- `--year-range`
- `--incremental`

## Search

```bash
autor explore search --name <name> "<query>" [--top N]
```

No `--mode` flag is used; explore search is FTS5-only.

## Examples

User says: "Fetch all papers from JFM."
→ Run `autor explore fetch --issn 0022-1120 --name jfm`

User says: "Search JFM for drag reduction."
→ Run `autor explore search --name jfm "drag reduction"`

User says: "Update the JFM explore library."
→ Run `autor explore fetch --issn 0022-1120 --name jfm --incremental`
