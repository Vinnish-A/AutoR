"""
vectors.py — 向量嵌入与语义检索
==================================

使用 Qwen3-Embedding-0.6B（本地 ModelScope 缓存）生成论文向量。
嵌入文本 = title + abstract，存入 index.db 的 paper_vectors 表。

用法：
    from autor.vectors import build_vectors, vsearch
    build_vectors(papers_dir, db_path)
    results = vsearch("turbulent drag reduction", db_path, top_k=5)
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sqlite3
import struct
from pathlib import Path
import logging
from typing import TYPE_CHECKING

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    import faiss

    from autor.config import Config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_vectors (
    paper_id     TEXT PRIMARY KEY,
    embedding    BLOB NOT NULL,
    content_hash TEXT NOT NULL DEFAULT ''
);
"""

_MIGRATE_HASH = (
    "ALTER TABLE paper_vectors ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''"
)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create paper_vectors table and migrate schema if needed."""
    conn.execute(_SCHEMA)
    # Migrate: add content_hash column if missing
    cols = {row[1] for row in conn.execute("PRAGMA table_info(paper_vectors)")}
    if "content_hash" not in cols:
        conn.execute(_MIGRATE_HASH)


def _content_hash(title: str, abstract: str) -> str:
    """Compute a short hash of the embedding source text."""
    text = f"{title}\n\n{abstract}"
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


# ============================================================================
#  Embedding
# ============================================================================

_model_cache: dict = {}  # key: (model_path, device) → SentenceTransformer


def _load_model(cfg: Config | None = None):
    """Load SentenceTransformer, using module-level cache to avoid reloading."""
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    SentenceTransformer = importlib.import_module("sentence_transformers").SentenceTransformer

    # Resolve config
    if cfg is not None:
        model_name = cfg.embed.model
        cache_dir = os.path.expanduser(cfg.embed.cache_dir)
        device_cfg = cfg.embed.device
        source = cfg.embed.source
    else:
        model_name = "Qwen/Qwen3-Embedding-0.6B"
        cache_dir = os.path.expanduser("~/.cache/modelscope/hub/models")
        device_cfg = "auto"
        source = "modelscope"

    # Resolve device
    if device_cfg == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    else:
        device = device_cfg

    cache_key = (model_name, cache_dir, device)
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    # Try to find or download the model
    local_path = _resolve_model_path(model_name, cache_dir, source)
    if local_path:
        model = SentenceTransformer(local_path, device=device)
    else:
        # HuggingFace fallback: SentenceTransformer handles download internally
        _log.info("[embed] downloading model %s from HuggingFace", model_name)
        model = SentenceTransformer(model_name, device=device)

    _model_cache[cache_key] = model
    return model


def _resolve_model_path(model_name: str, cache_dir: str, source: str) -> str | None:
    """Find local model path or download via ModelScope.

    Args:
        model_name: Model ID (e.g. ``"Qwen/Qwen3-Embedding-0.6B"``).
        cache_dir: Local cache directory.
        source: ``"modelscope"`` or ``"huggingface"``.

    Returns:
        Local folder path if found or downloaded, ``None`` to fall back
        to HuggingFace (SentenceTransformer handles download internally).
    """
    if source != "modelscope":
        return None

    try:
        from modelscope import snapshot_download
    except ImportError:
        return None

    # Check if already cached locally
    try:
        local_path = snapshot_download(model_name, cache_dir=cache_dir, local_files_only=True)
        return local_path
    except Exception as e:
        _log.debug("model not cached locally: %s", e)

    # Download
    try:
        _log.info("[embed] downloading model %s from ModelScope", model_name)
        return snapshot_download(model_name, cache_dir=cache_dir)
    except Exception as e:
        _log.warning("[embed] ModelScope download failed: %s, falling back to HuggingFace", e)
    return None


def _embed_text(text: str, cfg: Config | None = None) -> list[float]:
    model = _load_model(cfg)
    vec = model.encode([text], prompt_name="query", normalize_embeddings=True)
    return vec[0].tolist()


def _embed_batch(texts: list[str], cfg: Config | None = None) -> list[list[float]]:
    model = _load_model(cfg)
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=16)
    return vecs.tolist()


class QwenEmbedder:
    """BERTopic-compatible embedder wrapping Qwen3 via ``_embed_batch``.

    BERTopic's KeyBERTInspired representation model requires an embedding
    backend that exposes ``embed_documents`` and ``embed_words`` methods.
    This class provides that interface.

    Args:
        cfg: Optional Config (or None) forwarded to ``_embed_batch``.
    """

    def __init__(self, cfg: Config | None = None):
        self._cfg = cfg

    def embed_documents(self, documents, verbose=False):
        import numpy as np
        return np.array(_embed_batch(documents, self._cfg), dtype="float32")

    def embed_words(self, words, verbose=False):
        return self.embed_documents(words, verbose)


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _faiss_paths(db_path: Path) -> tuple[Path, Path]:
    """Return (faiss_index_path, faiss_ids_path) next to the db file."""
    parent = db_path.parent
    return parent / "faiss.index", parent / "faiss_ids.json"


def _invalidate_faiss(db_path: Path) -> None:
    """Delete cached FAISS index files so next search rebuilds them."""
    for p in _faiss_paths(db_path):
        p.unlink(missing_ok=True)


def _append_faiss_files(
    index_path: Path,
    ids_path: Path,
    new_ids: list[str],
    new_vecs: list[list[float]],
) -> None:
    """Append new vectors to a FAISS index at explicit file paths.

    If the cached index does not exist yet, does nothing (it will be built on
    next search).  If any new IDs overlap with existing ones, the cached index
    is deleted so it gets rebuilt.

    Args:
        index_path: Path to ``faiss.index`` file.
        ids_path: Path to ``faiss_ids.json`` file.
        new_ids: New paper IDs.
        new_vecs: Corresponding embedding vectors (already normalised).
    """
    import faiss
    import numpy as np

    if not index_path.exists() or not ids_path.exists():
        return

    try:
        index = faiss.read_index(str(index_path))
        paper_ids = json.loads(ids_path.read_text("utf-8"))
    except Exception as e:
        _log.debug("failed to load FAISS cache, rebuilding: %s", e)
        index_path.unlink(missing_ok=True)
        ids_path.unlink(missing_ok=True)
        return

    if set(new_ids) & set(paper_ids):
        index_path.unlink(missing_ok=True)
        ids_path.unlink(missing_ok=True)
        return

    arr = np.array(new_vecs, dtype="float32")
    faiss.normalize_L2(arr)
    index.add(arr)
    paper_ids.extend(new_ids)

    faiss.write_index(index, str(index_path))
    ids_path.write_text(
        json.dumps(paper_ids, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _append_faiss(db_path: Path, new_ids: list[str], new_vecs: list[list[float]]) -> None:
    """Append new vectors to existing FAISS index, or invalidate if not possible.

    Args:
        db_path: SQLite 数据库路径。
        new_ids: 新增论文 ID 列表。
        new_vecs: 对应的向量列表（已归一化）。
    """
    idx_p, ids_p = _faiss_paths(db_path)
    _append_faiss_files(idx_p, ids_p, new_ids, new_vecs)


# ============================================================================
#  Build
# ============================================================================


def build_vectors(papers_dir: Path, db_path: Path, rebuild: bool = False, cfg: Config | None = None) -> int:
    """为论文生成语义嵌入向量并写入 ``paper_vectors`` 表。

    嵌入文本 = ``title`` + ``abstract`` 拼接。
    使用 Sentence Transformer 模型（默认 Qwen3-Embedding-0.6B）。

    Args:
        papers_dir: 已入库论文目录，扫描其中的 ``*.json``。
        db_path: SQLite 数据库路径，不存在时自动创建。
        rebuild: 为 ``True`` 时清空旧向量后重建。
        cfg: 可选的 :class:`~autor.config.Config`，用于读取模型/设备配置。

    Returns:
        本次新写入的向量数量。
    """
    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)

        if rebuild:
            conn.execute("DELETE FROM paper_vectors")

        # Build lookup of existing hashes for incremental check
        existing_hashes: dict[str, str] = {}
        if not rebuild:
            for row in conn.execute(
                "SELECT paper_id, content_hash FROM paper_vectors"
            ).fetchall():
                existing_hashes[row[0]] = row[1]

        # Collect papers to embed
        from autor.papers import iter_paper_dirs, read_meta

        to_embed: list[tuple[str, str, str]] = []  # (paper_id, text, hash)
        for pdir in iter_paper_dirs(papers_dir):
            try:
                meta = read_meta(pdir)
            except (ValueError, FileNotFoundError) as e:
                _log.debug("failed to read meta.json in %s: %s", pdir.name, e)
                continue
            paper_id = meta.get("id") or pdir.name

            title = (meta.get("title") or "").strip()
            abstract = (meta.get("abstract") or "").strip()
            if not title and not abstract:
                continue

            h = _content_hash(title, abstract)
            if not rebuild and existing_hashes.get(paper_id) == h:
                continue  # content unchanged, skip

            if not abstract:
                _log.debug("no abstract, embedding title only: %s", paper_id)

            parts = [p for p in [title, abstract] if p]
            text = "\n\n".join(parts)
            to_embed.append((paper_id, text, h))

        if not to_embed:
            return 0

        _log.info("embedding %d papers", len(to_embed))
        texts = [t for _, t, _ in to_embed]
        vecs = _embed_batch(texts, cfg)

        new_ids = []
        new_vecs_raw = []
        updated_ids = set()
        for (paper_id, _, h), vec in zip(to_embed, vecs):
            is_update = paper_id in existing_hashes
            conn.execute(
                "INSERT OR REPLACE INTO paper_vectors "
                "(paper_id, embedding, content_hash) VALUES (?, ?, ?)",
                (paper_id, _pack(vec), h),
            )
            new_ids.append(paper_id)
            new_vecs_raw.append(vec)
            if is_update:
                updated_ids.add(paper_id)

        conn.commit()
    finally:
        conn.close()

    if to_embed:
        if updated_ids:
            # Content changed for existing papers — must rebuild FAISS
            _invalidate_faiss(db_path)
        else:
            # Pure additions — try incremental append
            _append_faiss(db_path, new_ids, new_vecs_raw)

    return len(to_embed)


# ============================================================================
#  Search
# ============================================================================


def _build_faiss_from_db(
    db_path: Path,
    index_path: Path,
    ids_path: Path,
    *,
    empty_msg: str = "向量索引为空，请先运行 `autor embed`",
) -> tuple["faiss.Index", list[str]]:
    """Build or load a FAISS IndexFlatIP from a paper_vectors table.

    Generic implementation that works with any SQLite DB containing a
    ``paper_vectors`` table (main library or explore silo).

    Args:
        db_path: SQLite database with ``paper_vectors`` table.
        index_path: Path to cached ``faiss.index`` file.
        ids_path: Path to cached ``faiss_ids.json`` file.
        empty_msg: Error message when no vectors found.

    Returns:
        ``(faiss_index, paper_ids)`` tuple.

    Raises:
        FileNotFoundError: No vectors in the database.
    """
    import faiss
    import numpy as np

    if index_path.exists() and ids_path.exists():
        index = faiss.read_index(str(index_path))
        paper_ids = json.loads(ids_path.read_text("utf-8"))
        return index, paper_ids

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT paper_id, embedding FROM paper_vectors"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise FileNotFoundError(empty_msg)

    # Validate blob dimensions: use first row to determine dim, skip corrupted rows
    expected_blob_len = len(rows[0][1])
    dim = expected_blob_len // 4
    if expected_blob_len == 0 or expected_blob_len % 4 != 0:
        raise ValueError(f"First embedding blob has invalid length: {expected_blob_len}")

    valid_rows = []
    for r in rows:
        if len(r[1]) != expected_blob_len:
            _log.warning("Skipping paper %s: blob length %d != expected %d",
                         r[0], len(r[1]), expected_blob_len)
            continue
        valid_rows.append(r)

    if not valid_rows:
        raise FileNotFoundError("No valid embedding rows after dimension check")

    paper_ids = [r[0] for r in valid_rows]
    vecs = np.array(
        [list(struct.unpack(f"{dim}f", r[1])) for r in valid_rows],
        dtype="float32",
    )
    faiss.normalize_L2(vecs)

    index = faiss.IndexFlatIP(dim)
    index.add(vecs)

    faiss.write_index(index, str(index_path))
    ids_path.write_text(
        json.dumps(paper_ids, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return index, paper_ids


def _build_faiss_index(db_path: Path) -> tuple["faiss.Index", list[str]]:
    """Build or load a FAISS IndexFlatIP for the main library."""
    idx_p, ids_p = _faiss_paths(db_path)
    return _build_faiss_from_db(db_path, idx_p, ids_p)


def _vsearch_faiss(
    query: str,
    index: "faiss.Index",
    paper_ids: list[str],
    top_k: int,
    cfg: Config | None = None,
) -> list[tuple[str, float]]:
    """Run a FAISS similarity search, returning ``(paper_id, score)`` pairs.

    Args:
        query: Natural-language query text.
        index: FAISS ``IndexFlatIP`` instance.
        paper_ids: Paper ID list aligned with the index.
        top_k: Number of results to return.
        cfg: Optional config for embedding model.

    Returns:
        List of ``(paper_id, score)`` sorted by descending similarity.
    """
    import faiss
    import numpy as np

    q_vec = np.array([_embed_text(query, cfg)], dtype="float32")
    faiss.normalize_L2(q_vec)

    fetch_k = min(top_k, index.ntotal)
    scores, indices = index.search(q_vec, fetch_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        results.append((paper_ids[idx], float(score)))
    return results


def vsearch(
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
    """语义向量检索，使用 FAISS 加速余弦相似度搜索。

    将查询文本编码为向量，通过 FAISS IndexFlatIP 检索最相似的论文。
    FAISS 索引在首次查询时自动构建并缓存到磁盘，向量变更后自动失效重建。

    Args:
        query: 自然语言查询文本。
        db_path: SQLite 数据库路径（需包含 ``paper_vectors`` 表）。
        top_k: 最多返回条数，为 ``None`` 时从 ``cfg.embed.top_k`` 读取。
        cfg: 可选的 :class:`~autor.config.Config`，用于加载嵌入模型。
        year: 年份过滤（``"2023"`` / ``"2020-2024"`` / ``"2020-"``）。
        journal: 期刊名过滤（LIKE 模糊匹配）。
        paper_type: 论文类型过滤（如 ``"review"``、``"journal-article"``）。
        paper_ids: 论文 UUID 白名单，仅返回集合内的结果。

    Returns:
        论文字典列表，按 ``score`` 降序排列。每项包含
        ``paper_id``, ``title``, ``authors``, ``year``, ``journal``, ``score``。

    Raises:
        FileNotFoundError: 索引文件或 ``paper_vectors`` 表不存在。
    """
    import faiss
    import numpy as np

    if top_k is None:
        top_k = cfg.embed.top_k if cfg is not None else 10

    if not db_path.exists():
        raise FileNotFoundError(
            f"索引文件不存在：{db_path}\n请先运行 `autor index`"
        )

    conn = sqlite3.connect(db_path)
    try:
        has_vectors = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_vectors'"
        ).fetchone()
        if not has_vectors:
            raise FileNotFoundError(
                "向量索引不存在，请先运行 `autor embed`"
            )
    finally:
        conn.close()

    index, faiss_ids = _build_faiss_index(db_path)

    q_vec = np.array([_embed_text(query, cfg)], dtype="float32")
    faiss.normalize_L2(q_vec)

    # Fetch more candidates when post-filtering is needed
    fetch_k = top_k * 5 if (year or journal or paper_type or paper_ids) else top_k
    fetch_k = min(fetch_k, index.ntotal)
    scores, indices = index.search(q_vec, fetch_k)

    # Load metadata from FTS5 table
    conn = sqlite3.connect(db_path)
    try:
        has_fts = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='papers'"
        ).fetchone()
        meta_map: dict[str, dict] = {}
        if has_fts:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(
                "SELECT paper_id, title, authors, year, journal, citation_count, paper_type FROM papers"
            ).fetchall():
                meta_map[row["paper_id"]] = dict(row)
        # Load dir_name mapping
        dir_map: dict[str, str] = {}
        has_reg = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='papers_registry'"
        ).fetchone()
        if has_reg:
            for row in conn.execute("SELECT id, dir_name FROM papers_registry").fetchall():
                dir_map[row[0]] = row[1]
    finally:
        conn.close()

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        pid = faiss_ids[idx]
        meta = meta_map.get(pid, {})
        results.append({
            "paper_id": pid,
            "dir_name": dir_map.get(pid, ""),
            "title": meta.get("title") or pid,
            "authors": meta.get("authors") or "",
            "year": meta.get("year") or "",
            "journal": meta.get("journal") or "",
            "citation_count": meta.get("citation_count") or "",
            "paper_type": meta.get("paper_type") or "",
            "score": float(score),
        })

    if paper_ids is not None:
        results = [r for r in results if r["paper_id"] in paper_ids]
    if year or journal or paper_type:
        results = _post_filter(results, year=year, journal=journal, paper_type=paper_type)

    return results[:top_k]


def _safe_year(r: dict) -> int | None:
    """Extract year as int, return None if missing or invalid."""
    val = r.get("year", "")
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _post_filter(
    results: list[dict],
    *,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
) -> list[dict]:
    """对向量检索结果做年份/期刊/类型过滤。"""
    from autor.papers import parse_year_range

    filtered = results
    if year:
        start_i, end_i = parse_year_range(year)
        if start_i is not None and end_i is not None:
            filtered = [r for r in filtered
                        if _safe_year(r) is not None and start_i <= _safe_year(r) <= end_i]
        elif start_i is not None:
            filtered = [r for r in filtered
                        if _safe_year(r) is not None and _safe_year(r) >= start_i]
        elif end_i is not None:
            filtered = [r for r in filtered
                        if _safe_year(r) is not None and _safe_year(r) <= end_i]
    if journal:
        j_lower = journal.lower()
        filtered = [r for r in filtered if j_lower in str(r.get("journal", "")).lower()]
    if paper_type:
        t_lower = paper_type.lower()
        filtered = [r for r in filtered if t_lower in str(r.get("paper_type", "")).lower()]
    return filtered
