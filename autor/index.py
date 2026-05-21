"""
index.py — SQLite FTS5 可审计证据索引
=======================================

索引包括论文级 metadata/registry 表、引用图表，以及从 ``meta.json`` 和
``paper.md`` 生成的 ``paper_nodes`` / ``paper_node_fts`` 节点级证据索引。
检索结果保留 evidence snippet 和 ref_path，供 answer-time provenance 使用。

用法：
    from autor.index import build_index, search
    build_index(papers_dir, db_path)
    results = search("turbulent boundary layer", db_path)
    bundle = research_bundle("What evidence supports ...?", db_path)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from autor.papers import best_citation, parse_year_range

if TYPE_CHECKING:
    from autor.config import Config

_log = logging.getLogger(__name__)

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS papers USING fts5(
    paper_id       UNINDEXED,
    title,
    authors,
    year,
    journal,
    abstract,
    conclusion,
    doi            UNINDEXED,
    paper_type     UNINDEXED,
    citation_count UNINDEXED,
    md_path        UNINDEXED,
    tokenize       = 'unicode61'
);
"""


_HASH_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers_hash (
    paper_id     TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL
);
"""

_REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers_registry (
    id                   TEXT PRIMARY KEY,
    dir_name             TEXT NOT NULL UNIQUE,
    title                TEXT,
    doi                  TEXT,
    pmid                 TEXT,
    publication_number   TEXT,
    year                 INTEGER,
    first_author         TEXT
);
"""

_REGISTRY_DOI_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_doi
    ON papers_registry(doi) WHERE doi IS NOT NULL AND doi != '';
"""

_REGISTRY_PUBNUM_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_publication_number
    ON papers_registry(publication_number) WHERE publication_number IS NOT NULL AND publication_number != '';
"""

_REGISTRY_PMID_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_pmid
    ON papers_registry(pmid) WHERE pmid IS NOT NULL AND pmid != '';
"""

_REGISTRY_TITLE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_registry_title_exact
    ON papers_registry(LOWER(TRIM(title))) WHERE title IS NOT NULL AND title != '';
"""

_CITATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS citations (
    source_id   TEXT NOT NULL,
    target_doi  TEXT NOT NULL,
    target_id   TEXT,
    PRIMARY KEY (source_id, target_doi)
);
"""
_CITATIONS_IDX_TARGET_DOI = "CREATE INDEX IF NOT EXISTS idx_cit_target_doi ON citations(target_doi);"
_CITATIONS_IDX_TARGET_ID = (
    "CREATE INDEX IF NOT EXISTS idx_cit_target_id ON citations(target_id) WHERE target_id IS NOT NULL;"
)

_NODE_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_nodes (
    node_id      TEXT PRIMARY KEY,
    paper_id     TEXT NOT NULL,
    dir_name     TEXT NOT NULL,
    ordinal      INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    section      TEXT NOT NULL,
    title        TEXT NOT NULL,
    ref_path     TEXT NOT NULL,
    prev_id      TEXT,
    next_id      TEXT,
    content      TEXT NOT NULL,
    tokens       TEXT NOT NULL,
    content_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_paper_nodes_paper_id ON paper_nodes(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_nodes_prev_id ON paper_nodes(prev_id);
CREATE INDEX IF NOT EXISTS idx_paper_nodes_next_id ON paper_nodes(next_id);
"""

_NODE_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS paper_node_fts USING fts5(
    node_id  UNINDEXED,
    paper_id UNINDEXED,
    tokens,
    tokenize = 'unicode61'
);
"""


def _index_hash(meta: dict) -> str:
    """Compute a short hash of the fields indexed in FTS5."""
    parts = [
        meta.get("title") or "",
        ", ".join(meta.get("authors") or []),
        str(meta.get("year") or ""),
        meta.get("journal") or "",
        meta.get("abstract") or "",
        json.dumps(meta.get("l3") or {}, sort_keys=True, ensure_ascii=False),
        meta.get("doi") or "",
        meta.get("pmid") or ((meta.get("ids") or {}).get("pmid", "") or ""),
        meta.get("paper_type") or "",
        ((meta.get("ids") or {}).get("patent_publication_number", "") or ""),
    ]
    cc = meta.get("citation_count")
    if cc and isinstance(cc, dict):
        vals = [v for v in cc.values() if isinstance(v, (int, float))]
        parts.append(str(max(vals)) if vals else "")
    parts.append(json.dumps(meta.get("references", []), sort_keys=True))
    text = "\n".join(parts)
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def _render_l3_index_text(meta: dict) -> str:
    """Return compact text from the structured L3 record for indexing."""
    l3 = meta.get("l3")
    if not isinstance(l3, dict):
        return ""
    parts: list[str] = []
    for key in ("takeaway", "confidence", "mode"):
        value = l3.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    for key in ("key_findings", "quantitative_signals", "limitations"):
        value = l3.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = " ".join(str(v).strip() for v in item.values() if str(v).strip())
            else:
                text = str(item).strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _text_hash(text: str) -> str:
    """Compute a short hash for node-level evidence text."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x3040 <= code <= 0x30FF
        or 0xAC00 <= code <= 0xD7AF
    )


def _fts_tokens(text: str) -> list[str]:
    """Tokenize text into ASCII words plus CJK 2-grams for deterministic FTS."""
    tokens: list[str] = []
    seen: set[str] = set()
    cjk_run: list[str] = []

    def add(token: str) -> None:
        token = token.strip().lower()
        if not token or token in seen:
            return
        seen.add(token)
        tokens.append(token)

    def flush_cjk() -> None:
        nonlocal cjk_run
        if not cjk_run:
            return
        if len(cjk_run) == 1:
            add(cjk_run[0])
        else:
            for i in range(len(cjk_run) - 1):
                add("".join(cjk_run[i : i + 2]))
        cjk_run = []

    for part in re.finditer(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", str(text or "")):
        raw = part.group(0)
        if len(raw) == 1 and _is_cjk(raw):
            cjk_run.append(raw)
            continue
        flush_cjk()
        if re.match(r"^[A-Za-z0-9_]+$", raw):
            add(raw)
    flush_cjk()
    return tokens


def _quote_fts_token(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _build_node_match(query: str, *, query_mode: str = "or", require_terms: list[str] | None = None) -> str:
    """Build a safe FTS5 expression over pre-tokenized node text."""
    tokens = _fts_tokens(query)
    if not tokens:
        return ""
    joiner = " AND " if str(query_mode or "or").lower() == "and" else " OR "
    expr = joiner.join(_quote_fts_token(t) for t in tokens[:64])
    required: list[str] = []
    for term in require_terms or []:
        required.extend(_fts_tokens(term))
    required_expr = " AND ".join(_quote_fts_token(t) for t in required[:32])
    if required_expr:
        return f"{required_expr} AND ({expr})"
    return expr


def _extract_snippet(text: str, terms: list[str], *, max_chars: int = 360) -> str:
    """Return a deterministic evidence window around the first query-term hit."""
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(clean) <= max_chars:
        return clean
    low = clean.lower()
    positions = [low.find(t.lower()) for t in terms if t and low.find(t.lower()) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - max_chars // 3)
    end = min(len(clean), start + max_chars)
    start = max(0, end - max_chars)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(clean) else ""
    return prefix + clean[start:end].strip() + suffix


def _normalize_doi(value: str | None) -> str:
    """Normalize DOI strings for exact registry matching."""
    text = str(value or "").strip()
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE).strip()
    return text.lower()


def _normalize_pmid(value: str | None) -> str:
    """Normalize PubMed IDs from raw inputs, prefixes, or URLs."""
    text = str(value or "").strip()
    if not text:
        return ""
    url_match = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", text, re.IGNORECASE)
    if url_match:
        return url_match.group(1)
    text = re.sub(r"^pmid:\s*", "", text, flags=re.IGNORECASE).strip()
    return text if text.isdigit() else ""


def _escape_like(value: str) -> str:
    """Escape a string for SQLite LIKE prefix matching."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _lookup_registry_dir_prefix(conn: sqlite3.Connection, prefixes: list[str]) -> sqlite3.Row | None:
    """Find a registry row by dir_name prefix, preferring non-DUP entries."""
    seen: set[str] = set()
    for prefix in prefixes:
        prefix = prefix.strip()
        if not prefix or prefix in seen:
            continue
        seen.add(prefix)
        row = conn.execute(
            """
            SELECT * FROM papers_registry
            WHERE dir_name LIKE ? ESCAPE '\\'
            ORDER BY
                CASE WHEN dir_name LIKE 'DUP-%' THEN 1 ELSE 0 END,
                LENGTH(dir_name),
                dir_name
            LIMIT 1
            """,
            (_escape_like(prefix) + "%",),
        ).fetchone()
        if row:
            return row
    return None


def _normalize_exact_title(value: str | None) -> str:
    """Normalize titles for case-insensitive exact matching."""
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _create_partial_index_with_fallback(
    conn: sqlite3.Connection,
    *,
    unique_sql: str,
    fallback_sql: str,
    label: str,
) -> None:
    """Create a partial UNIQUE index, falling back to a non-unique one on duplicates."""
    try:
        conn.execute(unique_sql)
    except sqlite3.OperationalError:
        pass
    except sqlite3.IntegrityError:
        _log.warning(
            "cannot create UNIQUE index on %s: duplicate values exist; falling back to non-unique index",
            label,
        )
        try:
            conn.execute(fallback_sql)
        except sqlite3.OperationalError:
            pass


def _ensure_registry_indexes(conn: sqlite3.Connection) -> None:
    """Ensure exact-match indexes exist on the current registry schema."""
    try:
        conn.execute(_REGISTRY_DOI_INDEX)
    except sqlite3.OperationalError:
        pass
    _create_partial_index_with_fallback(
        conn,
        unique_sql=_REGISTRY_PMID_INDEX,
        fallback_sql=(
            "CREATE INDEX IF NOT EXISTS idx_registry_pmid_nonunique "
            "ON papers_registry(pmid) WHERE pmid IS NOT NULL AND pmid != ''"
        ),
        label="pmid",
    )
    _create_partial_index_with_fallback(
        conn,
        unique_sql=_REGISTRY_PUBNUM_INDEX,
        fallback_sql=(
            "CREATE INDEX IF NOT EXISTS idx_registry_publication_number "
            "ON papers_registry(publication_number) "
            "WHERE publication_number IS NOT NULL AND publication_number != ''"
        ),
        label="publication_number",
    )
    try:
        conn.execute(_REGISTRY_TITLE_INDEX)
    except sqlite3.OperationalError:
        pass


def _upsert_registry_record(
    conn: sqlite3.Connection,
    *,
    paper_id: str,
    dir_name: str,
    title: str,
    doi: str,
    pmid: str,
    publication_number: str,
    year: int | None,
    first_author: str,
) -> None:
    """Insert or update a registry row while degrading conflicting optional IDs safely."""
    record = {
        "paper_id": paper_id,
        "dir_name": dir_name,
        "title": title,
        "doi": doi,
        "pmid": pmid,
        "publication_number": publication_number,
        "year": year,
        "first_author": first_author,
    }
    sql = """INSERT INTO papers_registry
                (id, dir_name, title, doi, pmid, publication_number, year, first_author)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)
             ON CONFLICT(id) DO UPDATE SET
                dir_name=excluded.dir_name,
                title=excluded.title,
                doi=excluded.doi,
                pmid=excluded.pmid,
                publication_number=excluded.publication_number,
                year=excluded.year,
                first_author=excluded.first_author"""
    while True:
        try:
            conn.execute(
                sql,
                (
                    record["paper_id"],
                    record["dir_name"],
                    record["title"],
                    record["doi"],
                    record["pmid"],
                    record["publication_number"],
                    record["year"],
                    record["first_author"],
                ),
            )
            return
        except sqlite3.IntegrityError as exc:
            err_msg = str(exc).lower()
            if "pmid" in err_msg and record["pmid"]:
                _log.warning(
                    "pmid %r for paper %s conflicts with another paper; storing without pmid",
                    record["pmid"],
                    paper_id,
                )
                record["pmid"] = ""
                continue
            if "publication_number" in err_msg and record["publication_number"]:
                _log.warning(
                    "publication_number %r for paper %s conflicts with another paper; storing without publication_number",
                    record["publication_number"],
                    paper_id,
                )
                record["publication_number"] = ""
                continue
            _log.warning("IntegrityError for paper %s: %s; skipping registry update", paper_id, exc)
            return


def _select_registry_rows(
    conn: sqlite3.Connection,
    clause: str,
    params: tuple[object, ...] = (),
    *,
    paper_ids: set[str] | None = None,
) -> list[dict]:
    """Run a registry query and return rows as dictionaries."""
    if paper_ids is not None and not paper_ids:
        return []
    sql = f"SELECT * FROM papers_registry WHERE {clause}"
    query_params: list[object] = list(params)
    if paper_ids is not None:
        ids_sorted = sorted(paper_ids)
        sql += f" AND id IN ({','.join('?' for _ in ids_sorted)})"
        query_params.extend(ids_sorted)
    sql += " ORDER BY year DESC, dir_name"
    return [dict(row) for row in conn.execute(sql, tuple(query_params)).fetchall()]


def build_index(
    papers_dir: Path,
    db_path: Path,
    rebuild: bool = False,
    *,
    paper_ids: set[str] | None = None,
) -> int:
    """建立或增量更新 SQLite FTS5 全文检索索引。

    索引字段: ``title`` + ``abstract`` + ``conclusion``，
    均参与全文检索。其余字段（``paper_id``, ``authors`` 等）仅存储。

    Args:
        papers_dir: 已入库论文目录，扫描其中的 ``*.json``。
        db_path: SQLite 数据库路径，不存在时自动创建。
        rebuild: 为 ``True`` 时清空旧数据后重建。
        paper_ids: 可选；仅增量更新指定 UUID 的论文。``rebuild=True`` 时忽略。

    Returns:
        本次索引的论文数量。
    """
    from autor.papers import iter_paper_dirs
    from autor.papers import read_meta as _read_meta

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_SCHEMA)
        conn.execute(_HASH_SCHEMA)
        conn.executescript(_NODE_SCHEMA)
        conn.execute(_NODE_FTS_SCHEMA)
        conn.execute(_REGISTRY_SCHEMA)
        _ensure_registry_indexes(conn)
        conn.execute(_CITATIONS_SCHEMA)
        try:
            conn.execute(_CITATIONS_IDX_TARGET_DOI)
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute(_CITATIONS_IDX_TARGET_ID)
        except sqlite3.OperationalError:
            pass

        if rebuild:
            conn.execute("DROP TABLE IF EXISTS papers")
            conn.execute("DROP TABLE IF EXISTS paper_node_fts")
            conn.execute("DROP TABLE IF EXISTS paper_nodes")
            conn.execute(_SCHEMA)
            conn.executescript(_NODE_SCHEMA)
            conn.execute(_NODE_FTS_SCHEMA)
            conn.execute("DELETE FROM papers_hash")
            conn.execute("DELETE FROM papers_registry")
            conn.execute("DELETE FROM citations")

        # Load existing hashes for incremental change detection
        existing_hashes: dict[str, str] = {}
        if not rebuild:
            for row in conn.execute("SELECT paper_id, content_hash FROM papers_hash").fetchall():
                existing_hashes[row[0]] = row[1]

        count = 0
        target_ids = None if rebuild or paper_ids is None else set(paper_ids)
        for pdir in iter_paper_dirs(papers_dir):
            try:
                meta = _read_meta(pdir)
            except (ValueError, FileNotFoundError):
                continue
            paper_id = meta.get("id") or pdir.name
            if target_ids is not None and paper_id not in target_ids:
                continue
            h = _index_hash(meta)
            has_nodes = conn.execute("SELECT 1 FROM paper_nodes WHERE paper_id = ? LIMIT 1", (paper_id,)).fetchone()
            if not rebuild and existing_hashes.get(paper_id) == h and has_nodes:
                continue  # unchanged, skip

            if not rebuild:
                conn.execute("DELETE FROM papers WHERE paper_id = ?", (paper_id,))

            best_cite = best_citation(meta)
            md_file = pdir / "paper.md"
            conn.execute(
                """
                INSERT INTO papers
                    (paper_id, title, authors, year, journal, abstract, conclusion,
                     doi, paper_type, citation_count, md_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    paper_id,
                    meta.get("title") or "",
                    ", ".join(meta.get("authors") or []),
                    str(meta.get("year") or ""),
                    meta.get("journal") or "",
                    meta.get("abstract") or "",
                    _render_l3_index_text(meta),
                    meta.get("doi") or "",
                    meta.get("paper_type") or "",
                    str(best_cite) if best_cite is not None else "",
                    str(md_file) if md_file.exists() else "",
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO papers_hash (paper_id, content_hash) VALUES (?, ?)",
                (paper_id, h),
            )

            # Update papers_registry — use ON CONFLICT(id) DO UPDATE so that
            # a publication_number UNIQUE violation is surfaced rather than
            # silently deleting a different paper's row (which INSERT OR REPLACE
            # would do when the new pub_num collides with another id's row).
            dir_name = pdir.name
            pub_num = ((meta.get("ids") or {}).get("patent_publication_number", "") or "").upper().strip()
            pmid_norm = _normalize_pmid(meta.get("pmid") or ((meta.get("ids") or {}).get("pmid", "") or ""))
            _upsert_registry_record(
                conn,
                paper_id=paper_id,
                dir_name=dir_name,
                title=meta.get("title") or "",
                doi=_normalize_doi(meta.get("doi") or ""),
                pmid=pmid_norm,
                publication_number=pub_num,
                year=meta.get("year"),
                first_author=meta.get("first_author_lastname") or "",
            )

            # Insert references into citations table
            refs = _reference_dois(meta.get("references") or [])
            conn.execute("DELETE FROM citations WHERE source_id = ?", (paper_id,))
            if refs:
                conn.executemany(
                    "INSERT OR IGNORE INTO citations (source_id, target_doi, target_id) VALUES (?, ?, NULL)",
                    [(paper_id, doi) for doi in refs],
                )

            _replace_paper_nodes(conn, paper_id=paper_id, dir_name=dir_name, meta=meta, paper_dir=pdir)

            count += 1

        # Bulk resolve target_id for citations where target paper is in library
        conn.execute("""
            UPDATE citations SET target_id = (
                SELECT pr.id FROM papers_registry pr
                WHERE LOWER(pr.doi) = LOWER(citations.target_doi)
            ) WHERE target_id IS NULL
        """)

        conn.commit()
    finally:
        conn.close()
    return count


def _checkpoint_wal(db_path: Path) -> None:
    """Checkpoint and truncate SQLite WAL files after a build."""
    if not db_path.exists():
        return
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def build_index_atomic(
    papers_dir: Path,
    db_path: Path,
    rebuild: bool = False,
    *,
    paper_ids: set[str] | None = None,
    temp_dir: Path | None = None,
) -> int:
    """Build the index, using a temporary database for full rebuilds.

    Full rebuilds can be very slow on Windows-mounted WSL paths because SQLite
    writes large WAL files. For ``rebuild=True`` this helper builds the database
    in a local temporary directory, checkpoints it, then replaces the target DB.

    Args:
        papers_dir: Papers directory.
        db_path: Final SQLite database path.
        rebuild: Whether to rebuild from scratch.
        paper_ids: Optional UUID scope for incremental updates.
        temp_dir: Optional temporary directory for rebuild output.

    Returns:
        Number of indexed papers.
    """
    if not rebuild:
        return build_index(papers_dir, db_path, rebuild=False, paper_ids=paper_ids)

    tmp_root = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp_db = tmp_root / f"autor-index-{os.getpid()}.db"
    for suffix in ("", "-wal", "-shm"):
        tmp_db.with_name(tmp_db.name + suffix).unlink(missing_ok=True)

    count = build_index(papers_dir, tmp_db, rebuild=True)
    _checkpoint_wal(tmp_db)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("-wal", "-shm"):
        try:
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        except OSError as e:
            _log.debug("failed to remove stale SQLite sidecar %s: %s", db_path.name + suffix, e)
    shutil.copy2(tmp_db, db_path)
    for suffix in ("-wal", "-shm"):
        try:
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        except OSError as e:
            _log.debug("failed to remove SQLite sidecar after atomic copy %s: %s", db_path.name + suffix, e)
    for suffix in ("", "-wal", "-shm"):
        tmp_db.with_name(tmp_db.name + suffix).unlink(missing_ok=True)
    return count


def index_status(db_path: Path) -> dict:
    """Return a compact health summary for the local SQLite index."""
    payload: dict = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "wal_size_bytes": db_path.with_name(db_path.name + "-wal").stat().st_size
        if db_path.with_name(db_path.name + "-wal").exists()
        else 0,
        "shm_size_bytes": db_path.with_name(db_path.name + "-shm").stat().st_size
        if db_path.with_name(db_path.name + "-shm").exists()
        else 0,
        "tables": {},
        "ok": False,
    }
    if not db_path.exists():
        return payload

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1) as conn:
            conn.execute("PRAGMA query_only=ON")
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                ).fetchall()
            }
            for table in ("papers_registry", "papers", "paper_nodes", "paper_node_fts", "citations"):
                if table not in names:
                    payload["tables"][table] = None
                    continue
                if table == "paper_node_fts":
                    payload["tables"][table] = "present"
                    continue
                payload["tables"][table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            payload["ok"] = all(payload["tables"].get(t) is not None for t in ("papers_registry", "paper_nodes", "paper_node_fts"))
    except sqlite3.Error as e:
        payload["error"] = str(e)
    return payload


def _replace_paper_nodes(conn: sqlite3.Connection, *, paper_id: str, dir_name: str, meta: dict, paper_dir: Path) -> None:
    """Replace deterministic evidence nodes for one paper."""
    conn.execute("DELETE FROM paper_node_fts WHERE paper_id = ?", (paper_id,))
    conn.execute("DELETE FROM paper_nodes WHERE paper_id = ?", (paper_id,))

    title = str(meta.get("title") or "").strip()
    abstract = str(meta.get("abstract") or "").strip()
    conclusion = _render_l3_index_text(meta)
    authors = ", ".join(meta.get("authors") or [])
    journal = str(meta.get("journal") or "").strip()
    year = str(meta.get("year") or "").strip()
    doi = str(meta.get("doi") or "").strip()
    paper_type = str(meta.get("paper_type") or "").strip()

    nodes: list[tuple[str, str, str, str]] = []
    metadata_parts = [
        f"Title: {title}" if title else "",
        f"Authors: {authors}" if authors else "",
        f"Year: {year}" if year else "",
        f"Journal: {journal}" if journal else "",
        f"DOI: {doi}" if doi else "",
        f"Type: {paper_type}" if paper_type else "",
        f"Abstract: {abstract}" if abstract else "",
        f"Conclusion: {conclusion}" if conclusion else "",
    ]
    metadata_text = "\n".join(part for part in metadata_parts if part).strip()
    if metadata_text:
        nodes.append(("metadata", "Metadata", metadata_text, str(paper_dir / "meta.json")))

    md_path = paper_dir / "paper.md"
    if md_path.exists():
        try:
            from autor.loader import chunk_markdown_text

            markdown = md_path.read_text(encoding="utf-8", errors="replace")
            chunks = chunk_markdown_text(markdown, title=title, max_chars=1200, overlap_chars=120)
            for chunk in chunks:
                ref = f"{md_path}#{_slugify_section(chunk.section)}" if chunk.section else str(md_path)
                nodes.append(("chunk", chunk.section or "Full text", chunk.content, ref))
        except Exception as exc:
            _log.warning("failed to build evidence chunks for %s: %s", paper_dir.name, exc)

    if not nodes and title:
        nodes.append(("metadata", "Metadata", title, str(paper_dir / "meta.json")))

    node_rows: list[tuple] = []
    fts_rows: list[tuple[str, str, str]] = []
    total = len(nodes)
    for idx, (kind, section, content, ref_path) in enumerate(nodes, start=1):
        node_id = f"{paper_id}:node:{idx:04d}"
        prev_id = f"{paper_id}:node:{idx - 1:04d}" if idx > 1 else None
        next_id = f"{paper_id}:node:{idx + 1:04d}" if idx < total else None
        node_title = title or section or dir_name
        token_text = " ".join(_fts_tokens(f"{node_title}\n{section}\n{content}"))
        if not token_text:
            token_text = node_title.lower() or paper_id.lower()
        node_rows.append(
            (
                node_id,
                paper_id,
                dir_name,
                idx,
                kind,
                section,
                node_title,
                ref_path,
                prev_id,
                next_id,
                content,
                token_text,
                _text_hash(content),
            )
        )
        fts_rows.append((node_id, paper_id, token_text))

    conn.executemany(
        """
        INSERT INTO paper_nodes
            (node_id, paper_id, dir_name, ordinal, kind, section, title, ref_path,
             prev_id, next_id, content, tokens, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        node_rows,
    )
    conn.executemany(
        "INSERT INTO paper_node_fts(node_id, paper_id, tokens) VALUES (?, ?, ?)",
        fts_rows,
    )


def _slugify_section(value: str) -> str:
    slug = re.sub(r"[^\w\u3400-\u9fff]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or "section"


_SEARCH_COLS = "paper_id, title, authors, year, journal, doi, paper_type, citation_count"


def _reference_dois(refs: list) -> list[str]:
    """Extract DOI strings from heterogeneous reference entries.

    Supports both the canonical list[str] shape and dict entries that may
    come from manually curated metadata or external APIs.
    """
    dois: list[str] = []
    for ref in refs:
        doi = ""
        if isinstance(ref, str):
            doi = ref
        elif isinstance(ref, dict):
            external_ids = ref.get("externalIds")
            if not isinstance(external_ids, dict):
                external_ids = {}
            external_ids_alt = ref.get("external_ids")
            if not isinstance(external_ids_alt, dict):
                external_ids_alt = {}
            doi = (
                str(ref.get("doi") or "")
                or str(ref.get("DOI") or "")
                or str(external_ids.get("DOI") or "")
                or str(external_ids_alt.get("DOI") or "")
            )
        doi = (doi or "").strip().lower()
        if doi:
            dois.append(doi)
    return dois


def _ensure_fts_table(conn: sqlite3.Connection) -> None:
    """Raise FileNotFoundError if the FTS5 papers table does not exist."""
    has_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='papers'").fetchone()
    if not has_table:
        raise FileNotFoundError("FTS5 索引表不存在，请先运行 `autor index`")


def _ensure_node_fts_table(conn: sqlite3.Connection) -> None:
    """Raise FileNotFoundError if the node-level evidence index is missing."""
    has_nodes = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_nodes'").fetchone()
    has_fts = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_node_fts'").fetchone()
    if not has_nodes or not has_fts:
        raise FileNotFoundError("节点证据索引不存在，请先运行 `autor index --rebuild`")


def _paper_ids_clause(alias: str, paper_ids: set[str] | None) -> tuple[str, list[str]]:
    if paper_ids is None:
        return "", []
    if not paper_ids:
        return " AND 0", []
    ids = sorted(paper_ids)
    return f" AND {alias}.paper_id IN ({','.join('?' for _ in ids)})", ids


def search_nodes(
    query: str,
    db_path: Path,
    top_k: int | None = None,
    cfg: Config | None = None,
    *,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    paper_ids: set[str] | None = None,
    query_mode: str = "or",
    require_terms: list[str] | None = None,
    exclude_terms: list[str] | None = None,
) -> list[dict]:
    """Search deterministic full-text evidence nodes.

    Args:
        query: Natural-language query or keywords.
        db_path: SQLite index path.
        top_k: Maximum node hits to return.
        cfg: Optional config.
        year: Optional year filter.
        journal: Optional journal filter.
        paper_type: Optional paper type filter.
        paper_ids: Optional UUID whitelist.
        query_mode: ``"or"`` for broad recall or ``"and"`` for stricter matching.
        require_terms: Terms that must also appear in the FTS expression.
        exclude_terms: Terms that must not appear in returned node content.

    Returns:
        Evidence-node dictionaries with paper metadata, section, snippet, and source path.

    Raises:
        FileNotFoundError: Database or node index missing.
    """
    if top_k is None:
        top_k = cfg.search.top_k if cfg is not None else 20
    if top_k <= 0:
        return []
    if paper_ids is not None and not paper_ids:
        return []
    if not db_path.exists():
        raise FileNotFoundError(f"索引文件不存在：{db_path}\n请先运行 `autor index`")

    terms = _fts_tokens(query)
    match_expr = _build_node_match(query, query_mode=query_mode, require_terms=require_terms)
    if not match_expr:
        return []

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        _ensure_node_fts_table(conn)
        filter_sql, filter_params = _build_filter_clause(
            year=year,
            journal=journal,
            paper_type=paper_type,
            table_alias="p",
        )
        ids_sql, ids_params = _paper_ids_clause("n", paper_ids)
        rows = []
        try:
            rows = conn.execute(
                f"""
                SELECT
                    n.node_id, n.paper_id, n.dir_name, n.ordinal, n.kind, n.section,
                    n.title AS node_title, n.ref_path, n.prev_id, n.next_id, n.content,
                    p.title, p.authors, p.year, p.journal, p.doi, p.paper_type, p.citation_count,
                    bm25(paper_node_fts) AS rank
                FROM paper_node_fts
                JOIN paper_nodes n ON n.node_id = paper_node_fts.node_id
                JOIN papers p ON p.paper_id = n.paper_id
                WHERE paper_node_fts MATCH ?{filter_sql}{ids_sql}
                ORDER BY rank, n.paper_id, n.ordinal
                LIMIT ?
                """,
                [match_expr, *filter_params, *ids_params, top_k],
            ).fetchall()
        except sqlite3.OperationalError as exc:
            _log.debug("node FTS query failed, using LIKE fallback: %s", exc)

        if not rows:
            rows = _search_nodes_like_fallback(
                conn,
                terms,
                top_k=top_k,
                year=year,
                journal=journal,
                paper_type=paper_type,
                paper_ids=paper_ids,
            )

        excluded = [str(t).strip().lower() for t in exclude_terms or [] if str(t).strip()]
        results: list[dict] = []
        for row in rows:
            item = dict(row)
            content = str(item.get("content") or "")
            if excluded and any(term in content.lower() for term in excluded):
                continue
            item["snippet"] = _extract_snippet(content, terms)
            item["match"] = "fts"
            rank = item.get("rank")
            item["score"] = float(-rank) if isinstance(rank, (int, float)) else 0.0
            results.append(item)
        return results[:top_k]
    finally:
        conn.close()


def _search_nodes_like_fallback(
    conn: sqlite3.Connection,
    terms: list[str],
    *,
    top_k: int,
    year: str | None,
    journal: str | None,
    paper_type: str | None,
    paper_ids: set[str] | None,
) -> list[sqlite3.Row]:
    """Fallback deterministic LIKE scan used when FTS has no hits."""
    if not terms:
        return []
    conditions: list[str] = []
    params: list[str] = []
    for term in terms[:8]:
        escaped = _escape_like(term)
        conditions.append("LOWER(n.content) LIKE ? ESCAPE '\\'")
        params.append(f"%{escaped.lower()}%")
    filter_sql, filter_params = _build_filter_clause(
        year=year,
        journal=journal,
        paper_type=paper_type,
        table_alias="p",
    )
    ids_sql, ids_params = _paper_ids_clause("n", paper_ids)
    return conn.execute(
        f"""
        SELECT
            n.node_id, n.paper_id, n.dir_name, n.ordinal, n.kind, n.section,
            n.title AS node_title, n.ref_path, n.prev_id, n.next_id, n.content,
            p.title, p.authors, p.year, p.journal, p.doi, p.paper_type, p.citation_count,
            999.0 AS rank
        FROM paper_nodes n
        JOIN papers p ON p.paper_id = n.paper_id
        WHERE ({' OR '.join(conditions)}){filter_sql}{ids_sql}
        ORDER BY n.paper_id, n.ordinal
        LIMIT ?
        """,
        [*params, *filter_params, *ids_params, top_k],
    ).fetchall()


def auditable_search(
    query: str,
    db_path: Path,
    top_k: int | None = None,
    cfg: Config | None = None,
    *,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    paper_ids: set[str] | None = None,
    query_mode: str = "or",
) -> list[dict]:
    """Return paper-level results aggregated from deterministic evidence nodes."""
    if top_k is None:
        top_k = cfg.search.top_k if cfg is not None else 20
    node_hits = search_nodes(
        query,
        db_path,
        top_k=max(top_k * 4, top_k),
        cfg=cfg,
        year=year,
        journal=journal,
        paper_type=paper_type,
        paper_ids=paper_ids,
        query_mode=query_mode,
    )
    return _aggregate_node_hits(node_hits, top_k=top_k)


def _aggregate_node_hits(node_hits: list[dict], *, top_k: int) -> list[dict]:
    merged: dict[str, dict] = {}
    for rank, hit in enumerate(node_hits):
        pid = hit["paper_id"]
        score = 1.0 / (60 + rank + 1)
        evidence = {
            "node_id": hit["node_id"],
            "section": hit["section"],
            "snippet": hit["snippet"],
            "ref_path": hit["ref_path"],
        }
        if pid not in merged:
            merged[pid] = {
                "paper_id": pid,
                "dir_name": hit.get("dir_name", ""),
                "title": hit.get("title", ""),
                "authors": hit.get("authors", ""),
                "year": hit.get("year", ""),
                "journal": hit.get("journal", ""),
                "doi": hit.get("doi", ""),
                "paper_type": hit.get("paper_type", ""),
                "citation_count": hit.get("citation_count", ""),
                "score": score,
                "match": "fts",
                "evidence_count": 1,
                "evidence": [evidence],
            }
        else:
            merged[pid]["score"] += score
            merged[pid]["evidence_count"] += 1
            if len(merged[pid]["evidence"]) < 3:
                merged[pid]["evidence"].append(evidence)

    results = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
    return results[:top_k]


def search(
    query: str,
    db_path: Path,
    top_k: int | None = None,
    cfg: Config | None = None,
    *,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    paper_ids: set[str] | None = None,
) -> list[dict]:
    """可审计关键词检索。

    在 ``paper_nodes`` / ``paper_node_fts`` 节点级证据索引上执行确定性
    FTS5 检索，再按论文聚合返回结果。结果中的 ``evidence`` 字段保留
    命中节点、片段和 ``paper.md`` 路径，供模型回答时追溯来源。

    Args:
        query: 检索词（多词用空格分隔，FTS5 语法）。
        db_path: SQLite 索引数据库路径。
        top_k: 最多返回条数，为 ``None`` 时从 ``cfg.search.top_k`` 读取。
        cfg: 可选的 :class:`~autor.config.Config` 实例。
        year: 年份过滤（``"2023"`` / ``"2020-2024"`` / ``"2020-"``）。
        journal: 期刊名过滤（LIKE 模糊匹配）。
        paper_type: 论文类型过滤（如 ``"review"``、``"journal-article"``）。
        paper_ids: 论文 UUID 白名单，仅返回集合内的结果。

    Returns:
        匹配的论文字典列表，每项包含 ``paper_id``, ``title``,
        ``authors``, ``year``, ``journal``, ``doi``, ``paper_type``,
        ``citation_count``。

    Raises:
        FileNotFoundError: 索引文件或 FTS5 表不存在。
    """
    return auditable_search(
        query,
        db_path,
        top_k=top_k,
        cfg=cfg,
        year=year,
        journal=journal,
        paper_type=paper_type,
        paper_ids=paper_ids,
    )


def search_author(
    query: str,
    db_path: Path,
    top_k: int | None = None,
    cfg: Config | None = None,
    *,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    paper_ids: set[str] | None = None,
) -> list[dict]:
    """按作者名搜索论文（LIKE 模糊匹配）。

    Args:
        query: 作者名（或部分名字），不区分大小写。
        db_path: SQLite 索引数据库路径。
        top_k: 最多返回条数，为 ``None`` 时从 ``cfg.search.top_k`` 读取。
        cfg: 可选的 :class:`~autor.config.Config` 实例。
        year: 年份过滤（``"2023"`` / ``"2020-2024"`` / ``"2020-"``）。
        journal: 期刊名过滤（LIKE 模糊匹配）。
        paper_type: 论文类型过滤（如 ``"review"``、``"journal-article"``）。
        paper_ids: 论文 UUID 白名单，仅返回集合内的结果。

    Returns:
        匹配的论文字典列表。
    """
    if top_k is None:
        top_k = cfg.search.top_k if cfg is not None else 20

    if not db_path.exists():
        raise FileNotFoundError(f"索引文件不存在：{db_path}\n请先运行 `autor index`")

    conn = sqlite3.connect(db_path)
    try:
        _ensure_fts_table(conn)

        conn.row_factory = sqlite3.Row
        filter_sql, filter_params = _build_filter_clause(year=year, journal=journal, paper_type=paper_type)

        # Over-fetch when post-filtering by paper_ids to avoid empty results
        fetch_k = top_k * 5 if paper_ids else top_k

        rows = conn.execute(
            f"""
            SELECT {_SEARCH_COLS}
            FROM papers
            WHERE authors LIKE ?{filter_sql}
            ORDER BY year DESC
            LIMIT ?
            """,
            [f"%{query}%", *filter_params, fetch_k],
        ).fetchall()
        results = [dict(r) for r in rows]
        _enrich_dir_names(results, conn)
    finally:
        conn.close()
    if paper_ids is not None:
        results = [r for r in results if r["paper_id"] in paper_ids]
    return results[:top_k]


def top_cited(
    db_path: Path,
    top_k: int = 10,
    *,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    paper_ids: set[str] | None = None,
) -> list[dict]:
    """按引用量降序返回论文。

    Args:
        db_path: SQLite 索引数据库路径。
        top_k: 最多返回条数。
        year: 年份过滤（``"2023"`` / ``"2020-2024"`` / ``"2020-"``）。
        journal: 期刊名过滤（LIKE 模糊匹配）。
        paper_type: 论文类型过滤（如 ``"review"``、``"journal-article"``）。
        paper_ids: 论文 UUID 白名单，仅返回集合内的结果。

    Returns:
        论文字典列表，按 ``citation_count`` 降序排列。

    Raises:
        FileNotFoundError: 索引文件或 FTS5 表不存在。
    """
    if not db_path.exists():
        raise FileNotFoundError(f"索引文件不存在：{db_path}\n请先运行 `autor index`")

    conn = sqlite3.connect(db_path)
    try:
        _ensure_fts_table(conn)

        conn.row_factory = sqlite3.Row
        filter_sql, filter_params = _build_filter_clause(year=year, journal=journal, paper_type=paper_type)

        # Skip SQL LIMIT when post-filtering by paper_ids (workspace scope)
        limit_clause = "" if paper_ids else "LIMIT ?"
        limit_params = [] if paper_ids else [top_k]

        rows = conn.execute(
            f"""
            SELECT {_SEARCH_COLS}
            FROM papers
            WHERE citation_count != ''{filter_sql}
            ORDER BY CAST(citation_count AS INTEGER) DESC
            {limit_clause}
            """,
            [*filter_params, *limit_params],
        ).fetchall()
        results = [dict(r) for r in rows]
        _enrich_dir_names(results, conn)
    finally:
        conn.close()
    if paper_ids is not None:
        results = [r for r in results if r["paper_id"] in paper_ids]
    return results[:top_k]


def _parse_year_filter(year: str) -> tuple[str, list[str]]:
    """解析年份过滤表达式，返回 SQL WHERE 片段和参数。

    支持格式: ``"2023"`` (单年), ``"2020-2024"`` (范围), ``"2020-"`` (起始年至今)。

    Args:
        year: 年份过滤表达式。

    Returns:
        ``(where_clause, params)`` 二元组。
    """
    start, end = parse_year_range(year)
    if start is not None and end is not None:
        if start == end:
            return "year = ?", [str(start)]
        return "year >= ? AND year <= ?", [str(start), str(end)]
    elif start is not None:
        return "year >= ?", [str(start)]
    elif end is not None:
        return "year <= ?", [str(end)]
    return "1=1", []


def _build_filter_clause(
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    *,
    table_alias: str = "",
) -> tuple[str, list[str]]:
    """构建过滤 WHERE 子句（不含前导 AND/WHERE）。

    Args:
        year: 年份过滤表达式，为 ``None`` 时不过滤。
        journal: 期刊名（LIKE 模糊匹配），为 ``None`` 时不过滤。
        paper_type: 论文类型（LIKE 模糊匹配，如 ``review``、``journal-article``），
            为 ``None`` 时不过滤。

    Returns:
        ``(clauses_str, params)``，clauses_str 每个条件前带 ``AND``。
    """
    prefix = f"{table_alias}." if table_alias else ""
    clauses: list[str] = []
    params: list[str] = []
    if year:
        yc, yp = _parse_year_filter(year)
        yc = yc.replace("year", f"{prefix}year")
        clauses.append(yc)
        params.extend(yp)
    if journal:
        clauses.append(f"{prefix}journal LIKE ?")
        params.append(f"%{journal}%")
    if paper_type:
        clauses.append(f"{prefix}paper_type LIKE ?")
        params.append(f"%{paper_type}%")
    sql = "".join(f" AND {c}" for c in clauses)
    return sql, params


def _safe_query(query: str) -> str:
    """去除 FTS5 特殊字符，避免语法错误。"""
    return re.sub(r"[^\w\s]", " ", query).strip()


def _enrich_dir_names(results: list[dict], conn: sqlite3.Connection) -> list[dict]:
    """Enrich search results with dir_name from papers_registry."""
    has_reg = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='papers_registry'").fetchone()
    if not has_reg:
        return results
    id_to_dir: dict[str, str] = {}
    for row in conn.execute("SELECT id, dir_name FROM papers_registry").fetchall():
        id_to_dir[row[0]] = row[1]
    for r in results:
        r["dir_name"] = id_to_dir.get(r["paper_id"], "")
    return results


def lookup_paper(db_path: Path, user_input: str) -> dict | None:
    """查找论文：支持 UUID、dir_name、DOI、PMID、专利公开号。

    按以下顺序尝试匹配: UUID → dir_name → DOI → PMID → publication_number。
    PMID 查询会自动归一化数字形式；公开号查询会自动归一化为大写。

    Args:
        db_path: SQLite 数据库路径。
        user_input: UUID、目录名、DOI、PMID 或专利公开号。

    Returns:
        ``papers_registry`` 行字典，找不到时返回 ``None``。
    """
    if not db_path.exists():
        return None
    raw_input = str(user_input or "").strip()
    if not raw_input:
        return None
    conn = sqlite3.connect(db_path)
    try:
        has_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='papers_registry'"
        ).fetchone()
        if not has_table:
            return None
        conn.row_factory = sqlite3.Row
        _ensure_registry_indexes(conn)
        # Try UUID
        row = conn.execute("SELECT * FROM papers_registry WHERE id = ?", (raw_input,)).fetchone()
        if row:
            return dict(row)
        # Try dir_name
        row = conn.execute("SELECT * FROM papers_registry WHERE dir_name = ?", (raw_input,)).fetchone()
        if row:
            return dict(row)
        # Try DOI
        normalized_doi = _normalize_doi(raw_input)
        row = conn.execute(
            "SELECT * FROM papers_registry WHERE doi = ?",
            (normalized_doi,),
        ).fetchone()
        if row:
            return dict(row)
        normalized_pmid = _normalize_pmid(raw_input)
        if normalized_pmid:
            row = conn.execute(
                "SELECT * FROM papers_registry WHERE pmid = ?",
                (normalized_pmid,),
            ).fetchone()
            if row:
                return dict(row)
            row = _lookup_registry_dir_prefix(
                conn,
                [f"PMID-{normalized_pmid}-", f"PMID:{normalized_pmid}-", f"PMID_{normalized_pmid}_"],
            )
            if row:
                return dict(row)
        # Try patent publication number (normalize to uppercase)
        row = conn.execute(
            "SELECT * FROM papers_registry WHERE publication_number = ?",
            (raw_input.upper().strip(),),
        ).fetchone()
        if row:
            return dict(row)
        # Last-chance prefix matching for callers that pass a dir_name stem.
        prefix_candidates = [raw_input]
        if normalized_doi:
            safe_doi = re.sub(r"[^A-Za-z0-9]+", "-", normalized_doi).strip("-")
            prefix_candidates.extend([f"DOI-{safe_doi}-", f"DOI-{safe_doi}"])
        row = _lookup_registry_dir_prefix(conn, prefix_candidates)
        if row:
            return dict(row)
    finally:
        conn.close()
    return None


def find_exact_matches(
    db_path: Path,
    *,
    doi: str | None = None,
    pmid: str | None = None,
    title: str | None = None,
    paper_ids: set[str] | None = None,
) -> dict[str, list[dict]]:
    """Find exact registry matches by DOI, PMID, and/or exact title.

    Args:
        db_path: SQLite 数据库路径。
        doi: 精确 DOI（大小写不敏感）。
        pmid: 精确 PubMed ID。
        title: 精确标题（大小写不敏感）。
        paper_ids: 可选 paper_id 子集，用于工作区过滤。

    Returns:
        结果字典，包含 ``doi``、``pmid``、``title`` 三个字段匹配列表，
        以及去重后的 ``records`` 总表。
    """
    empty: dict[str, list[dict]] = {"doi": [], "pmid": [], "title": [], "records": []}
    if not db_path.exists():
        raise FileNotFoundError(f"Index not built: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        has_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='papers_registry'"
        ).fetchone()
        if not has_table:
            raise FileNotFoundError(f"papers_registry missing in index: {db_path}")
        _ensure_registry_indexes(conn)

        results: dict[str, list[dict]] = {"doi": [], "pmid": [], "title": []}
        normalized_doi = _normalize_doi(doi)
        if normalized_doi:
            results["doi"] = _select_registry_rows(conn, "doi = ?", (normalized_doi,), paper_ids=paper_ids)
        normalized_pmid = _normalize_pmid(pmid)
        if normalized_pmid:
            results["pmid"] = _select_registry_rows(conn, "pmid = ?", (normalized_pmid,), paper_ids=paper_ids)
        normalized_title = _normalize_exact_title(title)
        if normalized_title:
            results["title"] = _select_registry_rows(
                conn,
                "LOWER(TRIM(title)) = ?",
                (normalized_title,),
                paper_ids=paper_ids,
            )

        merged: dict[str, dict] = {}
        for field in ("doi", "pmid", "title"):
            for row in results[field]:
                merged.setdefault(row["id"], row)
        results["records"] = list(merged.values())
        return results
    finally:
        conn.close()


def research_bundle(
    query: str,
    db_path: Path,
    *,
    run_dir: Path | None = None,
    top_k: int = 10,
    cfg: Config | None = None,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    paper_ids: set[str] | None = None,
    neighbors: int = 1,
    max_chars: int = 40000,
    per_node_max_chars: int = 6000,
) -> dict:
    """Run one deterministic evidence-bundling round.

    Args:
        query: Research question or search goal.
        db_path: SQLite index path.
        run_dir: Optional directory where bundle/trace/verify artifacts are written.
        top_k: Seed node count.
        cfg: Optional config.
        year: Optional year filter.
        journal: Optional journal filter.
        paper_type: Optional type filter.
        paper_ids: Optional UUID whitelist.
        neighbors: Previous/next node expansion count within each paper.
        max_chars: Total Markdown bundle budget.
        per_node_max_chars: Per evidence node body budget.

    Returns:
        Dict containing ``bundle_json``, ``bundle_md``, ``trace``, ``verify`` and
        optionally artifact ``paths``.
    """
    seed_nodes = search_nodes(
        query,
        db_path,
        top_k=top_k,
        cfg=cfg,
        year=year,
        journal=journal,
        paper_type=paper_type,
        paper_ids=paper_ids,
    )
    evidence_nodes = _expand_research_nodes(db_path, seed_nodes, neighbors=max(0, int(neighbors)))
    bundle_md, rendered_nodes, budget_exhausted = _render_research_bundle_md(
        query,
        evidence_nodes,
        max_chars=max_chars,
        per_node_max_chars=per_node_max_chars,
    )
    now = datetime.now(timezone.utc).isoformat()
    trace = {
        "query": query,
        "created_at": now,
        "seed_node_ids": [n["node_id"] for n in seed_nodes],
        "rendered_node_ids": [n["node_id"] for n in rendered_nodes],
        "filters": {"year": year, "journal": journal, "paper_type": paper_type, "paper_ids": sorted(paper_ids or [])},
        "neighbors": neighbors,
        "top_k": top_k,
        "budget": {"max_chars": max_chars, "per_node_max_chars": per_node_max_chars},
    }
    verify = {
        "ok": bool(rendered_nodes) and not budget_exhausted,
        "has_evidence": bool(rendered_nodes),
        "evidence_count": len(rendered_nodes),
        "references_count": len({n.get("ref_path", "") for n in rendered_nodes if n.get("ref_path")}),
        "budget_exhausted": budget_exhausted,
    }
    bundle_json = {
        "search_goal": {"query": query, "filters": trace["filters"]},
        "coverage_assessment": {
            "status": "covered" if rendered_nodes else "no_hits",
            "seed_hits": len(seed_nodes),
            "evidence_items": len(rendered_nodes),
        },
        "answerability_assessment": {
            "status": "answer_from_bundle" if rendered_nodes else "insufficient_evidence",
            "constraint": "Answer only from evidence_items and preserve references.",
        },
        "probe_trace": trace,
        "evidence_items": [
            {
                "node_id": n["node_id"],
                "paper_id": n["paper_id"],
                "dir_name": n.get("dir_name", ""),
                "title": n.get("title", ""),
                "section": n.get("section", ""),
                "ref_path": n.get("ref_path", ""),
                "snippet": n.get("snippet", ""),
            }
            for n in rendered_nodes
        ],
        "round_decision": {
            "stop": bool(rendered_nodes) and not budget_exhausted,
            "reason": "sufficient_bundle" if rendered_nodes and not budget_exhausted else "revise_query_or_budget",
        },
    }
    paths: dict[str, str] = {}
    if run_dir is not None:
        paths = _write_research_artifacts(run_dir, bundle_json, bundle_md, trace, verify)
    return {
        "bundle_json": bundle_json,
        "bundle_md": bundle_md,
        "trace": trace,
        "verify": verify,
        "paths": paths,
    }


def _expand_research_nodes(db_path: Path, seed_nodes: list[dict], *, neighbors: int) -> list[dict]:
    if not seed_nodes or neighbors <= 0:
        return seed_nodes
    ordered_ids: list[str] = []
    seen: set[str] = set()

    def add(node_id: str | None) -> None:
        if node_id and node_id not in seen:
            seen.add(node_id)
            ordered_ids.append(node_id)

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        for node in seed_nodes:
            prev_id = node.get("prev_id")
            prev_chain: list[str] = []
            for _ in range(neighbors):
                if not prev_id:
                    break
                prev_chain.append(prev_id)
                row = conn.execute("SELECT prev_id FROM paper_nodes WHERE node_id = ?", (prev_id,)).fetchone()
                prev_id = row["prev_id"] if row else None
            for prev in reversed(prev_chain):
                add(prev)
            add(node.get("node_id"))
            next_id = node.get("next_id")
            for _ in range(neighbors):
                if not next_id:
                    break
                add(next_id)
                row = conn.execute("SELECT next_id FROM paper_nodes WHERE node_id = ?", (next_id,)).fetchone()
                next_id = row["next_id"] if row else None
        return _fetch_nodes_by_ids(conn, ordered_ids, _fts_tokens(" ".join(n.get("snippet", "") for n in seed_nodes)))
    finally:
        conn.close()


def _fetch_nodes_by_ids(conn: sqlite3.Connection, node_ids: list[str], terms: list[str]) -> list[dict]:
    if not node_ids:
        return []
    placeholders = ",".join("?" for _ in node_ids)
    rows = conn.execute(
        f"""
        SELECT
            n.node_id, n.paper_id, n.dir_name, n.ordinal, n.kind, n.section,
            n.title AS node_title, n.ref_path, n.prev_id, n.next_id, n.content,
            p.title, p.authors, p.year, p.journal, p.doi, p.paper_type, p.citation_count,
            0.0 AS rank
        FROM paper_nodes n
        JOIN papers p ON p.paper_id = n.paper_id
        WHERE n.node_id IN ({placeholders})
        """,
        node_ids,
    ).fetchall()
    by_id = {row["node_id"]: dict(row) for row in rows}
    out: list[dict] = []
    for node_id in node_ids:
        item = by_id.get(node_id)
        if not item:
            continue
        item["snippet"] = _extract_snippet(str(item.get("content") or ""), terms)
        item["match"] = "fts"
        item["score"] = 0.0
        out.append(item)
    return out


def _render_research_bundle_md(
    query: str,
    nodes: list[dict],
    *,
    max_chars: int,
    per_node_max_chars: int,
) -> tuple[str, list[dict], bool]:
    parts = [
        "# AutoR Evidence Bundle\n\n",
        "## Search Goal\n\n",
        f"{query}\n\n",
        "## Coverage Assessment\n\n",
        f"- seed coverage: {'covered' if nodes else 'no_hits'}\n",
        f"- evidence items: {len(nodes)}\n\n",
        "## Answerability Assessment\n\n",
        "- Answer only from the evidence below; do not invent citations or claims outside this bundle.\n\n",
        "## Probe Trace\n\n",
        "- retrieval: deterministic node-level SQLite FTS5 with CJK 2-gram and ASCII-word tokens\n\n",
        "## Evidence\n\n",
    ]
    rendered: list[dict] = []
    used = sum(len(part) for part in parts)
    budget_exhausted = False
    for node in nodes:
        content = str(node.get("content") or "")
        marker = ""
        if per_node_max_chars > 0 and len(content) > per_node_max_chars:
            content = content[:per_node_max_chars].rstrip() + "\n"
            marker = "*(TRUNCATED)*\n\n"
        block = (
            f"### `{node.get('node_id')}` {node.get('title') or node.get('node_title') or ''}\n\n"
            f"- paper_id: `{node.get('paper_id')}`\n"
            f"- dir_name: `{node.get('dir_name', '')}`\n"
            f"- section: {node.get('section', '')}\n"
            f"- ref: `{node.get('ref_path', '')}`\n\n"
            f"{marker}{content.strip()}\n\n"
        )
        if max_chars > 0 and used + len(block) > max_chars:
            budget_exhausted = True
            break
        parts.append(block)
        used += len(block)
        rendered.append(node)

    parts.append("## References\n\n")
    for ref in sorted({str(node.get("ref_path") or "") for node in rendered if node.get("ref_path")}):
        parts.append(f"- `{ref}`\n")
    if budget_exhausted:
        parts.append("\n> BUDGET EXHAUSTED. Increase `--max-chars` or lower `--top/--neighbors`.\n")
    return "".join(parts), rendered, budget_exhausted


def _write_research_artifacts(
    run_dir: Path,
    bundle_json: dict,
    bundle_md: str,
    trace: dict,
    verify: dict,
) -> dict[str, str]:
    run_dir.mkdir(parents=True, exist_ok=True)
    round_no = _next_round_no(run_dir)
    suffix = f"round{round_no:02d}"
    bundle_json_path = run_dir / "bundle.json"
    bundle_md_path = run_dir / "bundle.md"
    round_bundle_path = run_dir / f"bundle.{suffix}.md"
    trace_path = run_dir / f"trace.{suffix}.json"
    verify_path = run_dir / f"verify.{suffix}.json"
    trace_jsonl = run_dir / "trace.jsonl"

    bundle_json_path.write_text(json.dumps(bundle_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    bundle_md_path.write_text(bundle_md, encoding="utf-8")
    round_bundle_path.write_text(bundle_md, encoding="utf-8")
    trace_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    verify_path.write_text(json.dumps(verify, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with trace_jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(trace, ensure_ascii=False) + "\n")
    return {
        "bundle_json": str(bundle_json_path),
        "bundle_md": str(bundle_md_path),
        "round_bundle_md": str(round_bundle_path),
        "trace": str(trace_path),
        "verify": str(verify_path),
        "trace_jsonl": str(trace_jsonl),
    }


def _next_round_no(run_dir: Path) -> int:
    existing = []
    for path in run_dir.glob("trace.round*.json"):
        match = re.search(r"round(\d+)", path.name)
        if match:
            existing.append(int(match.group(1)))
    return (max(existing) + 1) if existing else 1


# ============================================================================
#  Citation graph queries
# ============================================================================


def get_references(
    paper_id: str,
    db_path: Path,
    *,
    paper_ids: set[str] | None = None,
) -> list[dict]:
    """查询论文的参考文献列表。

    Args:
        paper_id: 论文 UUID。
        db_path: SQLite 数据库路径。
        paper_ids: 论文 UUID 白名单（仅过滤库内结果）。

    Returns:
        参考文献列表，每项含 ``target_doi``、``target_id``，
        库内论文另含 ``title``、``dir_name``、``year``、``first_author``。
    """
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT c.target_doi, c.target_id,
                      pr.title, pr.dir_name, pr.year, pr.first_author
               FROM citations c
               LEFT JOIN papers_registry pr ON c.target_id = pr.id
               WHERE c.source_id = ?
               ORDER BY pr.year DESC NULLS LAST, c.target_doi""",
            (paper_id,),
        ).fetchall()
    finally:
        conn.close()
    results = [dict(r) for r in rows]
    if paper_ids is not None:
        results = [r for r in results if r.get("target_id") is None or r["target_id"] in paper_ids]
    return results


def get_citing_papers(
    paper_id: str,
    db_path: Path,
    *,
    paper_ids: set[str] | None = None,
) -> list[dict]:
    """查询哪些本地论文引用了指定论文（库内反向查找）。

    Args:
        paper_id: 被引论文的 UUID。
        db_path: SQLite 数据库路径。
        paper_ids: 论文 UUID 白名单。

    Returns:
        引用方论文列表，每项含 ``source_id``、``dir_name``、``title``、``year``。
    """
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        # Get DOI of target paper
        row = conn.execute("SELECT doi FROM papers_registry WHERE id = ?", (paper_id,)).fetchone()
        target_doi = row["doi"] if row else ""

        # Find papers that cite this paper (by target_id or target_doi)
        params: list = [paper_id]
        doi_clause = ""
        if target_doi:
            doi_clause = " OR LOWER(c.target_doi) = LOWER(?)"
            params.append(target_doi)

        rows = conn.execute(
            f"""SELECT DISTINCT c.source_id,
                       pr.dir_name, pr.title, pr.year, pr.first_author
                FROM citations c
                JOIN papers_registry pr ON c.source_id = pr.id
                WHERE (c.target_id = ?{doi_clause})
                ORDER BY pr.year DESC""",
            params,
        ).fetchall()
    finally:
        conn.close()
    results = [dict(r) for r in rows]
    if paper_ids is not None:
        results = [r for r in results if r["source_id"] in paper_ids]
    return results


def get_shared_references(
    paper_id_list: list[str],
    db_path: Path,
    min_shared: int = 2,
    *,
    paper_ids: set[str] | None = None,
) -> list[dict]:
    """查询多篇论文的共同参考文献。

    Args:
        paper_id_list: 论文 UUID 列表。
        db_path: SQLite 数据库路径。
        min_shared: 最少被几篇论文共同引用才纳入结果。
        paper_ids: 论文 UUID 白名单（仅过滤库内结果）。

    Returns:
        共同引用列表，每项含 ``target_doi``、``shared_count``、``target_id``，
        库内论文另含 ``title``、``dir_name``。
    """
    if not db_path.exists() or not paper_id_list:
        return []
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in paper_id_list)
        rows = conn.execute(
            f"""SELECT c.target_doi,
                       COUNT(DISTINCT c.source_id) AS shared_count,
                       c.target_id,
                       pr.title, pr.dir_name, pr.year
                FROM citations c
                LEFT JOIN papers_registry pr ON c.target_id = pr.id
                WHERE c.source_id IN ({placeholders})
                GROUP BY LOWER(c.target_doi)
                HAVING shared_count >= ?
                ORDER BY shared_count DESC, c.target_doi""",
            [*paper_id_list, min_shared],
        ).fetchall()
    finally:
        conn.close()
    results = [dict(r) for r in rows]
    if paper_ids is not None:
        results = [r for r in results if r.get("target_id") is None or r["target_id"] in paper_ids]
    return results
