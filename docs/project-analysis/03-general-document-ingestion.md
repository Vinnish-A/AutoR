# Direction 3: General Document Ingestion — Making Non-Paper PDFs/Markdown Searchable

## Problem Analysis

### Current System Assumptions

autor’s ingestion pipeline is built around one core assumption: **everything being ingested is an academic paper**.

This shows up in several places:

1. **Metadata extraction** (`extractor.py`): extracts title / authors / year / DOI / journal — all paper-specific fields
2. **API enrichment** (`_api.py`): queries Crossref / S2 / OpenAlex — APIs that index academic publications
3. **Deduplication logic** (`step_dedup`): DOI-centric — non-paper documents usually do not have DOIs
4. **Fallback path** (`step_dedup`): no DOI → ask the LLM whether it is a thesis → if not, move it to `pending/` for manual handling
5. **Embeddings and retrieval** (`vectors.py`): builds vectors from `title + abstract` — non-paper documents may have neither

**Conclusion:** The current system has **no formal ingestion path** for non-paper documents (technical reports, lecture notes, standards, book chapters, personal notes, meeting minutes, etc.). In practice, they either get stuck in `pending/`, or the user has to invent a DOI just to bypass deduplication.

### User Scenarios

| Document Type | Characteristics | Example |
|---------------|-----------------|---------|
| Technical report | Has a title/author, but no DOI or journal | NASA Technical Report, NIST SP |
| Lecture notes / textbook chapter | Has a title, but may not have an author or year | MIT OCW lecture notes |
| Standards document | Has a standard number (ISO/GB), but no DOI | ISO 9001:2015 |
| Personal notes / draft | May have no title or author at all | Research log, meeting notes |
| Book | Has an ISBN, not a DOI | A standalone chapter from a monograph |
| White paper / industry report | Has a title and organization, but not academic metadata | McKinsey report |
| Preprint | Has an arXiv ID and may or may not have a DOI | arXiv:2301.12345 |

---

## Design Proposal

### Core Idea: Introduce `paper_type: "document"` and a Dedicated Ingestion Path

Rather than building a separate system, **reuse the existing infrastructure** and extend it with `paper_type`, so non-paper documents can plug into the same retrieval stack.

### Architecture Overview

```
data/inbox-doc/           ← New entry point
├── report.pdf
├── notes.md
└── slides.pdf
        ↓
    step_mineru            (PDF → MD, same as papers)
        ↓
    step_extract_doc       ← New step (replaces step_extract)
    │  Try standard extraction first
    │  → If it fails / is too sparse → let the LLM generate title + summary from full text
        ↓
    step_ingest_doc        ← Reuses step_ingest (skips DOI deduplication)
        ↓
    data/papers/{Author-Year-Title}/   (shared storage layout)
    ├── meta.json          (paper_type: "document")
    ├── paper.md
    └── images/
```

### Step 1: Add a `data/inbox-doc/` entry point

Like `data/inbox-thesis/`, add a dedicated inbox:

```python
# New in pipeline.py _process_inbox

# Process document inbox (data/inbox-doc/)
doc_inbox = cfg._root / "data" / "inbox-doc"
if doc_inbox.exists():
    _process_inbox(
        doc_inbox, papers_dir, pending_dir, existing_dois,
        per_file_steps_doc, global_steps, cfg, opts,
        is_document=True,  # New flag
    )
```

**Why add a new inbox instead of modifying the current one?**
- User intent is explicit: anything placed in `inbox-doc/` is a non-paper document, so no LLM guessing is needed
- It mirrors the `inbox-thesis/` design
- It does not affect the existing paper-ingestion flow

### Step 2: Let the LLM generate title + summary (core addition)

**Add `ingest/metadata/_doc_extract.py`:**

```python
"""
Metadata extraction for non-paper documents.

For general documents that do not have a usable title or abstract,
use the LLM to generate them from the full text.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autor.config import Config

from autor.ingest.metadata._models import PaperMetadata

_log = logging.getLogger(__name__)

# Upper bound on text sent to the LLM (context-window limit)
_MAX_TEXT_FOR_LLM = 60_000  # roughly 60k characters


def extract_document_metadata(
    md_path: Path,
    cfg: "Config",
    *,
    existing_meta: PaperMetadata | None = None,
) -> PaperMetadata:
    """Extract or generate metadata for a non-paper document.

    Flow:
    1. First try the standard regex-based extraction (may recover title, authors, etc.)
    2. Check whether the result is sufficient (must have at least a title)
    3. If not sufficient, call the LLM on the full text to generate title + summary

    Args:
        md_path: Path to the Markdown file.
        cfg: Global config.
        existing_meta: Existing metadata, if already available.

    Returns:
        The completed `PaperMetadata`.
    """
    from autor.ingest.extractor import RegexExtractor
    from autor.llm import call_llm

    # Step 1: Try the standard extractor first
    if existing_meta:
        meta = existing_meta
    else:
        extractor = RegexExtractor()
        meta = extractor.extract(md_path)

    text = md_path.read_text(encoding="utf-8", errors="replace")

    # Step 2: Check whether LLM completion is needed
    has_title = bool((meta.title or "").strip())
    has_abstract = bool((meta.abstract or "").strip())

    if has_title and has_abstract:
        _log.debug("document already has title and abstract, skipping LLM")
        meta.paper_type = meta.paper_type or "document"
        return meta

    # Step 3: Ask the LLM to generate title and summary
    api_key = cfg.resolved_llm_api_key()
    if not api_key:
        _log.warning("no LLM API key, cannot generate title/abstract for document")
        if not has_title:
            # Final fallback: use the filename as the title
            meta.title = md_path.stem.replace("-", " ").replace("_", " ")
        meta.paper_type = meta.paper_type or "document"
        return meta

    truncated = text[:_MAX_TEXT_FOR_LLM]

    prompt = _build_prompt(truncated, has_title=has_title, has_abstract=has_abstract,
                           existing_title=meta.title)

    try:
        result = call_llm(prompt, cfg, purpose="doc_extract", max_tokens=1000)
        data = _parse_llm_response(result)

        if not has_title and data.get("title"):
            meta.title = data["title"]

        if not has_abstract and data.get("summary"):
            meta.abstract = data["summary"]

        if data.get("authors"):
            meta.authors = data["authors"]
            meta.first_author = data["authors"][0] if data["authors"] else ""

        if data.get("year") and not meta.year:
            meta.year = data["year"]

        if data.get("document_type"):
            meta.paper_type = data["document_type"]
        else:
            meta.paper_type = "document"

    except Exception as e:
        _log.warning("LLM document extraction failed: %s", e)
        if not has_title:
            meta.title = md_path.stem.replace("-", " ").replace("_", " ")
        meta.paper_type = meta.paper_type or "document"

    return meta


def _build_prompt(text: str, *, has_title: bool, has_abstract: bool,
                  existing_title: str = "") -> str:
    """Build the LLM prompt."""
    tasks = []
    if not has_title:
        tasks.append("1. Generate a concise, descriptive **title** for this document")
    if not has_abstract:
        tasks.append(
            f"{'2' if not has_title else '1'}. Write a **summary** (150-300 words) "
            "that captures the main content, key points, and purpose of this document. "
            "This summary will be used as the document's abstract for search indexing."
        )

    task_str = "\n".join(tasks)

    return (
        "You are analyzing a document (not necessarily an academic paper). "
        "It could be a technical report, lecture notes, manual, standard, "
        "book chapter, or any other type of document.\n\n"
        f"Your tasks:\n{task_str}\n\n"
        "Also extract if present:\n"
        "- **authors**: list of author/editor names\n"
        "- **year**: publication/creation year\n"
        "- **document_type**: one of: technical-report, lecture-notes, "
        "standard, book-chapter, manual, white-paper, presentation, "
        "meeting-notes, or document (generic fallback)\n\n"
        f"{'Existing title: ' + existing_title + chr(10) if existing_title else ''}"
        "Respond in JSON format:\n"
        "```json\n"
        "{\n"
        '  "title": "...",\n'
        '  "summary": "...",\n'
        '  "authors": ["..."],\n'
        '  "year": 2024,\n'
        '  "document_type": "..."\n'
        "}\n"
        "```\n\n"
        "--- DOCUMENT CONTENT ---\n\n"
        f"{text}"
    )


def _parse_llm_response(text: str) -> dict:
    """Extract JSON from the LLM response."""
    import json
    import re

    # Extract a ```json ... ``` block
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))

    # Try parsing JSON directly
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))

    return {}
```

### Step 3: Update the pipeline flow

**Add `step_extract_doc` to `pipeline.py`:**

```python
def step_extract_doc(ctx: InboxCtx) -> StepResult:
    """Metadata extraction for non-paper documents (replaces step_extract + step_dedup)."""
    if not ctx.md_path or not ctx.md_path.exists():
        return StepResult.SKIP

    from autor.ingest.metadata._doc_extract import extract_document_metadata

    try:
        meta = extract_document_metadata(ctx.md_path, ctx.cfg)
    except Exception as e:
        _log.error("document extraction failed: %s", e)
        ctx.status = "failed"
        return StepResult.FAIL

    if not (meta.title or "").strip():
        _log.error("cannot determine document title")
        ctx.status = "failed"
        return StepResult.FAIL

    ctx.meta = meta
    ctx.meta.paper_type = ctx.meta.paper_type or "document"
    return StepResult.OK
```

**Document inbox uses a different step sequence:**

```python
# Step sequence for document ingestion (skip dedup/API lookup)
DOC_STEPS = ["mineru", "extract_doc", "ingest"]
```

**Inside `_process_inbox()`:**

```python
def _process_inbox(inbox_dir, papers_dir, pending_dir, existing_dois,
                   per_file_steps, global_steps, cfg, opts,
                   is_thesis=False, is_document=False):
    ...
    if is_document:
        per_file_steps = ["mineru", "extract_doc", "ingest"]
    ...
```

### Step 4: Document deduplication strategy

Non-paper documents do not have DOIs, so they need a replacement deduplication mechanism:

```python
def _dedup_document(meta: PaperMetadata, existing_papers: dict) -> bool:
    """Deduplicate documents by title similarity.

    Returns:
        True if this document is a duplicate.
    """
    from difflib import SequenceMatcher

    if not meta.title:
        return False

    title_lower = meta.title.lower().strip()
    for existing_name, existing_meta in existing_papers.items():
        existing_title = (existing_meta.get("title") or "").lower().strip()
        if not existing_title:
            continue

        # Exact match
        if title_lower == existing_title:
            return True

        # Fuzzy match (threshold 0.9; stricter than papers because there is no DOI)
        ratio = SequenceMatcher(None, title_lower, existing_title).ratio()
        if ratio > 0.9:
            _log.info("document title similar to existing '%s' (%.2f), skipping",
                      existing_name, ratio)
            return True

    return False
```

### Step 5: Make sure the retrieval path works end to end

**Embedding construction (`vectors.py`):**

The current code can already handle non-paper documents:

```python
# Embedding logic in vectors.py
text = f"{title}\n\n{abstract}"
if not abstract:
    text = title  # title-only embeddings still work
```

Once the LLM-generated summary is written into the `abstract` field of `meta.json`, semantic search works naturally.

**FTS5 indexing (`index.py`):**

```python
# index.py build_index() indexes these fields:
# title, authors, year, journal, abstract, conclusion
# For non-paper documents, title + abstract (LLM-generated) will both be indexed
```

**No changes are required to the current indexing logic.**

**BibTeX export (`export.py`):**

```python
# Add mappings for document-style types
TYPE_MAP = {
    ...
    "document": "@misc",
    "technical-report": "@techreport",
    "book-chapter": "@inbook",
    "manual": "@manual",
    "lecture-notes": "@misc",
    "standard": "@misc",
    "white-paper": "@misc",
}
```

### Step 6: Direct Markdown ingestion (no MinerU needed)

Users may place `.md` files directly into `inbox-doc/`:

```python
# Existing logic in _process_inbox() already handles this:
# If inbox contains an .md file but no matching .pdf, skip the MinerU step
# step_mineru checks whether md_path already exists; if so, it returns SKIP
```

**No changes needed.** If the user drops in a `.md` file directly, `step_mineru` is skipped automatically and the flow proceeds to `step_extract_doc`.

### Step 7: Extend `meta.json` fields

```python
# Example meta.json for a non-paper document
{
    "id": "uuid-...",
    "title": "Title generated by the LLM / extracted from the filename",
    "authors": ["Author Name"],              # May be empty
    "year": 2024,                             # May be null
    "doi": "",                               # Empty
    "journal": "",                           # Empty
    "abstract": "LLM-generated 150-300 word summary",  # Critical for retrieval quality
    "paper_type": "document",                # Or technical-report, lecture-notes, etc.
    "extraction_method": "llm_document",     # Marks the source
    "source_file": "original-filename.pdf",

    # Keep the following fields empty for schema consistency
    "volume": "",
    "issue": "",
    "pages": "",
    "publisher": "",
    "issn": "",
    "citation_count": {},
    "ids": {},
    "references": [],
    "api_sources": []
}
```

---

## Complete Change List

| File | Change | Estimated Size |
|------|--------|----------------|
| **New** `ingest/metadata/_doc_extract.py` | LLM-based document metadata extraction | ~180 lines |
| `ingest/pipeline.py` | Add `step_extract_doc`, support `is_document` in `_process_inbox`, process `inbox-doc` | ~60 lines |
| `ingest/pipeline.py` | Add `_dedup_document()` for title-based deduplication | ~30 lines |
| `config.py` | Add `data/inbox-doc/` to `ensure_dirs()` | ~2 lines |
| `export.py` | Extend `TYPE_MAP` | ~8 lines |
| `cli.py` | Show the new step in pipeline `--list` output | ~5 lines |
| `.claude/skills/ingest/SKILL.md` | Documentation update | docs |

**Total changes:** ~285 new lines

---

## Fallback Strategy (No LLM API Key)

If the user has not configured an LLM API key:

1. **Title:** derive it from the filename (`technical-report_2024.pdf` → `"technical report 2024"`)
2. **Summary:** take the first 500 words of the Markdown (similar to the existing `_extract_abstract_from_md()`)
3. **paper_type:** default to `"document"`
4. **Author/year:** try to recover them from the filename via regex (e.g. `Smith-2024-Report.pdf`)

```python
# Fallback path
def _fallback_document_metadata(md_path: Path) -> PaperMetadata:
    """Minimal metadata extraction when no LLM is available."""
    text = md_path.read_text(encoding="utf-8", errors="replace")

    # Title: first Markdown heading or filename
    title = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            title = line.lstrip("# ").strip()
            break
    if not title:
        title = md_path.stem.replace("-", " ").replace("_", " ")

    # Summary: first 500 words
    words = text.split()[:500]
    abstract = " ".join(words)

    return PaperMetadata(
        title=title,
        abstract=abstract,
        paper_type="document",
    )
```

---

## Interaction with the Existing System

### Search

```bash
# Non-paper documents and papers share the same search space
autor search "drag reduction"           # FTS5, will match title/abstract from documents too
autor vsearch "drag reduction"          # Semantic search, using the LLM-generated summary
autor usearch "drag reduction"          # Hybrid search

# You can filter by paper_type
autor search "report" --type document   # Search non-paper documents only
autor search "report" --type article    # Search papers only
```

### Workspace

Non-paper documents can be added to workspaces just like papers:

```bash
autor workspace add my-project <document-uuid>
```

### Audit

```python
# audit.py needs a small adjustment: for entries where paper_type == "document"
# do not emit a missing_doi warning (documents are not expected to have a DOI)
if meta.get("paper_type") in ("document", "technical-report", "lecture-notes",
                               "standard", "manual", "white-paper"):
    # skip DOI warning
    pass
```

### Citation graph

Non-paper documents do not have DOIs, so they cannot participate in the citation graph. That is expected behavior—the citation graph is fundamentally a network of academic publications.

---

## Future Extensions

### ISBN support (books)

```python
# In the future, _doc_extract.py could detect ISBNs
# and use the Google Books API or Open Library API for metadata enrichment
isbn_pattern = r"(?:ISBN[-: ]?)?(?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx]"
```

### arXiv ID support (preprints)

```python
# Detect arXiv IDs and enrich metadata through the arXiv API
arxiv_pattern = r"(?:arXiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)"
# https://export.arxiv.org/api/query?id_list=2301.12345
```

### Segment-level embeddings (long documents)

For very long documents (100+ pages), a single `title + abstract` embedding may not represent the full content well enough. In the future:

```python
# Split by section/paragraph and embed each segment independently
# At search time, return the document that contains the most relevant segment
# This requires changing the vectors.py data model (currently 1 paper = 1 vector)
```

This is a larger architectural change and should be planned as a separate workstream.

---

## Testing Strategy

```python
# tests/test_doc_ingest.py

def test_extract_doc_with_title_and_abstract():
    """If the document already has title and abstract, do not call the LLM."""


def test_extract_doc_missing_title():
    """If the document has no title, the LLM should generate one."""


def test_extract_doc_missing_abstract():
    """If the document has no abstract, the LLM should generate the summary."""


def test_extract_doc_no_llm_fallback():
    """Fallback path when no LLM API key is configured."""


def test_dedup_document_exact_title():
    """Documents with identical titles should be deduplicated."""


def test_dedup_document_similar_title():
    """Documents with highly similar titles (>0.9) should be deduplicated."""


def test_doc_in_search_results():
    """Documents should be discoverable through FTS5 / FAISS / unified search."""


def test_doc_bibtex_export():
    """Documents should export as @misc BibTeX entries."""


def test_doc_audit_no_doi_warning():
    """Document types should not trigger missing_doi warnings."""
```
