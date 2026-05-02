"""Tests for autor.config — YAML loading, merging, path resolution, defaults."""

from __future__ import annotations

from autor.config import _build_config, _deep_merge, load_config


class TestDeepMerge:
    def test_scalar_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 99}
        assert _deep_merge(base, override) == {"a": 1, "b": 99}

    def test_nested_merge(self):
        base = {"llm": {"model": "gpt-4", "timeout": 30}}
        override = {"llm": {"timeout": 60}}
        result = _deep_merge(base, override)
        assert result == {"llm": {"model": "gpt-4", "timeout": 60}}

    def test_add_new_keys(self):
        base = {"a": 1}
        override = {"b": 2}
        assert _deep_merge(base, override) == {"a": 1, "b": 2}

    def test_empty_override(self):
        base = {"a": 1}
        assert _deep_merge(base, {}) == {"a": 1}

    def test_empty_base(self):
        override = {"a": 1}
        assert _deep_merge({}, override) == {"a": 1}

    def test_override_dict_with_scalar(self):
        base = {"a": {"nested": True}}
        override = {"a": "flat"}
        assert _deep_merge(base, override) == {"a": "flat"}

    def test_deep_nesting(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"c": 99}}}
        result = _deep_merge(base, override)
        assert result == {"a": {"b": {"c": 99, "d": 2}}}


class TestBuildConfig:
    def test_empty_dict_uses_defaults(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        assert cfg.llm.model == "deepseek-chat"
        assert cfg.llm.backend == "openai-compat"
        assert cfg.paths.papers_dir == "data/papers"
        assert cfg.search.top_k == 20

    def test_partial_override(self, tmp_path):
        data = {"llm": {"model": "gpt-4o", "timeout": 60}}
        cfg = _build_config(data, tmp_path)
        assert cfg.llm.model == "gpt-4o"
        assert cfg.llm.timeout == 60
        assert cfg.llm.backend == "openai-compat"  # default preserved

    def test_concurrency_min_1(self, tmp_path):
        data = {"llm": {"concurrency": 0}}
        cfg = _build_config(data, tmp_path)
        assert cfg.llm.concurrency == 1

    def test_concurrency_negative(self, tmp_path):
        data = {"llm": {"concurrency": -5}}
        cfg = _build_config(data, tmp_path)
        assert cfg.llm.concurrency == 1

    def test_api_key_none_becomes_empty(self, tmp_path):
        data = {"llm": {"api_key": None}}
        cfg = _build_config(data, tmp_path)
        assert cfg.llm.api_key == ""

    def test_ingest_defaults(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        assert cfg.ingest.extractor == "robust"
        assert cfg.ingest.chunk_page_limit == 100
        assert cfg.ingest.mineru_cloud_batch_size == 20
        assert cfg.ingest.mineru_batch_size == 20

    def test_plot_defaults(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        assert cfg.plot.host == "https://grsai.dakka.com.cn"
        assert cfg.plot.model == "gpt-image-2"
        assert cfg.plot.aspect_ratio == "auto"

    def test_null_sections_handled(self, tmp_path):
        data = {"llm": None, "paths": None}
        cfg = _build_config(data, tmp_path)
        assert cfg.llm.model == "deepseek-chat"
        assert cfg.paths.papers_dir == "data/papers"

    def test_zotero_library_id_coerced_to_str(self, tmp_path):
        data = {"zotero": {"library_id": 12345}}
        cfg = _build_config(data, tmp_path)
        assert cfg.zotero.library_id == "12345"

    def test_mineru_formula_and_table_null_use_defaults(self, tmp_path):
        data = {
            "ingest": {
                "mineru_enable_formula": None,
                "mineru_enable_table": None,
            }
        }
        cfg = _build_config(data, tmp_path)
        assert cfg.ingest.mineru_enable_formula is True
        assert cfg.ingest.mineru_enable_table is True

    def test_embed_env_vars_override_yaml(self, tmp_path, monkeypatch):
        data = {
            "embed": {
                "source": "modelscope",
                "cache_dir": "/yaml-cache",
                "model": "yaml-model",
            }
        }
        monkeypatch.setenv("AUTOR_EMBED_SOURCE", "huggingface")
        monkeypatch.setenv("AUTOR_EMBED_CACHE_DIR", "/env-cache")
        monkeypatch.setenv("AUTOR_EMBED_MODEL", "env-model")
        cfg = _build_config(data, tmp_path)
        assert cfg.embed.source == "huggingface"
        assert cfg.embed.cache_dir == "/env-cache"
        assert cfg.embed.model == "env-model"

    def test_autor_hf_endpoint_wins_over_hf_endpoint(self, tmp_path, monkeypatch):
        data = {"embed": {"hf_endpoint": "https://yaml-mirror.example"}}
        monkeypatch.setenv("AUTOR_HF_ENDPOINT", "https://autor-mirror.example")
        monkeypatch.setenv("HF_ENDPOINT", "https://generic-mirror.example")
        cfg = _build_config(data, tmp_path)
        assert cfg.embed.hf_endpoint == "https://autor-mirror.example"

    def test_empty_embed_env_vars_do_not_override_yaml(self, tmp_path, monkeypatch):
        data = {
            "embed": {
                "source": "huggingface",
                "cache_dir": "/yaml-cache",
                "model": "yaml-model",
                "hf_endpoint": "https://yaml-mirror.example",
            }
        }
        monkeypatch.setenv("AUTOR_EMBED_SOURCE", "")
        monkeypatch.setenv("AUTOR_EMBED_CACHE_DIR", "")
        monkeypatch.setenv("AUTOR_EMBED_MODEL", "")
        monkeypatch.setenv("AUTOR_HF_ENDPOINT", "")
        monkeypatch.setenv("HF_ENDPOINT", "")
        cfg = _build_config(data, tmp_path)
        assert cfg.embed.source == "huggingface"
        assert cfg.embed.cache_dir == "/yaml-cache"
        assert cfg.embed.model == "yaml-model"
        assert cfg.embed.hf_endpoint == "https://yaml-mirror.example"

    def test_plot_env_vars_override_yaml(self, tmp_path, monkeypatch):
        data = {
            "plot": {
                "host": "https://yaml.example",
                "model": "gpt-image-2",
                "aspect_ratio": "1:1",
            }
        }
        monkeypatch.setenv("AUTOR_PLOT_HOST", "https://env.example")
        monkeypatch.setenv("AUTOR_PLOT_MODEL", "gpt-image-2")
        monkeypatch.setenv("AUTOR_PLOT_ASPECT_RATIO", "auto")
        cfg = _build_config(data, tmp_path)
        assert cfg.plot.host == "https://env.example"
        assert cfg.plot.model == "gpt-image-2"
        assert cfg.plot.aspect_ratio == "auto"


class TestConfigProperties:
    def test_papers_dir_absolute(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        assert cfg.papers_dir.is_absolute()
        assert cfg.papers_dir == (tmp_path / "data" / "papers").resolve()

    def test_index_db_absolute(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        assert cfg.index_db.is_absolute()
        assert cfg.index_db == (tmp_path / "data" / "index.db").resolve()

    def test_log_file_absolute(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        assert cfg.log_file.is_absolute()

    def test_metrics_db_path(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        assert cfg.metrics_db_path == (tmp_path / "data" / "metrics.db").resolve()

    def test_topics_model_dir(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        assert cfg.topics_model_dir == (tmp_path / "data" / "topic_model").resolve()


class TestEnsureDirs:
    def test_creates_required_dirs(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        cfg.ensure_dirs()
        assert cfg.papers_dir.exists()
        assert (tmp_path / "data" / "inbox").exists()
        assert (tmp_path / "data" / "inbox-thesis").exists()
        assert (tmp_path / "data" / "inbox-doc").exists()
        assert (tmp_path / "data" / "pending").exists()
        assert (tmp_path / "workspace").exists()

    def test_idempotent(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        cfg.ensure_dirs()
        cfg.ensure_dirs()  # should not raise


class TestResolvedApiKey:
    def test_config_key_wins(self, tmp_path, monkeypatch):
        data = {"llm": {"api_key": "from-config"}}
        cfg = _build_config(data, tmp_path)
        monkeypatch.setenv("AUTOR_LLM_API_KEY", "from-env")
        assert cfg.resolved_api_key() == "from-config"

    def test_generic_env_var(self, tmp_path, monkeypatch):
        cfg = _build_config({}, tmp_path)
        monkeypatch.setenv("AUTOR_LLM_API_KEY", "generic-key")
        assert cfg.resolved_api_key() == "generic-key"

    def test_backend_specific_env_openai(self, tmp_path, monkeypatch):
        cfg = _build_config({"llm": {"backend": "openai-compat"}}, tmp_path)
        monkeypatch.delenv("AUTOR_LLM_API_KEY", raising=False)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "dsk-123")
        assert cfg.resolved_api_key() == "dsk-123"

    def test_backend_specific_env_anthropic(self, tmp_path, monkeypatch):
        cfg = _build_config({"llm": {"backend": "anthropic"}}, tmp_path)
        monkeypatch.delenv("AUTOR_LLM_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")
        assert cfg.resolved_api_key() == "ant-key"

    def test_backend_specific_env_google(self, tmp_path, monkeypatch):
        cfg = _build_config({"llm": {"backend": "google"}}, tmp_path)
        monkeypatch.delenv("AUTOR_LLM_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "goog-key")
        assert cfg.resolved_api_key() == "goog-key"

    def test_no_key_returns_empty(self, tmp_path, monkeypatch):
        cfg = _build_config({}, tmp_path)
        for v in ("AUTOR_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
            monkeypatch.delenv(v, raising=False)
        assert cfg.resolved_api_key() == ""

    def test_mineru_key_from_config(self, tmp_path):
        cfg = _build_config({"ingest": {"mineru_api_key": "mu-key"}}, tmp_path)
        assert cfg.resolved_mineru_api_key() == "mu-key"
        assert cfg.resolved_mineru_api_keys() == ["mu-key"]

    def test_mineru_keys_from_config_list(self, tmp_path):
        cfg = _build_config({"ingest": {"mineru_api_keys": ["mu-key-1", "mu-key-2"]}}, tmp_path)
        assert cfg.resolved_mineru_api_key() == "mu-key-1"
        assert cfg.resolved_mineru_api_keys() == ["mu-key-1", "mu-key-2"]

    def test_mineru_key_from_env(self, tmp_path, monkeypatch):
        cfg = _build_config({}, tmp_path)
        monkeypatch.setenv("MINERU_API_KEYS", "mu-env-1,mu-env-2")
        assert cfg.resolved_mineru_api_key() == "mu-env-1"
        assert cfg.resolved_mineru_api_keys() == ["mu-env-1", "mu-env-2"]

    def test_mineru_env_keys_win_over_config(self, tmp_path, monkeypatch):
        cfg = _build_config({"ingest": {"mineru_api_keys": ["mu-cfg"]}}, tmp_path)
        monkeypatch.setenv("MINERU_API_KEYS", "mu-env")
        assert cfg.resolved_mineru_api_keys() == ["mu-env"]

    def test_s2_key_from_config(self, tmp_path):
        cfg = _build_config({"ingest": {"s2_api_key": "s2-cfg"}}, tmp_path)
        assert cfg.resolved_s2_api_key() == "s2-cfg"

    def test_s2_key_from_env(self, tmp_path, monkeypatch):
        cfg = _build_config({}, tmp_path)
        monkeypatch.setenv("S2_API_KEY", "s2-env")
        assert cfg.resolved_s2_api_key() == "s2-env"

    def test_s2_key_config_wins_over_env(self, tmp_path, monkeypatch):
        cfg = _build_config({"ingest": {"s2_api_key": "s2-cfg"}}, tmp_path)
        monkeypatch.setenv("S2_API_KEY", "s2-env")
        assert cfg.resolved_s2_api_key() == "s2-cfg"

    def test_s2_key_empty_when_unset(self, tmp_path, monkeypatch):
        cfg = _build_config({}, tmp_path)
        monkeypatch.delenv("S2_API_KEY", raising=False)
        assert cfg.resolved_s2_api_key() == ""

    def test_ncbi_key_from_config(self, tmp_path):
        cfg = _build_config({"ingest": {"ncbi_api_key": "ncbi-cfg"}}, tmp_path)
        assert cfg.resolved_ncbi_api_key() == "ncbi-cfg"

    def test_ncbi_key_from_env(self, tmp_path, monkeypatch):
        cfg = _build_config({}, tmp_path)
        monkeypatch.setenv("NCBI_API_KEY", "ncbi-env")
        assert cfg.resolved_ncbi_api_key() == "ncbi-env"

    def test_ncbi_key_config_wins_over_env(self, tmp_path, monkeypatch):
        cfg = _build_config({"ingest": {"ncbi_api_key": "ncbi-cfg"}}, tmp_path)
        monkeypatch.setenv("NCBI_API_KEY", "ncbi-env")
        assert cfg.resolved_ncbi_api_key() == "ncbi-cfg"

    def test_plot_key_from_config(self, tmp_path):
        cfg = _build_config({"plot": {"api_key": "plot-cfg"}}, tmp_path)
        assert cfg.resolved_plot_api_key() == "plot-cfg"

    def test_plot_key_from_env(self, tmp_path, monkeypatch):
        cfg = _build_config({}, tmp_path)
        monkeypatch.setenv("AUTOR_PLOT_API_KEY", "plot-env")
        assert cfg.resolved_plot_api_key() == "plot-env"

    def test_plot_key_config_wins_over_env(self, tmp_path, monkeypatch):
        cfg = _build_config({"plot": {"api_key": "plot-cfg"}}, tmp_path)
        monkeypatch.setenv("AUTOR_PLOT_API_KEY", "plot-env")
        assert cfg.resolved_plot_api_key() == "plot-cfg"


class TestLoadConfig:
    def test_load_from_explicit_path(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("llm:\n  model: test-model\n", encoding="utf-8")
        cfg = load_config(cfg_file)
        assert cfg.llm.model == "test-model"

    def test_local_yaml_overrides(self, tmp_path):
        (tmp_path / "config.yaml").write_text(
            "llm:\n  model: base-model\n  timeout: 30\n",
            encoding="utf-8",
        )
        (tmp_path / "config.local.yaml").write_text(
            "llm:\n  model: local-model\n",
            encoding="utf-8",
        )
        cfg = load_config(tmp_path / "config.yaml")
        assert cfg.llm.model == "local-model"
        assert cfg.llm.timeout == 30  # preserved from base

    def test_mineru_tokens_from_config_yaml_are_ignored(self, tmp_path):
        (tmp_path / "config.yaml").write_text(
            "ingest:\n  mineru_api_keys:\n    - tracked-secret\n  mineru_api_key: tracked-single\n",
            encoding="utf-8",
        )
        cfg = load_config(tmp_path / "config.yaml")
        assert cfg.resolved_mineru_api_keys() == []

    def test_mineru_tokens_from_local_yaml_are_used(self, tmp_path):
        (tmp_path / "config.yaml").write_text(
            "ingest:\n  mineru_api_keys: []\n",
            encoding="utf-8",
        )
        (tmp_path / "config.local.yaml").write_text(
            "ingest:\n  mineru_api_keys:\n    - local-one\n    - local-two\n",
            encoding="utf-8",
        )
        cfg = load_config(tmp_path / "config.yaml")
        assert cfg.resolved_mineru_api_keys() == ["local-one", "local-two"]

    def test_nonexistent_path_uses_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.llm.model == "deepseek-chat"

    def test_empty_yaml(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("", encoding="utf-8")
        cfg = load_config(cfg_file)
        assert cfg.llm.model == "deepseek-chat"

    def test_env_var_config_path(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "custom.yaml"
        cfg_file.write_text("search:\n  top_k: 42\n", encoding="utf-8")
        monkeypatch.setenv("AUTOR_CONFIG", str(cfg_file))
        cfg = load_config()
        assert cfg.search.top_k == 42
