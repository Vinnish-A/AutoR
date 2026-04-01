---
name: enrich
description: Enrich paper metadata using LLM extraction. Extract table of contents (TOC), conclusions (L3), backfill abstracts, or refetch citation counts from APIs. Use when the user wants to extract conclusions, build TOC, update citation data, or backfill missing abstracts.
---

# Enrich Paper Content

Use LLM to extract a table of contents (TOC) or conclusion section (L3) from papers, enriching their metadata.

> **Note**: `import-endnote` / `import-zotero` automatically run toc + l3 + abstract backfill by default. The commands below are for **selective enrichment** — re-extracting specific papers, supplementing individual entries, or processing the entire library.

## Execution Logic

1. Determine the user's intent:
   - **Extract TOC**: use `enrich-toc`
   - **Extract conclusion**: use `enrich-l3`
   - **Backfill abstracts**: use `backfill-abstract` (extracts from .md + LLM validation)
   - **Refetch citation counts**: use `refetch` (re-queries APIs to fill in `citation_count` and related fields)

2. Determine the scope:
   - Specify a paper ID → process that single paper
   - User says "all" → use `--all`
   - Optionally add `--force` to overwrite existing results

3. Run the command:

**Extract TOC:**
```bash
autor enrich-toc [<paper-id> | --all] [--force]
```

**Extract conclusion:**
```bash
autor enrich-l3 [<paper-id> | --all] [--force]
```

**Backfill abstracts:**
```bash
autor backfill-abstract [--dry-run]
```

**Refetch citation counts:**
```bash
autor refetch [<paper-id> | --all] [--force]
```

4. Display the processing results.

## Examples

User says: "Extract the conclusions for all papers."
→ Run `enrich-l3 --all`

User says: "Re-extract the TOC for Smith-2023-Survey."
→ Run `enrich-toc "Smith-2023-Survey" --force`

User says: "Backfill missing abstracts."
→ Run `backfill-abstract`, then suggest running `embed --rebuild`

User says: "Refresh the citation counts."
→ Run `refetch --all`, then `index --rebuild`
