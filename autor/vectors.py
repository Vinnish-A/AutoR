"""
vectors.py — 向量嵌入与语义检索
==================================

主库默认使用全文 Markdown 分块（chunk）生成嵌入向量，存入
``paper_chunks`` 表；同时保留按论文聚合后的 ``paper_vectors`` 兼容层，
供主题建模等仍需要 paper-level 向量的模块复用。

用法：
    from autor.vectors import build_vectors, vsearch
    build_vectors(papers_dir, db_path)
    results = vsearch("turbulent drag reduction", db_path, top_k=5)
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
import os
import sqlite3
import struct
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    import faiss

    from autor.config import Config

_DEFAULT_MODEL_NAME = "Alibaba-NLP/gte-Qwen2-1.5B-instruct"
_MAIN_VECTOR_PIPELINE = "paper-chunks-v1"
_QUERY_TEMPLATE = (
    "Instruction: Given a strictly clinical or biomedical query, "
    "retrieve the corresponding evidence passage.\n"
    "Query: {query}"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_vectors (
    paper_id     TEXT PRIMARY KEY,
    embedding    BLOB NOT NULL,
    content_hash TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS paper_chunks (
    chunk_id      TEXT PRIMARY KEY,
    paper_id      TEXT NOT NULL,
    chunk_content TEXT NOT NULL,
    embedding     BLOB NOT NULL,
    content_hash  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper_id ON paper_chunks(paper_id);

CREATE TABLE IF NOT EXISTS vector_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_MIGRATE_PAPER_VECTORS_HASH = "ALTER TABLE paper_vectors ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''"
_MIGRATE_PAPER_CHUNKS_HASH = "ALTER TABLE paper_chunks ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create vector tables and apply additive schema migrations."""
    conn.executescript(_SCHEMA)
    _ensure_column(conn, "paper_vectors", "content_hash", _MIGRATE_PAPER_VECTORS_HASH)
    _ensure_column(conn, "paper_chunks", "content_hash", _MIGRATE_PAPER_CHUNKS_HASH)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(ddl)


def _content_hash(*parts: str) -> str:
    """Compute a short hash of the embedding source text."""
    text = "\n\n".join(part for part in parts if part)
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def _get_meta(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM vector_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else ""


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO vector_meta (key, value) VALUES (?, ?)",
        (key, value),
    )


# ============================================================================
#  Embedding
# ============================================================================

_model_cache: dict = {}  # key: (model_path, device) → SentenceTransformer


def _load_model(cfg: Config | None = None):
    """Load SentenceTransformer, using module-level cache to avoid reloading."""
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    # Resolve config
    if cfg is not None:
        model_name = cfg.embed.model
        cache_dir = os.path.expanduser(cfg.embed.cache_dir)
        device_cfg = cfg.embed.device
        source = cfg.embed.source
        hf_endpoint = cfg.embed.hf_endpoint
    else:
        model_name = _DEFAULT_MODEL_NAME
        cache_dir = os.path.expanduser("~/.cache/modelscope/hub/models")
        device_cfg = "auto"
        source = "modelscope"
        hf_endpoint = os.environ.get("AUTOR_HF_ENDPOINT") or os.environ.get("HF_ENDPOINT") or ""

    if source == "modelscope":
        os.environ["MODELSCOPE_CACHE"] = cache_dir
    if hf_endpoint:
        os.environ["HF_ENDPOINT"] = hf_endpoint

    SentenceTransformer = importlib.import_module("sentence_transformers").SentenceTransformer

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

    load_kwargs = {"device": device, "trust_remote_code": _should_trust_remote_code(model_name)}
    if str(device).startswith("cuda"):
        load_kwargs["model_kwargs"] = _cuda_model_kwargs(model_name)

    # Try to find or download the model
    local_path = _resolve_model_path(model_name, cache_dir, source)
    patch_context = _patch_sentence_transformers_autoconfig(model_name) if load_kwargs["trust_remote_code"] else nullcontext()
    with patch_context:
        if local_path:
            model = SentenceTransformer(local_path, **load_kwargs)
        else:
            # HuggingFace fallback: SentenceTransformer handles download internally
            _log.info("[embed] downloading model %s from HuggingFace", model_name)
            model = SentenceTransformer(model_name, **load_kwargs)

    _model_cache[cache_key] = model
    return model


def _resolve_model_path(model_name: str, cache_dir: str, source: str) -> str | None:
    """Find local model path or download via ModelScope.

    Args:
        model_name: Model ID (e.g. ``"Alibaba-NLP/gte-Qwen2-1.5B-instruct"``).
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


def _needs_qwen_config_patch(model_name: str) -> bool:
    return "qwen" in model_name.lower()


def _should_trust_remote_code(model_name: str) -> bool:
    return not _needs_qwen_config_patch(model_name)


def _cuda_model_kwargs(model_name: str) -> dict[str, object]:
    if not _needs_qwen_config_patch(model_name):
        return {"torch_dtype": "auto"}

    import torch

    return {"torch_dtype": torch.float16}


def _install_qwen_tokenizer_shims() -> None:
    module_name = "transformers.models.qwen2.tokenization_qwen2_fast"
    if importlib.util.find_spec(module_name) is not None:
        return

    import sys
    import types

    from transformers.models.qwen2 import Qwen2Tokenizer

    shim = types.ModuleType(module_name)

    class Qwen2TokenizerFast(Qwen2Tokenizer):
        pass

    shim.Qwen2TokenizerFast = Qwen2TokenizerFast
    shim.__all__ = ["Qwen2TokenizerFast"]
    sys.modules[module_name] = shim


def _patch_hf_config(model_ref: str, config):
    if hasattr(config, "rope_theta"):
        return config

    try:
        config_path = Path(model_ref) / "config.json"
        if not config_path.exists():
            from transformers.utils.hub import cached_file

            resolved = cached_file(model_ref, "config.json")
            config_path = Path(resolved)
        raw = json.loads(config_path.read_text("utf-8"))
    except Exception as e:
        _log.debug("failed to recover raw config for %s: %s", model_ref, e)
        return config

    if "rope_theta" in raw:
        config.rope_theta = raw["rope_theta"]
    return config


def _load_hf_config(model_ref: str):
    """Load a transformers config and restore fields dropped by newer APIs."""
    from transformers import AutoConfig

    config = AutoConfig.from_pretrained(model_ref, trust_remote_code=True)
    return _patch_hf_config(model_ref, config)


@contextmanager
def _patch_sentence_transformers_autoconfig(model_name: str):
    if not _needs_qwen_config_patch(model_name):
        yield
        return

    _install_qwen_tokenizer_shims()
    from sentence_transformers.models import Transformer as STTransformer

    auto_config = STTransformer._load_config.__globals__["AutoConfig"]
    original_from_pretrained = auto_config.__dict__["from_pretrained"]

    def _patched_from_pretrained(cls, model_name_or_path: str, *args, **kwargs):
        config = original_from_pretrained.__get__(None, cls)(model_name_or_path, *args, **kwargs)
        return _patch_hf_config(model_name_or_path, config)

    auto_config.from_pretrained = classmethod(_patched_from_pretrained)
    try:
        yield
    finally:
        auto_config.from_pretrained = original_from_pretrained


# ============================================================================
#  GPU profiling & adaptive batching
# ============================================================================

_GPU_PROFILE_FILE = Path("~/.cache/autor/gpu_profile.json").expanduser()
_PROFILE_MAX_TOKENS = 4096


def _profile_cache_key(model_name: str, gpu_name: str) -> str:
    return f"{model_name}::{gpu_name}"


def _run_profile(model, cfg: Config | None = None) -> dict:
    """Profile GPU memory per sample at various sequence lengths.

    Generates dummy texts at several token counts, encodes one at a time,
    and records peak GPU memory.  Results are cached to disk so this only
    runs once per model + GPU combination.

    Returns:
        ``{"gpu_total_bytes": int, "per_sample": {token_len: bytes, ...},
           "model_name": str, "gpu_name": str, "profiled_at": str}``
    """
    import torch

    if not torch.cuda.is_available():
        return {}

    device = next(model.parameters() if hasattr(model, "parameters") else model[0].parameters()).device
    if device.type != "cuda":
        return {}

    gpu_props = torch.cuda.get_device_properties(device)
    gpu_name = gpu_props.name
    gpu_total = gpu_props.total_memory

    # Use model's tokenizer to craft texts of exact token lengths
    tokenizer = model.tokenizer

    per_sample: dict[int, int] = {}
    filler = "turbulence flow particle dynamics simulation "

    # Measure baseline: model weights already on GPU
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats(device)
    tiny = filler[:20]
    model.encode([tiny], normalize_embeddings=True, batch_size=1)
    baseline = torch.cuda.memory_allocated(device)

    model_name = cfg.embed.model if cfg is not None else _DEFAULT_MODEL_NAME

    _log.info(
        "[gpu-profile] Profiling GPU memory for %s on %s (baseline=%.0f MB, total=%.0f MB) ...",
        model_name,
        gpu_name,
        baseline / 1024**2,
        gpu_total / 1024**2,
    )

    # Chunked retrieval usually stays far below the model's full context window,
    # and _estimate_mem_per_sample() already extrapolates beyond the profiled range.
    # Capping the probe keeps first-run profiling practical on 8 GB GPUs.
    tgt_tokens = 64
    max_tokens = min(getattr(model, "max_seq_length", 32768) or 32768, _PROFILE_MAX_TOKENS)
    while tgt_tokens <= max_tokens:
        raw = filler * (tgt_tokens // 4 + 10)
        ids = tokenizer.encode(raw)[:tgt_tokens]
        text = tokenizer.decode(ids, skip_special_tokens=True)

        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)

        try:
            model.encode([text], normalize_embeddings=True, batch_size=1)
            peak = torch.cuda.max_memory_allocated(device)
            incremental = peak - baseline
            per_sample[tgt_tokens] = incremental
            _log.info(
                "[gpu-profile]   tokens=%5d  incremental=%6.0f MB  (peak=%.0f MB)",
                tgt_tokens,
                incremental / 1024**2,
                peak / 1024**2,
            )
        except torch.cuda.OutOfMemoryError:
            _log.info("[gpu-profile]   tokens=%5d  OOM — max single-sample capacity found", tgt_tokens)
            torch.cuda.empty_cache()
            break

        tgt_tokens *= 2

    return {
        "gpu_total_bytes": gpu_total,
        "baseline_bytes": baseline,
        "gpu_name": gpu_name,
        "model_name": model_name,
        "per_sample": {str(k): v for k, v in per_sample.items()},
        "profiled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _load_or_create_profile(model, cfg: Config | None = None) -> dict:
    """Load cached GPU profile or run profiling."""
    import torch

    if not torch.cuda.is_available():
        return {}

    device = next(model.parameters() if hasattr(model, "parameters") else model[0].parameters()).device
    if device.type != "cuda":
        return {}

    gpu_name = torch.cuda.get_device_properties(device).name
    model_name = cfg.embed.model if cfg is not None else _DEFAULT_MODEL_NAME
    cache_key = _profile_cache_key(model_name, gpu_name)

    # Try loading from disk
    if _GPU_PROFILE_FILE.exists():
        try:
            all_profiles = json.loads(_GPU_PROFILE_FILE.read_text("utf-8"))
            if cache_key in all_profiles:
                _log.debug("[gpu-profile] loaded cached profile for %s", cache_key)
                return all_profiles[cache_key]
        except Exception:
            pass

    # Run profiling
    profile = _run_profile(model, cfg)
    if not profile:
        return {}

    # Save to disk
    _GPU_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    all_profiles = {}
    if _GPU_PROFILE_FILE.exists():
        try:
            all_profiles = json.loads(_GPU_PROFILE_FILE.read_text("utf-8"))
        except Exception:
            pass
    all_profiles[cache_key] = profile
    _GPU_PROFILE_FILE.write_text(json.dumps(all_profiles, indent=2, ensure_ascii=False) + "\n", "utf-8")
    _log.info("[gpu-profile] saved profile to %s", _GPU_PROFILE_FILE)
    return profile


def _estimate_mem_per_sample(est_tokens: int, profile: dict) -> int:
    """Interpolate/extrapolate memory per sample from profile data.

    For sequence lengths beyond the profiled range, extrapolates using
    quadratic scaling (attention is O(n²)).
    """
    per_sample = profile.get("per_sample", {})
    if not per_sample:
        return 0

    # Convert keys to int, sort
    points = sorted((int(k), v) for k, v in per_sample.items())

    if est_tokens <= points[0][0]:
        return points[0][1]

    # Linear interpolation within profiled range
    for i in range(len(points) - 1):
        t0, m0 = points[i]
        t1, m1 = points[i + 1]
        if t0 <= est_tokens <= t1:
            frac = (est_tokens - t0) / (t1 - t0)
            return int(m0 + frac * (m1 - m0))

    # Extrapolate beyond max profiled point with quadratic scaling
    t_max, m_max = points[-1]
    ratio = est_tokens / t_max
    return int(m_max * ratio * ratio)


def _compute_batch_size(est_tokens: int, profile: dict, safety_factor: float = 0.85) -> int:
    """Compute optimal batch_size for texts of a given token length.

    Uses incremental memory per sample (peak minus baseline) from the
    profile, so model weight memory is excluded from the calculation.
    """
    if not profile or not profile.get("per_sample"):
        return 8  # conservative default

    gpu_total = profile["gpu_total_bytes"]
    baseline = profile.get("baseline_bytes", 0)
    mem_per_sample = _estimate_mem_per_sample(est_tokens, profile)

    if mem_per_sample <= 0:
        return 8

    # Available = total GPU memory * safety - baseline (model weights etc.)
    available = gpu_total * safety_factor - baseline
    if available <= 0:
        return 1

    bs = int(available / mem_per_sample)
    return max(1, min(bs, 128))


def _embed_text(text: str, cfg: Config | None = None) -> list[float]:
    model = _load_model(cfg)
    vec = model.encode([text], normalize_embeddings=True)
    return vec[0].tolist()


def _embed_query(query: str, cfg: Config | None = None) -> list[float]:
    return _embed_text(_QUERY_TEMPLATE.format(query=query.strip()), cfg)


def _estimate_token_count(text: str) -> int:
    ascii_chars = sum(ord(ch) < 128 for ch in text)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii_chars // 2)


def _embed_batch(texts: list[str], cfg: Config | None = None) -> list[list[float]]:
    """Embed texts with adaptive GPU batch sizing.

    Sorts texts by estimated token count, groups them into buckets of
    similar length, and computes an optimal batch_size per bucket based
    on a one-time GPU memory profile.  Falls back to halving the batch
    (and ultimately CPU) on OOM.
    """

    model = _load_model(cfg)
    profile = _load_or_create_profile(model, cfg)

    if not profile:
        # CPU path or profiling unavailable — use conservative fixed batch
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=8, show_progress_bar=len(texts) > 100)
        return vecs.tolist()

    # Estimate token count cheaply from text length; OOM retry below still
    # protects us if a bucket ends up slightly too optimistic.
    est_tokens = [_estimate_token_count(t) for t in texts]

    # Build indexed list and sort by token count
    indexed = sorted(enumerate(texts), key=lambda x: est_tokens[x[0]])

    # Group into buckets by similar token length
    # Bucket boundaries: powers of 2 from 64 to model max
    boundaries = [64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384]
    buckets: dict[int, list[int]] = {}  # boundary -> list of original indices

    for orig_idx, _text in indexed:
        tlen = est_tokens[orig_idx]
        # Find the smallest boundary >= tlen
        bucket_key = boundaries[-1]
        for b in boundaries:
            if tlen <= b:
                bucket_key = b
                break
        buckets.setdefault(bucket_key, []).append(orig_idx)

    # Encode each bucket with adaptive batch_size
    import torch

    results = [None] * len(texts)
    total_done = 0
    show_progress = len(texts) > 100

    for bucket_key in sorted(buckets.keys()):
        indices = buckets[bucket_key]
        bucket_texts = [texts[i] for i in indices]
        bs = _compute_batch_size(bucket_key, profile)

        _log.debug("[embed] bucket tokens<=%d: %d texts, batch_size=%d", bucket_key, len(bucket_texts), bs)

        # Encode with OOM retry
        encoded = None
        while encoded is None:
            try:
                encoded = model.encode(bucket_texts, normalize_embeddings=True, batch_size=bs)
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                if bs > 1:
                    bs = max(1, bs // 2)
                    _log.warning("[embed] OOM, retrying with batch_size=%d", bs)
                else:
                    _log.warning("[embed] OOM at batch_size=1, falling back to CPU")
                    model_cpu = model.to("cpu")
                    encoded = model_cpu.encode(bucket_texts, normalize_embeddings=True, batch_size=1)
                    model.to("cuda")

        for idx, vec in zip(indices, encoded):
            results[idx] = vec.tolist() if hasattr(vec, "tolist") else list(vec)
        total_done += len(indices)

    return results


class QwenEmbedder:
    """BERTopic-compatible embedder wrapping the configured retrieval model.

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
    ids_path.write_text(json.dumps(paper_ids, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_faiss(db_path: Path, new_ids: list[str], new_vecs: list[list[float]]) -> None:
    """Append new vectors to existing FAISS index, or invalidate if not possible.

    Args:
        db_path: SQLite 数据库路径。
        new_ids: 新增论文 ID 列表。
        new_vecs: 对应的向量列表（已归一化）。
    """
    idx_p, ids_p = _faiss_paths(db_path)
    _append_faiss_files(idx_p, ids_p, new_ids, new_vecs)


def _current_model_name(cfg: Config | None = None) -> str:
    return cfg.embed.model if cfg is not None else _DEFAULT_MODEL_NAME


def _reset_vector_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM paper_chunks")
    conn.execute("DELETE FROM paper_vectors")


def _should_reset_main_vectors(conn: sqlite3.Connection, cfg: Config | None = None) -> bool:
    stored_pipeline = _get_meta(conn, "main_pipeline")
    stored_model = _get_meta(conn, "main_model")
    current_model = _current_model_name(cfg)

    if stored_pipeline and stored_model:
        return stored_pipeline != _MAIN_VECTOR_PIPELINE or stored_model != current_model

    has_legacy_vectors = conn.execute("SELECT 1 FROM paper_vectors LIMIT 1").fetchone() is not None
    has_chunks = conn.execute("SELECT 1 FROM paper_chunks LIMIT 1").fetchone() is not None
    return has_legacy_vectors and not has_chunks


def _write_main_vector_meta(conn: sqlite3.Connection, cfg: Config | None = None) -> None:
    _set_meta(conn, "main_pipeline", _MAIN_VECTOR_PIPELINE)
    _set_meta(conn, "main_model", _current_model_name(cfg))


def _aggregate_paper_vector(chunk_vecs: list[list[float]]) -> list[float]:
    if not chunk_vecs:
        return []

    length = len(chunk_vecs[0])
    sums = [0.0] * length
    for vec in chunk_vecs:
        for idx, value in enumerate(vec):
            sums[idx] += value

    scale = 1.0 / len(chunk_vecs)
    return [value * scale for value in sums]


# ============================================================================
#  Build
# ============================================================================


def build_vectors(
    papers_dir: Path,
    db_path: Path,
    rebuild: bool = False,
    cfg: Config | None = None,
    *,
    paper_ids: set[str] | None = None,
) -> int:
    """为主库全文分块生成语义向量，并维护兼容的 paper-level 向量。

    Args:
        papers_dir: 已入库论文目录。
        db_path: SQLite 数据库路径，不存在时自动创建。
        rebuild: 为 ``True`` 时清空旧向量后重建。
        cfg: 可选的 :class:`~autor.config.Config`，用于读取模型/设备配置。
        paper_ids: 可选；仅为指定 UUID 的论文增量生成向量。``rebuild=True`` 时忽略。

    Returns:
        本次新写入的 chunk 向量数量。
    """
    from autor.loader import chunk_markdown_text, load_l4
    from autor.papers import iter_paper_dirs, read_meta

    db_path.parent.mkdir(parents=True, exist_ok=True)

    pipeline_reset = False
    updated_ids: set[str] = set()
    new_chunk_ids: list[str] = []
    new_chunk_vecs: list[list[float]] = []
    chunk_count = 0

    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)
        pipeline_reset = rebuild or _should_reset_main_vectors(conn, cfg)
        if pipeline_reset:
            _reset_vector_tables(conn)
            conn.commit()

        # Build lookup of existing hashes for incremental check
        existing_hashes: dict[str, str] = {}
        if not pipeline_reset:
            for row in conn.execute("SELECT paper_id, content_hash FROM paper_vectors").fetchall():
                existing_hashes[row[0]] = row[1]

        chunk_rows_buffer: list[tuple[str, str, str, bytes, str]] = []
        paper_rows_buffer: list[tuple[str, bytes, str]] = []
        chunk_flush_size = 4096
        embed_batch_size = 1024
        can_append_faiss = not pipeline_reset
        processed_papers = 0
        target_ids = None if rebuild or paper_ids is None else set(paper_ids)
        for pdir in iter_paper_dirs(papers_dir):
            try:
                meta = read_meta(pdir)
            except (ValueError, FileNotFoundError) as e:
                _log.debug("failed to read meta.json in %s: %s", pdir.name, e)
                continue
            paper_id = meta.get("id") or pdir.name
            if target_ids is not None and paper_id not in target_ids:
                continue

            title = (meta.get("title") or "").strip()
            abstract = (meta.get("abstract") or "").strip()
            md_path = pdir / "paper.md"
            full_markdown = load_l4(md_path) if md_path.exists() else ""
            body_source = full_markdown.strip() or abstract or title
            if not title and not body_source:
                continue

            paper_hash = _content_hash(title, body_source)
            if not pipeline_reset and existing_hashes.get(paper_id) == paper_hash:
                continue  # content unchanged, skip

            chunks = chunk_markdown_text(body_source, title=title or pdir.name)
            if not chunks:
                continue

            if paper_id in existing_hashes:
                updated_ids.add(paper_id)
                if can_append_faiss:
                    new_chunk_ids.clear()
                    new_chunk_vecs.clear()
                    can_append_faiss = False

            conn.execute("DELETE FROM paper_chunks WHERE paper_id = ?", (paper_id,))

            chunk_texts = [chunk.content for chunk in chunks]
            paper_sums: list[float] | None = None
            paper_chunk_count = 0
            for start in range(0, len(chunk_texts), embed_batch_size):
                batch_texts = chunk_texts[start : start + embed_batch_size]
                vecs = _embed_batch(batch_texts, cfg)
                for offset, (chunk_text, vec) in enumerate(zip(batch_texts, vecs), start=start + 1):
                    chunk_id = f"{paper_id}#{offset:04d}"
                    chunk_rows_buffer.append((chunk_id, paper_id, chunk_text, _pack(vec), paper_hash))
                    if paper_sums is None:
                        paper_sums = list(vec)
                    else:
                        for idx, value in enumerate(vec):
                            paper_sums[idx] += value
                    paper_chunk_count += 1
                    if can_append_faiss:
                        new_chunk_ids.append(chunk_id)
                        new_chunk_vecs.append(vec)
                    chunk_count += 1

                if len(chunk_rows_buffer) >= chunk_flush_size:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO paper_chunks
                            (chunk_id, paper_id, chunk_content, embedding, content_hash)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        chunk_rows_buffer,
                    )
                    chunk_rows_buffer.clear()
                    conn.commit()

            if paper_sums is not None and paper_chunk_count > 0:
                paper_vec = [value / paper_chunk_count for value in paper_sums]
                paper_rows_buffer.append((paper_id, _pack(paper_vec), paper_hash))
                processed_papers += 1

        if processed_papers:
            _log.info("embedding %d chunks from %d papers", chunk_count, processed_papers)
        if chunk_rows_buffer:
            conn.executemany(
                """
                INSERT OR REPLACE INTO paper_chunks
                    (chunk_id, paper_id, chunk_content, embedding, content_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                chunk_rows_buffer,
            )
        if paper_rows_buffer:
            conn.executemany(
                "INSERT OR REPLACE INTO paper_vectors (paper_id, embedding, content_hash) VALUES (?, ?, ?)",
                paper_rows_buffer,
            )
        _write_main_vector_meta(conn, cfg)
        conn.commit()
    finally:
        conn.close()

    if pipeline_reset or updated_ids:
        _invalidate_faiss(db_path)
    elif new_chunk_ids:
        _append_faiss(db_path, new_chunk_ids, new_chunk_vecs)

    return chunk_count


# ============================================================================
#  Search
# ============================================================================


def _build_faiss_from_db(
    db_path: Path,
    index_path: Path,
    ids_path: Path,
    *,
    table_name: str = "paper_vectors",
    id_column: str = "paper_id",
    empty_msg: str = "向量索引为空，请先运行 `autor embed`",
) -> tuple[faiss.Index, list[str]]:
    """Build or load a FAISS IndexFlatIP from a vector table.

    Generic implementation that works with any SQLite DB containing a
    vector table with ``(<id_column>, embedding)`` columns.

    Args:
        db_path: SQLite database path.
        index_path: Path to cached ``faiss.index`` file.
        ids_path: Path to cached ``faiss_ids.json`` file.
        table_name: Table containing embeddings.
        id_column: Identifier column aligned with the FAISS rows.
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
        rows = conn.execute(f"SELECT {id_column}, embedding FROM {table_name}").fetchall()
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
            _log.warning("Skipping paper %s: blob length %d != expected %d", r[0], len(r[1]), expected_blob_len)
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
    ids_path.write_text(json.dumps(paper_ids, ensure_ascii=False) + "\n", encoding="utf-8")
    return index, paper_ids


def _build_paper_faiss_index(db_path: Path) -> tuple[faiss.Index, list[str]]:
    """Build or load a FAISS IndexFlatIP over ``paper_vectors``."""
    idx_p, ids_p = _faiss_paths(db_path)
    return _build_faiss_from_db(db_path, idx_p, ids_p, table_name="paper_vectors", id_column="paper_id")


def _build_chunk_faiss_index(db_path: Path) -> tuple[faiss.Index, list[str]]:
    """Build or load a FAISS IndexFlatIP over ``paper_chunks``."""
    idx_p, ids_p = _faiss_paths(db_path)
    return _build_faiss_from_db(db_path, idx_p, ids_p, table_name="paper_chunks", id_column="chunk_id")


def _load_paper_meta_maps(db_path: Path) -> tuple[dict[str, dict], dict[str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        has_fts = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='papers'").fetchone()
        meta_map: dict[str, dict] = {}
        if has_fts:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(
                "SELECT paper_id, title, authors, year, journal, citation_count, paper_type FROM papers"
            ).fetchall():
                meta_map[row["paper_id"]] = dict(row)

        dir_map: dict[str, str] = {}
        has_reg = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='papers_registry'").fetchone()
        if has_reg:
            for row in conn.execute("SELECT id, dir_name FROM papers_registry").fetchall():
                dir_map[row[0]] = row[1]
    finally:
        conn.close()

    return meta_map, dir_map


def _load_chunk_map(db_path: Path, chunk_ids: list[str]) -> dict[str, dict]:
    if not chunk_ids:
        return {}

    conn = sqlite3.connect(db_path)
    try:
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = conn.execute(
            f"""
            SELECT chunk_id, paper_id, chunk_content
            FROM paper_chunks
            WHERE chunk_id IN ({placeholders})
            """,
            chunk_ids,
        ).fetchall()
    finally:
        conn.close()

    return {
        row[0]: {"paper_id": row[1], "chunk_content": row[2]}
        for row in rows
    }


def _vsearch_faiss(
    query: str,
    index: faiss.Index,
    row_ids: list[str],
    top_k: int,
    cfg: Config | None = None,
) -> list[tuple[str, float]]:
    """Run a FAISS similarity search, returning ``(row_id, score)`` pairs.

    Args:
        query: Natural-language query text.
        index: FAISS ``IndexFlatIP`` instance.
        row_ids: Identifier list aligned with the index.
        top_k: Number of results to return.
        cfg: Optional config for embedding model.

    Returns:
        List of ``(row_id, score)`` sorted by descending similarity.
    """
    import faiss
    import numpy as np

    q_vec = np.array([_embed_query(query, cfg)], dtype="float32")
    faiss.normalize_L2(q_vec)

    fetch_k = min(top_k, index.ntotal)
    scores, indices = index.search(q_vec, fetch_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        results.append((row_ids[idx], float(score)))
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

    主路径使用 ``paper_chunks`` 做 evidence-level 检索，并按 ``paper_id``
    进行 max-score 聚合，兼容外部仍然只消费 paper-level 结果的接口。
    若数据库尚未升级到 chunk 流程，则自动回退到旧版 ``paper_vectors`` 检索。

    Args:
        query: 自然语言查询文本。
        db_path: SQLite 数据库路径（需包含 ``paper_chunks`` 或 ``paper_vectors`` 表）。
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
        FileNotFoundError: 索引文件或向量表不存在。
    """
    if top_k is None:
        top_k = cfg.embed.top_k if cfg is not None else 10

    if not db_path.exists():
        raise FileNotFoundError(f"索引文件不存在：{db_path}\n请先运行 `autor index`")

    conn = sqlite3.connect(db_path)
    try:
        has_vectors = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_vectors'"
        ).fetchone()
        has_chunks = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_chunks'"
        ).fetchone()
        chunk_mode = bool(has_chunks and conn.execute("SELECT 1 FROM paper_chunks LIMIT 1").fetchone())
        if not has_vectors and not chunk_mode:
            raise FileNotFoundError("向量索引不存在，请先运行 `autor embed`")
    finally:
        conn.close()

    meta_map, dir_map = _load_paper_meta_maps(db_path)

    results = []
    if chunk_mode:
        index, faiss_ids = _build_chunk_faiss_index(db_path)
        multiplier = 20 if (year or journal or paper_type or paper_ids) else 10
        fetch_k = min(max(top_k * multiplier, top_k), index.ntotal)
        chunk_hits = _vsearch_faiss(query, index, faiss_ids, fetch_k, cfg=cfg)
        chunk_map = _load_chunk_map(db_path, [chunk_id for chunk_id, _score in chunk_hits])

        aggregated: dict[str, dict] = {}
        for chunk_id, score in chunk_hits:
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue
            pid = chunk["paper_id"]
            best = aggregated.get(pid)
            if best is None or score > best["score"]:
                aggregated[pid] = {
                    "score": float(score),
                    "matched_chunk_id": chunk_id,
                    "matched_chunk": chunk["chunk_content"],
                }

        for pid, hit in aggregated.items():
            meta = meta_map.get(pid, {})
            results.append(
                {
                    "paper_id": pid,
                    "dir_name": dir_map.get(pid, ""),
                    "title": meta.get("title") or pid,
                    "authors": meta.get("authors") or "",
                    "year": meta.get("year") or "",
                    "journal": meta.get("journal") or "",
                    "citation_count": meta.get("citation_count") or "",
                    "paper_type": meta.get("paper_type") or "",
                    "score": hit["score"],
                    "matched_chunk_id": hit["matched_chunk_id"],
                    "matched_chunk": hit["matched_chunk"],
                }
            )
    else:
        index, faiss_ids = _build_paper_faiss_index(db_path)
        fetch_k = top_k * 5 if (year or journal or paper_type or paper_ids) else top_k
        fetch_k = min(fetch_k, index.ntotal)
        for pid, score in _vsearch_faiss(query, index, faiss_ids, fetch_k, cfg=cfg):
            meta = meta_map.get(pid, {})
            results.append(
                {
                    "paper_id": pid,
                    "dir_name": dir_map.get(pid, ""),
                    "title": meta.get("title") or pid,
                    "authors": meta.get("authors") or "",
                    "year": meta.get("year") or "",
                    "journal": meta.get("journal") or "",
                    "citation_count": meta.get("citation_count") or "",
                    "paper_type": meta.get("paper_type") or "",
                    "score": float(score),
                }
            )

    if paper_ids is not None:
        results = [r for r in results if r["paper_id"] in paper_ids]
    if year or journal or paper_type:
        results = _post_filter(results, year=year, journal=journal, paper_type=paper_type)
    results.sort(key=lambda item: item["score"], reverse=True)
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
            filtered = [r for r in filtered if _safe_year(r) is not None and start_i <= _safe_year(r) <= end_i]
        elif start_i is not None:
            filtered = [r for r in filtered if _safe_year(r) is not None and _safe_year(r) >= start_i]
        elif end_i is not None:
            filtered = [r for r in filtered if _safe_year(r) is not None and _safe_year(r) <= end_i]
    if journal:
        j_lower = journal.lower()
        filtered = [r for r in filtered if j_lower in str(r.get("journal", "")).lower()]
    if paper_type:
        t_lower = paper_type.lower()
        filtered = [r for r in filtered if t_lower in str(r.get("paper_type", "")).lower()]
    return filtered
