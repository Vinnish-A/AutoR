# Paper Ingestion

## Quick Ingest

Place PDFs in `data/inbox/` and run the pipeline:

```bash
autor pipeline ingest
```

This will:

1. Convert PDFs to Markdown (via MinerU)
2. Extract metadata (regex + LLM)
3. Query APIs for completeness (Crossref, Semantic Scholar, OpenAlex)
4. Deduplicate by DOI
5. Move to `data/papers/` and update indexes

## Three Inboxes

| Inbox | Path | Behavior |
|-------|------|----------|
| Papers | `data/inbox/` | Standard pipeline with DOI dedup |
| Theses | `data/inbox-thesis/` | Skips DOI check, marks as thesis |
| Documents | `data/inbox-doc/` | Skips DOI check, LLM-generated title/abstract |

## Skip MinerU

Already have Markdown? Place `.md` files directly in the inbox — MinerU conversion is skipped.

## Pending Papers

Papers without DOI (that aren't theses) go to `data/pending/` for manual review. Add a DOI and re-run the pipeline to complete ingestion.

## External Import

```bash
# From Endnote
autor import-endnote library.xml

# From Zotero
autor import-zotero --api-key KEY --library-id ID
```
