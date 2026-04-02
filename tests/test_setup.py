"""Tests for setup.py dependency probing and check formatting."""

from __future__ import annotations

import importlib

from autor.setup import check_dep_group


def test_check_dep_group_treats_runtime_import_failure_as_missing(monkeypatch):
    original = importlib.import_module

    def fake_import(name: str, package=None):
        if name == "bertopic":
            raise RuntimeError("numba cache failure")
        if package is None:
            return original(name)
        return original(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    status = check_dep_group("topics")

    assert not status.installed
    assert "bertopic" in status.missing
