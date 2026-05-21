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

## Workspace-Scoped Runs

New ingest batches can be attached to a workspace during ingest:

```bash
autor pipeline ingest --workspace my_project
```

Only papers actually written to `data/papers/` in that run are added. Pending papers and deduplicated papers are not added.

For pipelines that do not include inbox steps, `--workspace/-w` scopes paper and global steps to existing papers in that workspace:

```bash
autor pipeline enrich -w my_project
autor pipeline reindex -w my_project
autor enrich-l3 --workspace my_project --only-missing
```

This is the preferred way to enrich a review workspace without accidentally running L3/TOC extraction across the whole library.

During normal ingest, the global `index` step is batched once for the changed paper IDs in that run. This updates the node-level FTS5 evidence index incrementally without vector/FAISS writes.

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
