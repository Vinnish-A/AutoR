from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from autor import vectors
from autor.config import _build_config
from autor.loader import MarkdownChunk, chunk_markdown_text

_SENTINEL_QUERY = "the cytokine storm index dropped to 0.03 within 48 hours"


def _make_paragraph(seed: str, repeat: int = 18) -> str:
    return " ".join(f"{seed} segment {idx} preserves clinically relevant context." for idx in range(repeat))


def _medical_markdown() -> str:
    return (
        "# Clinical biomarker trial\n\n"
        "## Abstract\n\n"
        f"{_make_paragraph('abstract signal overview', repeat=7)}\n\n"
        "## Methods\n\n"
        f"{_make_paragraph('flow cytometry pipeline and sampling schedule', repeat=7)}\n\n"
        "## Results\n\n"
        f"{_make_paragraph('results paragraph one tracks inflammatory drift', repeat=7)}\n\n"
        f"{_make_paragraph('results paragraph two tracks lymphocyte rescue', repeat=7)}\n\n"
        f"{_make_paragraph(_SENTINEL_QUERY, repeat=6)}"
    )


def _create_medical_paper(tmp_path: Path) -> tuple[Path, str, str]:
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir()

    dir_name = "Li-2026-CytokineTrial"
    paper_id = "paper-immune-1"
    paper_dir = papers_dir / dir_name
    paper_dir.mkdir()
    (paper_dir / "meta.json").write_text(
        json.dumps(
            {
                "id": paper_id,
                "title": "Clinical biomarker trial",
                "authors": ["Lan Li", "Ming Zhao"],
                "year": 2026,
                "journal": "Journal of Translational Immunology",
                "doi": "10.9999/jti.2026.001",
                "abstract": "Short abstract fallback that should be ignored once full text is present.",
                "paper_type": "journal-article",
                "citation_count": {"crossref": 3},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (paper_dir / "paper.md").write_text(_medical_markdown(), encoding="utf-8")
    return papers_dir, paper_id, dir_name


def _fake_vector(text: str) -> list[float]:
    lower = text.lower()
    return [
        6.0 if _SENTINEL_QUERY in lower else 0.0,
        2.0 if "section: results" in lower else 0.0,
        1.5 if "section: methods" in lower or "flow cytometry" in lower else 0.0,
        0.5 if "section: abstract" in lower else 0.0,
        0.1,
    ]


def _fake_embed_batch(texts: list[str], cfg=None) -> list[list[float]]:
    return [_fake_vector(text) for text in texts]


def _body(chunk: MarkdownChunk) -> str:
    return chunk.content.split("\n", 2)[2]


@pytest.fixture()
def fake_faiss(monkeypatch):
    store: dict[str, object] = {}

    class _FakeIndexFlatIP:
        def __init__(self, dim: int):
            self.dim = dim
            self.vectors = np.zeros((0, dim), dtype="float32")

        @property
        def ntotal(self) -> int:
            return int(self.vectors.shape[0])

        def add(self, arr):
            arr = np.array(arr, dtype="float32")
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            if self.vectors.size == 0:
                self.vectors = arr.copy()
            else:
                self.vectors = np.vstack([self.vectors, arr])

        def search(self, q, k: int):
            scores = self.vectors @ np.array(q, dtype="float32")[0]
            order = np.argsort(-scores)
            top = order[:k]
            out_scores = np.full((1, k), -1.0, dtype="float32")
            out_indices = np.full((1, k), -1, dtype="int64")
            for i, idx in enumerate(top):
                out_scores[0, i] = float(scores[idx])
                out_indices[0, i] = int(idx)
            return out_scores, out_indices

        def clone(self):
            copied = _FakeIndexFlatIP(self.dim)
            copied.vectors = self.vectors.copy()
            return copied

    def _normalize_l2(arr):
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr /= norms

    def _write_index(index, path: str):
        store[path] = index.clone()

    def _read_index(path: str):
        return store[path].clone()

    module = SimpleNamespace(
        IndexFlatIP=_FakeIndexFlatIP,
        normalize_L2=_normalize_l2,
        write_index=_write_index,
        read_index=_read_index,
    )
    monkeypatch.setitem(sys.modules, "faiss", module)
    return module


def test_load_model_sets_hf_endpoint_before_sentence_transformers_import(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTOR_HF_ENDPOINT", raising=False)
    monkeypatch.delenv("HF_ENDPOINT", raising=False)

    cfg = _build_config(
        {
            "embed": {
                "source": "huggingface",
                "hf_endpoint": "https://hf-mirror.example",
                "device": "cpu",
                "model": "test-model",
            }
        },
        tmp_path,
    )

    seen: dict[str, str | bool | None] = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, device: str, **kwargs):
            self.model_name = model_name
            self.device = device
            seen["trust_remote_code"] = kwargs.get("trust_remote_code")

    def fake_import_module(name: str):
        assert name == "sentence_transformers"
        seen["hf_endpoint_at_import"] = os.environ.get("HF_ENDPOINT")
        return SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)

    monkeypatch.setattr(vectors.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(vectors, "_resolve_model_path", lambda *args: None)
    vectors._model_cache.clear()

    prev_hf_endpoint = os.environ.get("HF_ENDPOINT")
    try:
        model = vectors._load_model(cfg)
    finally:
        if prev_hf_endpoint is None:
            monkeypatch.delenv("HF_ENDPOINT", raising=False)
        else:
            monkeypatch.setenv("HF_ENDPOINT", prev_hf_endpoint)

    assert seen["hf_endpoint_at_import"] == "https://hf-mirror.example"
    assert seen["trust_remote_code"] is True
    assert model.model_name == "test-model"
    assert model.device == "cpu"


def test_load_model_overrides_modelscope_cache_from_cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELSCOPE_CACHE", "/preexisting-cache")
    cfg = _build_config(
        {
            "embed": {
                "source": "modelscope",
                "cache_dir": str(tmp_path / "cfg-cache"),
                "device": "cpu",
                "model": "test-model",
            }
        },
        tmp_path,
    )

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, device: str, **kwargs):
            self.model_name = model_name
            self.device = device

    monkeypatch.setattr(
        vectors.importlib,
        "import_module",
        lambda name: SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    monkeypatch.setattr(vectors, "_resolve_model_path", lambda *args: None)
    vectors._model_cache.clear()

    prev_modelscope_cache = os.environ.get("MODELSCOPE_CACHE")
    try:
        vectors._load_model(cfg)
        assert os.environ.get("MODELSCOPE_CACHE") == str(tmp_path / "cfg-cache")
    finally:
        if prev_modelscope_cache is None:
            monkeypatch.delenv("MODELSCOPE_CACHE", raising=False)
        else:
            monkeypatch.setenv("MODELSCOPE_CACHE", prev_modelscope_cache)


def test_load_model_prefers_builtin_qwen_implementation(tmp_path, monkeypatch):
    cfg = _build_config(
        {
            "embed": {
                "source": "huggingface",
                "device": "cpu",
                "model": "Alibaba-NLP/gte-Qwen2-1.5B-instruct",
            }
        },
        tmp_path,
    )

    seen: dict[str, bool] = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, device: str, **kwargs):
            self.model_name = model_name
            self.device = device
            seen["trust_remote_code"] = kwargs.get("trust_remote_code")

    monkeypatch.setattr(
        vectors.importlib,
        "import_module",
        lambda name: SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    monkeypatch.setattr(vectors, "_resolve_model_path", lambda *args: None)
    vectors._model_cache.clear()

    model = vectors._load_model(cfg)

    assert seen["trust_remote_code"] is False
    assert model.model_name == "Alibaba-NLP/gte-Qwen2-1.5B-instruct"
    assert model.device == "cpu"


def test_chunk_markdown_text_splits_sections_with_overlap():
    chunks = chunk_markdown_text(
        _medical_markdown(),
        title="Clinical biomarker trial",
        max_chars=800,
        overlap_chars=100,
    )

    assert len(chunks) == 5
    assert all(chunk.content.startswith("Title: Clinical biomarker trial\nSection: ") for chunk in chunks)
    assert [chunk.section for chunk in chunks] == ["Abstract", "Methods", "Results", "Results", "Results"]
    assert _body(chunks[2])[-80:].strip() in _body(chunks[3])


def test_build_vectors_writes_chunk_rows_and_aggregated_paper_vector(tmp_path, monkeypatch, fake_faiss):
    papers_dir, paper_id, _dir_name = _create_medical_paper(tmp_path)
    db_path = tmp_path / "index.db"

    monkeypatch.setattr(vectors, "_embed_batch", _fake_embed_batch)

    count = vectors.build_vectors(papers_dir, db_path, rebuild=False)

    conn = sqlite3.connect(db_path)
    try:
        chunk_rows = conn.execute(
            "SELECT chunk_id, chunk_content FROM paper_chunks WHERE paper_id = ? ORDER BY chunk_id",
            (paper_id,),
        ).fetchall()
        paper_rows = conn.execute("SELECT paper_id FROM paper_vectors").fetchall()
    finally:
        conn.close()

    assert count == 5
    assert len(chunk_rows) == 5
    assert chunk_rows[0][0] == f"{paper_id}#0001"
    assert "Section: Results" in chunk_rows[-1][1]
    assert len(paper_rows) == 1


def test_build_vectors_clears_legacy_paper_vectors_on_pipeline_upgrade(tmp_path, monkeypatch, fake_faiss):
    papers_dir, paper_id, _dir_name = _create_medical_paper(tmp_path)
    db_path = tmp_path / "index.db"
    (tmp_path / "faiss.index").write_text("stale", encoding="utf-8")
    (tmp_path / "faiss_ids.json").write_text("stale", encoding="utf-8")

    conn = sqlite3.connect(db_path)
    try:
        vectors._ensure_schema(conn)
        conn.execute(
            "INSERT INTO paper_vectors (paper_id, embedding, content_hash) VALUES (?, ?, ?)",
            ("legacy-paper", vectors._pack([0.1, 0.2, 0.3]), "old-hash"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(vectors, "_embed_batch", _fake_embed_batch)
    count = vectors.build_vectors(papers_dir, db_path, rebuild=False)

    conn = sqlite3.connect(db_path)
    try:
        remaining_legacy = conn.execute(
            "SELECT paper_id FROM paper_vectors WHERE paper_id = ?",
            ("legacy-paper",),
        ).fetchone()
        pipeline = conn.execute(
            "SELECT value FROM vector_meta WHERE key = 'main_pipeline'",
        ).fetchone()
        chunk_count = conn.execute(
            "SELECT COUNT(*) FROM paper_chunks WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert count == 5
    assert remaining_legacy is None
    assert pipeline[0] == "paper-chunks-v1"
    assert chunk_count == 5
    assert not (tmp_path / "faiss.index").exists()
    assert not (tmp_path / "faiss_ids.json").exists()


def test_vsearch_returns_paper_by_best_matching_result_chunk(tmp_path, monkeypatch, fake_faiss):
    papers_dir, paper_id, dir_name = _create_medical_paper(tmp_path)
    db_path = tmp_path / "index.db"

    monkeypatch.setattr(vectors, "_embed_batch", _fake_embed_batch)
    monkeypatch.setattr(vectors, "_embed_query", lambda query, cfg=None: _fake_vector(query))
    vectors.build_vectors(papers_dir, db_path, rebuild=False)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE papers (
                paper_id TEXT,
                title TEXT,
                authors TEXT,
                year INTEGER,
                journal TEXT,
                citation_count TEXT,
                paper_type TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE papers_registry (
                id TEXT,
                dir_name TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                paper_id,
                "Clinical biomarker trial",
                "Lan Li, Ming Zhao",
                2026,
                "Journal of Translational Immunology",
                json.dumps({"crossref": 3}),
                "journal-article",
            ),
        )
        conn.execute(
            "INSERT INTO papers_registry VALUES (?, ?)",
            (paper_id, dir_name),
        )
        conn.commit()
    finally:
        conn.close()

    results = vectors.vsearch(_SENTINEL_QUERY, db_path, top_k=3)

    assert results[0]["paper_id"] == paper_id
    assert results[0]["dir_name"] == dir_name
    assert results[0]["matched_chunk_id"].startswith(f"{paper_id}#")
    assert _SENTINEL_QUERY in results[0]["matched_chunk"].lower()
