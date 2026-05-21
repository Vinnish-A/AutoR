# Direction 2: Long-PDF Ingestion — Automatic Splitting and Merging Under MinerU Page Limits

## Problem Analysis

### Current Situation

MinerU has practical limits on how many pages it can parse in one request:
- **Cloud API**: the codebase does not currently enforce a page cap, but the MinerU cloud service does have one in practice (typically ~100 pages)
- **Local API**: `ConvertOptions` already includes `start_page` / `end_page` (0-indexed), but the pipeline **never uses them automatically**
- Very long documents (200-500 page dissertations, 500-1000+ page books) are likely to be rejected by MinerU or time out if submitted as-is

### Existing Infrastructure in the Code

**Page-range support already present in `mineru.py`:**

```python
# ConvertOptions (line 166-167)
start_page: int = 0
end_page: int = 99999

# Passed through in the local API call (line 246-247)
"start_page_id": (None, str(opts.start_page)),
"end_page_id": (None, str(opts.end_page)),
```

**However, the cloud API (`convert_pdf_cloud`) does not pass `start_page` / `end_page`** — its payload contains no page range.

**In `pipeline.py`, `step_mineru` calls `convert_pdf()` directly without checking page count.**

---

## Design Goals

1. **Fully transparent**: users drop a long PDF into the inbox and the pipeline handles it automatically
2. **Robust and maintainable**: split/merge logic must handle edge cases correctly, without introducing technical debt
3. **Consistent output**: regardless of length, the final `paper.md` and `meta.json` should match the normal paper structure
4. **Correct image references**: image paths extracted by MinerU must still resolve after merging
5. **Idempotent and resumable**: if the process fails halfway through, it should be possible to resume from where it left off

---

## Implementation Plan

### Overall Strategy: Split into Chunks → Parse → Merge Markdown

```
Long PDF (500 pages)
    ↓
Detect page count (PyMuPDF / pikepdf)
    ↓
If <= PAGE_LIMIT → use the existing flow directly
    ↓
If > PAGE_LIMIT → split into multiple page ranges of PAGE_LIMIT size
    ↓
Run MinerU on each chunk (reusing start_page/end_page support where applicable)
    ↓
Merge Markdown and strip image references
    ↓
Output a single paper.md without image artifacts
    ↓
Continue through the normal pipeline (extract → dedup → ingest)
```

### Option Comparison: Physical Splitting vs Page Ranges

| Option | Pros | Cons |
|--------|------|------|
| **A: Physically split the PDF** | Independent files; can be sent to the cloud API in parallel | Requires PyMuPDF/pikepdf; elements spanning pages may be cut across chunk boundaries |
| **B: Use page-range parameters** | No extra dependency required (already supported by the local API) | The cloud API may not support it; processing is serial |
| **Recommended: Hybrid A + B** | Use B for the local API and A for the cloud API | Two code paths to maintain |

**Recommended direction: physical splitting (Option A)**, because:
1. It gives the cloud API and local API a unified handling model
2. After splitting, the cloud API batch workflow can process chunks in parallel
3. PyMuPDF (`pymupdf`) is a lightweight dependency, and MinerU already relies on it indirectly

### Detailed Implementation

#### Step 1: Detect PDF page count (new in `mineru.py`)

```python
def _get_pdf_page_count(pdf_path: Path) -> int:
    """Return the page count of a PDF. Prefer pymupdf, fall back to pikepdf."""
    try:
        import pymupdf  # PyMuPDF
        with pymupdf.open(pdf_path) as doc:
            return len(doc)
    except ImportError:
        pass
    try:
        import pikepdf
        with pikepdf.open(pdf_path) as pdf:
            return len(pdf.pages)
    except ImportError:
        pass
    _log.warning("cannot detect page count (install pymupdf or pikepdf)")
    return -1  # unknown; fall back to the original flow
```

#### Step 2: Physically split the PDF (new in `mineru.py`)

```python
# Configurable page cap
DEFAULT_CHUNK_SIZE = 100  # Maximum pages per chunk

def _split_pdf(pdf_path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE,
               output_dir: Path | None = None) -> list[Path]:
    """Split a very long PDF into multiple shorter PDFs.

    Args:
        pdf_path: Path to the original PDF.
        chunk_size: Maximum number of pages per chunk.
        output_dir: Directory for split chunks. By default, create it next to the PDF.

    Returns:
        A list of chunk PDF paths in page order.
        If total pages <= chunk_size, returns [pdf_path] (no split).
    """
    import pymupdf

    page_count = _get_pdf_page_count(pdf_path)
    if page_count <= chunk_size:
        return [pdf_path]

    if output_dir is None:
        output_dir = pdf_path.parent / f".{pdf_path.stem}_chunks"
    output_dir.mkdir(parents=True, exist_ok=True)

    chunks = []
    with pymupdf.open(pdf_path) as src_doc:
        for start in range(0, page_count, chunk_size):
            end = min(start + chunk_size, page_count)  # exclusive
            chunk_name = f"{pdf_path.stem}_p{start:04d}-{end-1:04d}.pdf"
            chunk_path = output_dir / chunk_name

            if chunk_path.exists():
                # Idempotent behavior: reuse chunks that were already created
                chunks.append(chunk_path)
                continue

            chunk_doc = pymupdf.open()
            chunk_doc.insert_pdf(src_doc, from_page=start, to_page=end - 1)
            chunk_doc.save(str(chunk_path))
            chunk_doc.close()
            chunks.append(chunk_path)

    _log.info("split %s (%d pages) into %d chunks of %d pages",
              pdf_path.name, page_count, len(chunks), chunk_size)
    return chunks
```

#### Step 3: Merge Markdown output (new in `mineru.py`)

```python
def _merge_chunk_results(
    chunk_results: list[ConvertResult],
    original_pdf: Path,
    output_dir: Path,
) -> ConvertResult:
    """Merge MinerU output from multiple chunks into a single result.

    Handles:
    1. Concatenating Markdown text
    2. Deduplicating and merging image files (renaming to avoid collisions)
    3. Merging content_list data
    4. Aggregating errors from failed chunks

    Args:
        chunk_results: List of per-chunk ConvertResult objects, already sorted by page range.
        original_pdf: Path to the original full PDF.
        output_dir: Final output directory.

    Returns:
        The merged ConvertResult.
    """
    merged = ConvertResult(pdf_path=original_pdf)
    final_md_path = output_dir / (original_pdf.stem + ".md")
    final_images_dir = output_dir / "images"

    md_parts: list[str] = []
    errors: list[str] = []
    total_elapsed = 0.0
    image_counter = 0

    for idx, cr in enumerate(chunk_results):
        total_elapsed += cr.elapsed_seconds

        if not cr.success:
            errors.append(f"chunk {idx}: {cr.error}")
            continue

        if not cr.md_path or not cr.md_path.exists():
            errors.append(f"chunk {idx}: md file not found")
            continue

        chunk_md = cr.md_path.read_text(encoding="utf-8", errors="replace")

        # Strip image paths and discard image directories
        chunk_images_dir = cr.md_path.parent / "images"
        if not chunk_images_dir.exists():
            # MinerU may also write images to {stem}_mineru_images/
            chunk_images_dir = cr.md_path.parent / f"{cr.md_path.stem}_mineru_images"

        if chunk_images_dir.exists() and chunk_images_dir.is_dir():
            shutil.rmtree(chunk_images_dir, ignore_errors=True)
        chunk_md = strip_markdown_images(chunk_md)

        md_parts.append(chunk_md)

    if not md_parts:
        merged.error = "all chunks failed: " + "; ".join(errors)
        merged.elapsed_seconds = total_elapsed
        return merged

    # Concatenate Markdown without extra separators; MinerU output already carries its own headings
    final_md = "\n\n".join(md_parts)
    final_md_path.write_text(final_md, encoding="utf-8")

    merged.success = True
    merged.md_path = final_md_path
    merged.elapsed_seconds = total_elapsed

    if errors:
        _log.warning("some chunks failed during merge: %s", "; ".join(errors))

    return merged
```

#### Step 4: Integrate into `convert_pdf()` (modify `mineru.py`)

```python
def convert_pdf(pdf_path: Path, opts: ConvertOptions, *,
                chunk_size: int = DEFAULT_CHUNK_SIZE) -> ConvertResult:
    """Convert a PDF to Markdown. Long PDFs are split automatically."""
    result = ConvertResult(pdf_path=pdf_path)
    ...

    # === New: automatic splitting for long PDFs ===
    page_count = _get_pdf_page_count(pdf_path)
    if page_count > chunk_size:
        _log.info("long PDF detected (%d pages > %d limit), splitting...",
                  page_count, chunk_size)
        return _convert_long_pdf(pdf_path, opts, chunk_size=chunk_size)

    # === Existing logic ===
    ...


def _convert_long_pdf(pdf_path: Path, opts: ConvertOptions,
                      chunk_size: int = DEFAULT_CHUNK_SIZE) -> ConvertResult:
    """Handle a long PDF: split → convert per chunk → merge."""
    out_dir = opts.output_dir if opts.output_dir else pdf_path.parent
    chunks_dir = out_dir / f".{pdf_path.stem}_chunks"

    # 1. Split
    chunk_paths = _split_pdf(pdf_path, chunk_size=chunk_size,
                             output_dir=chunks_dir)

    # 2. Convert each chunk
    chunk_results = []
    for i, chunk_pdf in enumerate(chunk_paths):
        _log.info("converting chunk %d/%d: %s", i + 1, len(chunk_paths),
                  chunk_pdf.name)
        chunk_opts = ConvertOptions(
            api_url=opts.api_url,
            output_dir=chunks_dir,  # Write chunk output into the temp directory
            backend=opts.backend,
            lang=opts.lang,
            parse_method=opts.parse_method,
            formula_enable=opts.formula_enable,
            table_enable=opts.table_enable,
            save_content_list=opts.save_content_list,
            force=opts.force,
            dry_run=opts.dry_run,
        )
        # Call the original single-PDF conversion logic directly (no recursion)
        cr = _convert_single_pdf(chunk_pdf, chunk_opts)
        chunk_results.append(cr)

    # 3. Merge
    merged = _merge_chunk_results(chunk_results, pdf_path, out_dir)

    # 4. Clean up temp files
    if merged.success and chunks_dir.exists():
        shutil.rmtree(chunks_dir)
        _log.debug("cleaned up chunks dir: %s", chunks_dir)

    return merged
```

**Refactoring note:** extract the current core conversion logic from `convert_pdf()` into `_convert_single_pdf()`. Then `convert_pdf()` simply becomes: detect page count → dispatch to the single-PDF path or the long-PDF path.

#### Step 5: Cloud API batch parallelism (modify `mineru.py`)

```python
def _convert_long_pdf_cloud(pdf_path: Path, opts: ConvertOptions, *,
                            api_key: str, cloud_url: str,
                            chunk_size: int = DEFAULT_CHUNK_SIZE) -> ConvertResult:
    """Handle a long PDF through the cloud API: split → batch upload → merge."""
    out_dir = opts.output_dir if opts.output_dir else pdf_path.parent
    chunks_dir = out_dir / f".{pdf_path.stem}_chunks"

    # 1. Split
    chunk_paths = _split_pdf(pdf_path, chunk_size=chunk_size,
                             output_dir=chunks_dir)

    # 2. Process chunks in parallel with the existing batch API
    chunk_opts = ConvertOptions(
        output_dir=chunks_dir,
        backend=opts.backend,
        lang=opts.lang,
        parse_method=opts.parse_method,
        formula_enable=opts.formula_enable,
        table_enable=opts.table_enable,
        save_content_list=opts.save_content_list,
    )
    batch_results = convert_pdfs_cloud_batch(
        chunk_paths, chunk_opts,
        api_key=api_key, cloud_url=cloud_url,
    )

    # 3. Merge (chunk_paths is already in page order, and batch_results matches it)
    merged = _merge_chunk_results(batch_results, pdf_path, out_dir)

    # 4. Clean up
    if merged.success and chunks_dir.exists():
        shutil.rmtree(chunks_dir)

    return merged
```

**Key advantage:** by reusing `convert_pdfs_cloud_batch()`, a 500-page PDF can be split into five 100-page chunks and processed in parallel via the batch API, so total runtime is close to the runtime of a single chunk.

#### Step 6: Pipeline integration (modify `pipeline.py`)

**No changes required in `pipeline.py`.** Because the split/merge logic is encapsulated inside `convert_pdf()` / `convert_pdf_cloud()`, the public interface stays the same. When `step_mineru` calls `convert_pdf()` or `convert_pdf_cloud()`, long PDFs are detected and handled internally.

```python
# No changes needed in the current step_mineru code:
def step_mineru(ctx: InboxCtx) -> StepResult:
    ...
    result = convert_pdf(ctx.pdf_path, opts)  # Long PDFs are handled internally
    ...
```

#### Step 7: Configuration (modify `config.py`)

```python
@dataclass
class IngestConfig:
    ...
    chunk_page_limit: int = 100  # Split threshold for long PDFs

# Example config.yaml
ingest:
  chunk_page_limit: 100  # Maximum pages per chunk (default 100)
```

---

## Edge Cases

### 1. Tables/images spanning chunk boundaries

MinerU performs layout analysis page by page. After splitting the PDF, each chunk is parsed independently, so tables spanning pages may be cut apart.

**Mitigation strategy:** overlapping pages between chunks

```python
OVERLAP_PAGES = 2  # Make adjacent chunks overlap by 2 pages

def _split_pdf_with_overlap(pdf_path, chunk_size, overlap=OVERLAP_PAGES):
    """Split with overlap."""
    for start in range(0, page_count, chunk_size - overlap):
        end = min(start + chunk_size, page_count)
        ...
```

But overlap makes merge-time deduplication much more complicated. **Recommendation: do not add overlap initially**, because:
- for dissertations and books, 100-page chunks are already coarse enough that boundary problems should be relatively rare
- MinerU is not perfect at handling multi-page tables even without splitting
- keeping the first version simple is worth more than optimizing a low-frequency edge case

### 2. Partial chunk failures

```python
# Already handled in _merge_chunk_results:
if not md_parts:
    merged.error = "all chunks failed"  # All chunks failed → raise an error
elif errors:
    _log.warning("some chunks failed")  # Partial failure → warn, but merge successful chunks
```

**Recommended behavior:**
- All chunks failed → `StepResult.FAIL`
- Some chunks failed → merge the successful subset, emit a warning, continue the pipeline
- The user can retry with `--force`

### 3. Metadata extraction after splitting

**Unaffected.** `step_extract` reads metadata from the merged `paper.md`, which is already the full document at that point. The LLM call inside `RobustExtractor` only reads the first 50k characters, so total document length is not a problem.

### 4. Temporary file cleanup

```python
# Clean up after success
if merged.success:
    shutil.rmtree(chunks_dir)  # Remove .{stem}_chunks/

# Keep the directory after failure (useful for debugging and retrying)
# Because chunks_dir starts with a dot, the pipeline will not mistake it for a new inbox item
```

### 5. Disk space

A 100 MB PDF split into 5 chunks may temporarily consume ~500 MB (original PDF + 5 chunk PDFs + 5 chunk Markdown outputs). After a successful merge and cleanup, usage should drop back to ~120 MB (original PDF + merged Markdown + images).

**Recommendation:** check available disk space before splitting, and warn if free space is less than `PDF size × 6`.

### 6. PyMuPDF dependency

PyMuPDF (`pymupdf`) is an indirect MinerU dependency and is usually already installed. If it is missing:

```python
def _split_pdf(pdf_path, chunk_size, output_dir):
    try:
        import pymupdf
    except ImportError:
        raise ImportError(
            "pymupdf is required for splitting long PDFs. "
            "Install it with: pip install pymupdf"
        )
```

---

## Complete Change List

| File | Change | Estimated Size |
|------|--------|----------------|
| `ingest/mineru.py` | Add `_get_pdf_page_count()`, `_split_pdf()`, `_merge_chunk_results()`, `_convert_long_pdf()`, `_convert_long_pdf_cloud()` | ~200 lines |
| `ingest/mineru.py` | Refactor `convert_pdf()` to extract `_convert_single_pdf()` | ~20 lines changed |
| `ingest/mineru.py` | Update `convert_pdf_cloud()` to detect long PDFs | ~15 lines |
| `config.py` | Add `chunk_page_limit` to `IngestConfig` | ~3 lines |
| `config.yaml` | Add default value | ~2 lines |

**Total changes:** ~240 new lines + ~20 lines of refactoring

---

## Testing Strategy

```python
# tests/test_pdf_split.py

def test_get_page_count():
    """Test page-count detection."""


def test_split_short_pdf():
    """A short PDF (< chunk_size) should not be split and should return [original_path]."""


def test_split_long_pdf():
    """A 500-page PDF should be split into five 100-page chunks."""


def test_split_idempotent():
    """Running the split twice should not create duplicate files."""


def test_merge_markdown():
    """Multiple Markdown chunks should be merged correctly."""


def test_merge_images():
    """Image paths should be remapped correctly."""


def test_merge_partial_failure():
    """If some chunks fail, the successful ones should still merge."""


def test_convert_long_pdf_e2e():
    """End-to-end: long PDF → split → convert → merge → single paper.md."""
```

---

## Compatibility with the Existing Flow

- **Pipeline (`step_mineru`)**: no changes required; the split logic is encapsulated inside `convert_pdf()`
- **Cloud batch (`_process_inbox`)**: needs a small adjustment—if a long PDF is detected, remove it from the batch list and handle it separately
- **Metadata extraction**: unaffected (runs on the merged Markdown)
- **Image references**: guaranteed unique via renaming
- **CLI parameters**: optionally add `--chunk-size N`; default comes from config
