from __future__ import annotations

import os
from types import SimpleNamespace

from autor import vectors
from autor.config import _build_config


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

    seen: dict[str, str | None] = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, device: str):
            self.model_name = model_name
            self.device = device

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
        def __init__(self, model_name: str, device: str):
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
