"""Tests for explore filter construction and name validation."""

from __future__ import annotations

import pytest

from autor.explore import _build_filter, fetch_explore


class TestBuildFilter:
    def test_min_citations_positive_adds_filter(self):
        filt, _ = _build_filter(min_citations=10)
        assert "cited_by_count:>9" in filt

    def test_min_citations_zero_or_negative_ignored(self):
        filt_zero, _ = _build_filter(min_citations=0)
        filt_negative, _ = _build_filter(min_citations=-3)
        assert "cited_by_count" not in filt_zero
        assert "cited_by_count" not in filt_negative


class TestFetchExploreLimit:
    def test_limit_must_be_positive(self):
        with pytest.raises(ValueError, match="limit 必须为正整数"):
            fetch_explore("tmp-limit-check", issn="0022-1120", limit=0)

        with pytest.raises(ValueError, match="limit 必须为正整数"):
            fetch_explore("tmp-limit-check", issn="0022-1120", limit=-1)
