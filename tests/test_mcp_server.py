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

    def test_identify_coverage_reports_missing_and_workspace_status(self, tmp_path, tmp_papers):
        cfg = _build_config({"paths": {"papers_dir": "papers", "index_db": "index.db"}}, tmp_path)
        cfg.ensure_dirs()
        build_index(tmp_papers, cfg.index_db)
        ws_dir = tmp_path / "workspace" / "coverage-ws"
        create(ws_dir)
        add(ws_dir, [], cfg.index_db, resolved=[{"id": "aaaa-1111", "dir_name": "Smith-2023-Turbulence"}])

        old_cfg = mcp_server._cfg
        try:
            mcp_server._cfg = cfg
            payload = json.loads(
                mcp_server.identify_coverage(
                    pmids=["PMID:12345678", "99999999"],
                    workspace="coverage-ws",
                )
            )
        finally:
            mcp_server._cfg = old_cfg

        assert payload["found_count"] == 1
        assert payload["missing"] == ["99999999"]
        assert payload["records"][0]["in_workspace"] is True


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


class TestWorkspaceTools:
    def test_workspace_status_export_screen_and_plan_package(self, tmp_path, tmp_papers):
        cfg = _build_config({"paths": {"papers_dir": "papers", "index_db": "index.db"}}, tmp_path)
        cfg.ensure_dirs()
        build_index(tmp_papers, cfg.index_db)
        ws_dir = tmp_path / "workspace" / "evidence-ws"
        create(ws_dir)
        add(
            ws_dir,
            [],
            cfg.index_db,
            resolved=[
                {"id": "aaaa-1111", "dir_name": "Smith-2023-Turbulence"},
                {"id": "bbbb-2222", "dir_name": "Wang-2024-DeepLearning"},
            ],
        )

        old_cfg = mcp_server._cfg
        try:
            mcp_server._cfg = cfg
            status_payload = json.loads(mcp_server.workspace_status("evidence-ws", include_papers=True))
            evidence_payload = json.loads(mcp_server.workspace_export_evidence("evidence-ws"))
            screen_payload = json.loads(
                mcp_server.workspace_screen("evidence-ws", "turbulence boundary layers", target_count=1)
            )
            plan_payload = json.loads(
                mcp_server.workspace_generate_planning_package(
                    "evidence-ws",
                    title="Boundary-layer turbulence review",
                    criteria="turbulence boundary layers",
                )
            )
            refmap = json.loads((ws_dir / "reference-map.json").read_text(encoding="utf-8"))
            (ws_dir / "final.md").write_text(f"Evidence [@{refmap['references'][0]['citekey']}].", encoding="utf-8")
            coverage_payload = json.loads(mcp_server.workspace_citation_coverage("evidence-ws"))
            figure_payload = json.loads(mcp_server.workspace_figure_status("evidence-ws"))
        finally:
            mcp_server._cfg = old_cfg

        assert status_payload["count"] == 2
        assert status_payload["papers"][0]["id"] == "aaaa-1111"
        assert evidence_payload[0]["id"] == "aaaa-1111"
        assert screen_payload["retained_count"] == 1
        assert plan_payload["count"] == 2
        assert coverage_payload["reference_count"] == 2
        assert coverage_payload["missing_required_count"] == 1
        assert figure_payload["planned_count"] == 1
        assert figure_payload["missing_count"] == 1
        assert (ws_dir / "reference-map.json").exists()

    def test_workspace_enrich_l3_is_scoped_to_workspace(self, tmp_path, tmp_papers, monkeypatch):
        cfg = _build_config({"paths": {"papers_dir": "papers", "index_db": "index.db"}}, tmp_path)
        cfg.ensure_dirs()
        build_index(tmp_papers, cfg.index_db)
        ws_dir = tmp_path / "workspace" / "l3-ws"
        create(ws_dir)
        add(ws_dir, [], cfg.index_db, resolved=[{"id": "aaaa-1111", "dir_name": "Smith-2023-Turbulence"}])

        calls: list[str] = []

        def fake_enrich_l3(json_path, _md_path, _cfg, **_kwargs):
            calls.append(json_path.parent.name)
            meta = json.loads(json_path.read_text(encoding="utf-8"))
            meta["l3"] = {"takeaway": "Scoped L3"}
            json_path.write_text(json.dumps(meta), encoding="utf-8")
            return True

        monkeypatch.setattr("autor.loader.enrich_l3", fake_enrich_l3)

        old_cfg = mcp_server._cfg
        try:
            mcp_server._cfg = cfg
            payload = json.loads(mcp_server.workspace_enrich_l3("l3-ws"))
        finally:
            mcp_server._cfg = old_cfg

        assert calls == ["Smith-2023-Turbulence"]
        assert payload["ok"] == 1
        assert payload["skipped"] == 0

    def test_workspace_dedup_removes_dup_entries(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        cfg.ensure_dirs()
        ws_dir = tmp_path / "workspace" / "dedup-ws"
        create(ws_dir)
        (ws_dir / "papers.json").write_text(
            json.dumps(
                [
                    {"id": "aaaa-1111", "dir_name": "Smith-2023-Test"},
                    {"id": "aaaa-1111", "dir_name": "Smith-2023-Test"},
                    {"id": "dup-1111", "dir_name": "DUP-12345678"},
                ]
            ),
            encoding="utf-8",
        )

        old_cfg = mcp_server._cfg
        try:
            mcp_server._cfg = cfg
            payload = json.loads(mcp_server.workspace_dedup("dedup-ws"))
        finally:
            mcp_server._cfg = old_cfg

        assert payload["kept_count"] == 1
        assert payload["removed_count"] == 2

    def test_export_bibtex_supports_workspace(self, tmp_path, tmp_papers):
        cfg = _build_config({"paths": {"papers_dir": "papers", "index_db": "index.db"}}, tmp_path)
        cfg.ensure_dirs()
        build_index(tmp_papers, cfg.index_db)
        ws_dir = tmp_path / "workspace" / "bib-ws"
        create(ws_dir)
        add(ws_dir, [], cfg.index_db, resolved=[{"id": "aaaa-1111", "dir_name": "Smith-2023-Turbulence"}])

        old_cfg = mcp_server._cfg
        try:
            mcp_server._cfg = cfg
            payload = json.loads(mcp_server.export_bibtex(workspace="bib-ws"))
        finally:
            mcp_server._cfg = old_cfg

        assert payload["count"] == 1
        assert "Smith2023" in payload["bibtex"]
