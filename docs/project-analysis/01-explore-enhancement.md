# Direction 1: Enhancing the Explore Module and Making It More General-Purpose

## Current State Analysis

### Current Explore Module Architecture

`explore.py` currently supports only **one data source**: pulling the complete paper set for a single journal from OpenAlex via ISSN.

```
fetch_journal(name, issn) → data/explore/<name>/papers.jsonl
                          → explore.db (paper_vectors)
                          → faiss.index + faiss_ids.json
                          → topic_model/ (BERTopic)
```

**Core workflow:**

1. `_fetch_page()` — uses `primary_location.source.issn:{issn}` as the filter and pulls the OpenAlex `/works` endpoint page by page with cursors
2. Writes JSONL output (`title`, `abstract`, `authors`, `year`, `doi`, `cited_by_count`, `type`)
3. `build_explore_vectors()` — generates Qwen3 embeddings and stores them in the `paper_vectors` table in `explore.db`
4. `build_explore_topics()` — clusters papers with BERTopic (reusing `topics.py` via the `papers_map` parameter)
5. `explore_vsearch()` — performs FAISS-based semantic search

### Existing Limitations

| Limitation | Details |
|------------|---------|
| **Only supports journal queries by ISSN** | Cannot explore by topic, author, institution, conference, or other dimensions |
| **Single data source** | Only OpenAlex; no path to integrate Semantic Scholar, Crossref, or arXiv |
| **No keyword search** | The explore corpus has FAISS semantic search only, with no FTS5 keyword search |
| **No hybrid retrieval** | The main library has `unified_search()` (RRF fusion), but explore corpora do not |
| **No incremental updates** | `fetch_journal()` always pulls the full corpus and cannot fetch only newly published papers |
| **Flat FAISS index** | `IndexFlatIP` becomes slower once the corpus grows beyond 100k papers |
| **No cross-library search** | Cannot search across the main library, one explore corpus, and multiple explore corpora together |

---

## Enhancement Plan

### Enhancement 1: Multi-Dimensional OpenAlex Queries (Top Priority)

**Goal:** Generalize `fetch_journal` into `fetch_explore` so it supports multiple filter dimensions.

**OpenAlex already supports rich filter combinations; the current code uses only `primary_location.source.issn`.**

#### Implementation

**1) Expand `fetch_journal()` into `fetch_explore()`**

```python
# New in explore.py

def fetch_explore(
    name: str,
    *,
    issn: str | None = None,           # Journal ISSN (backward-compatible)
    concept: str | None = None,        # OpenAlex concept ID (e.g. "C41008148" = Computer Science)
    topic: str | None = None,          # OpenAlex topic ID
    author: str | None = None,         # OpenAlex author ID (e.g. "A5023888391")
    institution: str | None = None,    # OpenAlex institution ID (e.g. "I27837315" = MIT)
    keyword: str | None = None,        # Keyword search over title/abstract
    source_type: str | None = None,    # journal / conference / repository
    year_range: str | None = None,
    min_citations: int | None = None,  # Lower bound on cited_by_count
    cfg: Config | None = None,
) -> int:
```

**2) Build a flexible filter string**

```python
def _build_filter(*, issn=None, concept=None, topic=None, author=None,
                  institution=None, keyword=None, source_type=None,
                  year_range=None, min_citations=None) -> tuple[str, dict]:
    """Build the OpenAlex filter string plus any extra query params."""
    parts = []
    extra_params = {}

    if issn:
        parts.append(f"primary_location.source.issn:{issn}")
    if concept:
        parts.append(f"concepts.id:{concept}")
    if topic:
        parts.append(f"topics.id:{topic}")
    if author:
        parts.append(f"authorships.author.id:{author}")
    if institution:
        parts.append(f"authorships.institutions.id:{institution}")
    if source_type:
        parts.append(f"primary_location.source.type:{source_type}")
    if year_range:
        parts.append(f"publication_year:{year_range}")
    if min_citations is not None:
        parts.append(f"cited_by_count:>{min_citations}")

    if keyword:
        extra_params["search"] = keyword  # OpenAlex search parameter

    return ",".join(parts), extra_params
```

**3) Let `_fetch_page()` accept a general filter**

The current `_fetch_page(issn, page, year_range, cursor)` becomes `_fetch_page(filt, extra_params, cursor)`.

**4) Store the full query in `meta.json`**

```python
# Record the full query in meta.json so incremental updates are possible later
{
    "name": "turbulence-2020",
    "query": {
        "concept": "C62520636",      # Turbulence
        "year_range": "2020-2025",
        "min_citations": 10
    },
    "count": 3200,
    "fetched_at": "2026-03-10T..."
}
```

**5) Expand the CLI**

```bash
# By concept / field
autor explore fetch --name turbulence --concept C62520636 --year-range 2020-2025

# By institution
autor explore fetch --name mit-ml --institution I27837315 --concept C41008148

# By author
autor explore fetch --name hinton-works --author A5048491430

# By keyword
autor explore fetch --name drag-reduction --keyword "drag reduction" --year-range 2015-2025

# Mixed filters
autor explore fetch --name jfm-review --issn 0022-1120 --source-type journal --min-citations 50
```

**Files to change:**
- `explore.py`: update the `_fetch_page()` signature, add `fetch_explore()` as a wrapper/generalization of `fetch_journal()`, and keep `fetch_journal()` as a backward-compatible alias
- `cli.py`: add new options to the `fetch` subcommand under `cmd_explore`
- `.claude/skills/explore/SKILL.md`: update the documentation

**Estimated size:** ~150 lines of Python + CLI argument definitions

---

### Enhancement 2: FTS5 + Hybrid Retrieval for Explore Corpora

**Goal:** Give explore corpora the same keyword + semantic hybrid retrieval ability as the main library.

**Current problem:** `explore_vsearch()` is semantic-only. That works poorly for exact matches such as paper titles, author names, or highly specific terms.

#### Implementation

**1) Create an FTS5 virtual table in `explore.db`**

```python
# New in explore.py
def _ensure_fts(db_path: Path):
    """Create the FTS5 index inside explore.db."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
                paper_id UNINDEXED,
                title,
                authors,
                year UNINDEXED,
                abstract,
                tokenize='unicode61'
            )
        """)
```

**2) Build FTS5 alongside `build_explore_vectors()`**

During the current embedding build process, also write the data from `papers.jsonl` into the FTS5 table.

Incremental logic: compare the row count in `papers_fts` against the line count in `papers.jsonl`.

**3) Add `explore_search()` and `explore_unified_search()`**

```python
def explore_search(name: str, query: str, *, top_k: int = 20, cfg=None) -> list[dict]:
    """Run FTS5 keyword search against an explore corpus."""
    ...

def explore_unified_search(name: str, query: str, *, top_k: int = 20, cfg=None) -> list[dict]:
    """Run RRF-based hybrid search over an explore corpus (FTS5 + FAISS)."""
    # Reuse the RRF merge logic from index.py
    fts_results = explore_search(name, query, top_k=top_k, cfg=cfg)
    vec_results = explore_vsearch(name, query, top_k=top_k, cfg=cfg)
    return _rrf_merge(fts_results, vec_results, top_k=top_k)
```

**4) Expand the CLI**

```bash
autor explore search --name jfm "drag reduction"                   # semantic (current behavior)
autor explore search --name jfm "drag reduction" --mode keyword    # keyword
autor explore search --name jfm "drag reduction" --mode unified    # hybrid
```

**Files to change:**
- `explore.py`: add ~100 lines (FTS5 construction + keyword search + hybrid search)
- `cli.py`: add a `--mode` option to the `explore search` subcommand

---

### Enhancement 3: Incremental Updates

**Goal:** When an explore corpus already exists, fetch only new papers instead of refetching everything.

#### Implementation

```python
def fetch_explore(name, ..., incremental: bool = True):
    meta_path = explore_dir / "meta.json"
    if incremental and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        last_fetched = meta.get("fetched_at", "")
        # OpenAlex supports the from_updated_date filter
        # publication_year can also be used as a coarser incremental strategy
        if last_fetched:
            extra_filter = f",from_updated_date:{last_fetched[:10]}"
    ...
    # Append to papers.jsonl instead of overwriting it
    # Deduplicate by DOI by loading the existing DOI set first
    existing_dois = _load_existing_dois(jsonl_path)
    ...
```

**Key points:**
- OpenAlex supports both `from_updated_date` and `from_created_date`
- Append to JSONL and deduplicate by DOI
- After an incremental pull, rebuild FTS5 + FAISS (append only for new records)
- Update `fetched_at` and `count` in `meta.json`

**Estimated size:** ~80 lines

---

### Enhancement 4: Cross-Library Search (Medium Priority)

**Goal:** Search across multiple explore corpora and the main library in one query.

```python
def cross_search(query: str, *, sources: list[str] | None = None,
                 top_k: int = 20, cfg=None) -> list[dict]:
    """Search across libraries. sources is a list of explore corpus names; None means search all."""
    results = []

    # 1. Search the main library
    main_results = unified_search(query, top_k=top_k, cfg=cfg)
    for r in main_results:
        r["source"] = "main"
    results.extend(main_results)

    # 2. Search all or selected explore corpora
    for explore_name in _list_explore_libs(cfg):
        if sources and explore_name not in sources:
            continue
        try:
            er = explore_unified_search(explore_name, query, top_k=top_k, cfg=cfg)
            for r in er:
                r["source"] = f"explore:{explore_name}"
            results.extend(er)
        except Exception:
            continue

    # 3. Re-rank with RRF
    return _rrf_merge_multi(results, top_k=top_k)
```

This can be deferred, because it depends on Enhancement 2 (hybrid retrieval for explore corpora).

---

### Enhancement 5: FAISS Optimization for Large Corpora (Low Priority)

The current `IndexFlatIP` is good enough for corpora under 100k papers. If explore corpora eventually grow to the million-paper scale:

```python
def _build_faiss_index(vectors, ids, *, large_scale: bool = False):
    if large_scale and len(vectors) > 100_000:
        # IVF index: train + quantize
        quantizer = faiss.IndexFlatIP(dim)
        nlist = min(int(len(vectors) ** 0.5), 4096)
        index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
        index.train(vectors)
        index.add(vectors)
        index.nprobe = min(nlist // 4, 64)
    else:
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
    return index
```

**Recommendation:** Do not implement this yet. The current use case (a full single-journal corpus is typically ~5k-50k papers) does not require it. A future `config.yaml` option such as `explore.faiss_type: flat | ivf` would be enough for now.

---

## Recommended Implementation Order

| Priority | Enhancement | Estimated Work | Benefit |
|----------|-------------|----------------|---------|
| P0 | Multi-dimensional OpenAlex queries | ~150 lines | Turns explore from "journal exploration" into "field-wide exploration" |
| P1 | FTS5 + hybrid retrieval | ~100 lines | Improves exact lookup and aligns explore with the main library |
| P2 | Incremental updates | ~80 lines | Avoids refetching the same data and reduces API usage |
| P3 | Cross-library search | ~60 lines | Provides a global view; depends on P1 |
| P4 | FAISS optimization | ~30 lines | Only necessary at larger scale |

**Total estimated change size:** ~400 lines of Python + CLI args + skill documentation updates

---

## Compatibility and Migration

- Keep `fetch_journal()` as an alias for `fetch_explore(issn=issn)`, so this is **non-breaking**
- Existing explore corpora (`papers.jsonl`) keep the same format
- The FTS5 table is additive, so existing `explore.db` files are unaffected (create it lazily on first search)
- All new CLI parameters are optional, so current usage continues to work
