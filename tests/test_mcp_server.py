"""Tests for MCP helpers exposed by ``autor.mcp_server``."""

from __future__ import annotations

import json

from autor import mcp_server
from autor.config import _build_config
from autor.index import build_index
from autor.workspace import add, create


class TestIdentifyTool:
    def test_identify_reports_library_and_workspace_matches(self, tmp_path, tmp_papers):
        cfg = _build_config({"paths": {"papers_dir": "papers", "index_db": "index.db"}}, tmp_path)
        cfg.ensure_dirs()
        build_index(tmp_papers, cfg.index_db)

        ws_dir = tmp_path / "workspace" / "car-t-sequential"
        create(ws_dir)
        add(ws_dir, [], cfg.index_db, resolved=[{"id": "aaaa-1111", "dir_name": "Smith-2023-Turbulence"}])

        old_cfg = mcp_server._cfg
        try:
            mcp_server._cfg = cfg
            payload = json.loads(
                mcp_server.identify(
                    doi="10.1234/jfm.2023.001",
                    pmid="12345678",
                    title="Turbulence modeling in boundary layers",
                    workspace="car-t-sequential",
                )
            )
        finally:
            mcp_server._cfg = old_cfg

        assert payload["library"]["found"] is True
        assert payload["library"]["records"][0]["id"] == "aaaa-1111"
        assert payload["workspace"]["exists"] is True
        assert payload["workspace"]["records"][0]["id"] == "aaaa-1111"

    def test_identify_reports_missing_index(self, tmp_path):
        cfg = _build_config({"paths": {"papers_dir": "papers", "index_db": "index.db"}}, tmp_path)
        cfg.ensure_dirs()

        old_cfg = mcp_server._cfg
        try:
            mcp_server._cfg = cfg
            payload = json.loads(mcp_server.identify(doi="10.1234/missing.index"))
        finally:
            mcp_server._cfg = old_cfg

        assert payload["error"] == "index_not_found"


class TestPlotTool:
    def test_plot_returns_saved_files(self, tmp_path, monkeypatch):
        from autor import plot as plot_mod

        cfg = _build_config({}, tmp_path)
        cfg.ensure_dirs()

        monkeypatch.setattr(
            plot_mod,
            "generate_plot",
            lambda prompt, **kwargs: {
                "id": "job-1",
                "status": "succeeded",
                "files": [str(tmp_path / "workspace" / "car-glioma" / "figure" / "overview.png")],
                "meta_file": str(tmp_path / "workspace" / "car-glioma" / "figure" / "overview.json"),
            },
        )

        old_cfg = mcp_server._cfg
        try:
            mcp_server._cfg = cfg
            payload = json.loads(
                mcp_server.plot(
                    prompt="English biomedical overview",
                    workspace="car-glioma",
                    name="overview",
                )
            )
        finally:
            mcp_server._cfg = old_cfg

        assert payload["id"] == "job-1"
        assert payload["files"][0].endswith("overview.png")
