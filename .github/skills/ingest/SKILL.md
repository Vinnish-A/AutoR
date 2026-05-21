---
name: ingest
description: Ingest papers from inbox into the knowledge base. Runs the pipeline to convert PDFs via MinerU (auto-splits long PDFs), extract metadata, deduplicate by DOI, generate L3 paper-level conclusion cards by default, and update the node-level FTS5 evidence index. Supports three inboxes - regular papers, theses, and general documents.
---

# Ingest Papers

Process PDF papers from the inbox into the knowledge base, or run the full processing pipeline.

## Execution Logic

1. Choose a pipeline preset based on user intent:
   - **Ingest new papers** (default): use the `ingest` preset; it now includes L3 paper-level conclusion-card generation and FTS5 indexing
   - **Full processing**: use the `full` preset when an explicit TOC should also be saved before/alongside L3
   - **Rebuild FTS5 index only**: use the `reindex` preset
   - **Content enrichment only**: use the `enrich` preset
   - **Retrieval refresh**: use the `index` step; no embedding step exists

2. Run the pipeline command:

```bash
autor pipeline <preset>
```

Available presets: `full` | `ingest` | `enrich` | `reindex`

3. The pipeline processes three inbox directories in sequence:
   - `data/inbox/` — regular papers (ingested only if a DOI is found; moved to pending if no DOI and not a thesis)
   - `data/inbox-thesis/` — theses (DOI deduplication skipped; automatically tagged as thesis)
   - `data/inbox-doc/` — non-paper documents (technical reports, lecture notes, standards, etc.; DOI deduplication skipped; LLM generates title/abstract)

4. Handling papers without a DOI:
   - From `data/inbox-thesis/` → tagged as thesis and ingested directly
   - From `data/inbox-doc/` → tagged as document type; LLM generates title and abstract, then ingested
   - From `data/inbox/` → LLM classifies whether it is a thesis
     - Is a thesis → tagged and ingested
     - Not a thesis → moved to `data/pending/` for manual review

5. Long PDFs (> 100 pages) are automatically split into shorter PDFs, converted in segments, then merged.

6. Display a summary of the processing results.

## Examples

User says: "I added some new papers to the inbox; please ingest them."
→ Run `pipeline ingest`

User says: "Process all new papers completely, including explicit TOC extraction."
→ Run `pipeline full`

User says: "I have some technical reports in inbox-doc."
→ Run `pipeline ingest` (the pipeline automatically handles all three inbox directories)

User says: "Rebuild the index."
→ Run `pipeline reindex`

User says: "I need semantic search / vector search."
→ Explain vector search has been removed, then use `autor search ...` or `autor research ...` for auditable evidence retrieval
