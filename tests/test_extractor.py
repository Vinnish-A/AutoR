"""Tests for autor.ingest.extractor — factory and RegexExtractor."""

from __future__ import annotations

from autor.config import _build_config
from autor.ingest.extractor import RegexExtractor, _clean_llm_str, get_extractor


class TestCleanLLMStr:
    def test_none(self):
        assert _clean_llm_str(None) == ""

    def test_null_string(self):
        assert _clean_llm_str("null") == ""

    def test_none_string(self):
        assert _clean_llm_str("None") == ""

    def test_na_string(self):
        assert _clean_llm_str("N/A") == ""

    def test_empty_string(self):
        assert _clean_llm_str("") == ""

    def test_normal_string(self):
        assert _clean_llm_str("hello") == "hello"

    def test_whitespace_stripped(self):
        assert _clean_llm_str("  hello  ") == "hello"

    def test_integer_input(self):
        assert _clean_llm_str(42) == "42"


class TestRegexExtractor:
    def test_extract_returns_metadata(self, tmp_path):
        md = tmp_path / "paper.md"
        md.write_text(
            "# Test Paper Title\n\nJohn Smith\n\nDOI: 10.1234/test.2023\n\nCopyright © 2023\n",
            encoding="utf-8",
        )
        ext = RegexExtractor()
        meta = ext.extract(md)
        assert meta.title == "Test Paper Title"
        assert meta.doi == "10.1234/test.2023"


class TestGetExtractor:
    def test_regex_mode(self, tmp_path):
        cfg = _build_config({"ingest": {"extractor": "regex"}}, tmp_path)
        ext = get_extractor(cfg)
        assert isinstance(ext, RegexExtractor)

    def test_regex_mode_no_api_key_needed(self, tmp_path):
        cfg = _build_config(
            {"ingest": {"extractor": "regex"}, "llm": {"api_key": ""}},
            tmp_path,
        )
        ext = get_extractor(cfg)
        assert isinstance(ext, RegexExtractor)
