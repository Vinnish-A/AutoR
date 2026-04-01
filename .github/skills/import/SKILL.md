---
name: import
description: Import papers from external reference managers (Endnote XML/RIS, Zotero Web API or local SQLite). Handles PDF matching, MinerU conversion, metadata enrichment, and index updates. Use when the user wants to import their existing library from Zotero, Endnote, or attach a PDF to an existing paper.
---

# Import from External Reference Managers

## Endnote Import

Supports Endnote export files in XML and RIS formats.

```bash
# Full import: metadata + PDF matching + MinerU batch conversion + enrich (toc/l3/abstract) + embed + index
autor import-endnote <file.xml>

# Import multiple files
autor import-endnote file1.xml file2.ris

# Import metadata and PDFs only, skip MinerU conversion and enrichment
autor import-endnote <file.xml> --no-convert

# Preview mode
autor import-endnote <file.xml> --dry-run

# Offline mode
autor import-endnote <file.xml> --no-api
```

### Automatic PDF Matching

For Endnote XML files, automatically parses `internal-pdf://` links and matches PDFs from the `<library>.Data/PDF/` directory:
- When multiple PDFs are present, supplementary / SI files are automatically excluded
- Matched PDFs are converted to paper.md via MinerU batch conversion by default

### Automatic Post-Import Processing

Default behavior (without `--no-convert`) automatically runs the full pipeline after import:
1. **Batch PDF→MD**: cloud mode uses `convert_pdfs_cloud_batch()` for batch conversion (batch size controlled by `config.yaml` `ingest.mineru_batch_size`, default 20)
2. **Abstract backfill**: extracts missing abstracts from the Markdown
3. **TOC + L3 extraction**: LLM extracts table of contents and conclusion sections
4. **Embed + Index**: updates semantic vectors and full-text index

Use `--no-convert` to skip all post-processing (imports metadata + copies PDFs + embed + index only).

## Zotero Import

Supports both Web API and local SQLite modes.

### Web API Mode

```bash
# List collections
autor import-zotero --api-key KEY --library-id ID --list-collections

# Full import
autor import-zotero --api-key KEY --library-id ID

# Import a specific collection only
autor import-zotero --api-key KEY --library-id ID --collection COLLECTION_KEY

# Import and create workspaces from collections
autor import-zotero --api-key KEY --library-id ID --import-collections
```

### Local SQLite Mode

```bash
autor import-zotero --local /path/to/zotero.sqlite
```

### Config File (Optional)

Configure Zotero credentials in `config.local.yaml`:

```yaml
zotero:
  api_key: "your-zotero-api-key"
  library_id: "your-library-id"
```

## Attach a PDF to an Existing Paper

```bash
autor attach-pdf <paper-id> <path/to/paper.pdf>
```

Automatically calls MinerU to convert the PDF to Markdown, backfills any missing abstract, and incrementally updates the embed + index.

## Batch PDF Conversion for Already-Ingested Papers

For papers already in the library that are missing paper.md (e.g. imported with `--no-convert`), batch conversion can be triggered via Python:

```python
from autor.config import load_config
from autor.ingest.pipeline import batch_convert_pdfs

cfg = load_config()
stats = batch_convert_pdfs(cfg, enrich=True)
```

Automatically scans `data/papers/` for papers that have a PDF but no paper.md, runs batch cloud API conversion, then runs abstract backfill + toc + l3 + embed + index.
