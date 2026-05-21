"""Tests for pipeline workspace auto-assignment."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from autor import cli
from autor.config import _build_config
from autor.index import build_index
from autor.ingest import pipeline
from autor.workspace import add, create


def _write_markdown(
    path: Path,
    *,
    title: str,
    authors: str,
    doi: str = "",
    year: int = 2026,
    journal: str = "Journal of Test Cases",
    abstract: str = "Test abstract.",
) -> None:
    lines = [
        f"# {title}",
        "",
        authors,
        "",
    ]
    if doi:
        lines.extend([f"DOI: {doi}", ""])
    lines.extend(
        [
            f"Copyright © {year}",
            "",
            journal,
            "",
            "## Abstract",
            "",
            abstract,
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


class TestCmdPipelineWorkspace:
    def test_default_presets_use_index_only_for_retrieval(self):
        assert pipeline.PRESETS["ingest"] == ["mineru", "extract", "dedup", "ingest", "l3", "index"]
        assert pipeline.PRESETS["full"] == ["mineru", "extract", "dedup", "ingest", "toc", "l3", "index"]
        assert pipeline.PRESETS["enrich"] == ["toc", "l3", "index"]
        assert pipeline.PRESETS["reindex"] == ["index"]

    def test_forwards_workspace_to_run_pipeline(self, monkeypatch):
        captured: dict[str, object] = {}

        def fake_run_pipeline(step_names, cfg, opts, workspace=None):
            captured["step_names"] = step_names
            captured["cfg"] = cfg
            captured["opts"] = opts
            captured["workspace"] = workspace

        monkeypatch.setattr(pipeline, "run_pipeline", fake_run_pipeline)

        cfg = SimpleNamespace()
        args = Namespace(
            list_steps=False,
            preset="ingest",
            steps=None,
            dry_run=False,
            no_api=False,
            force=False,
            inspect=False,
            max_retries=2,
            rebuild=False,
            inbox=None,
            papers=None,
            workspace="demo-workspace",
        )

        cli.cmd_pipeline(args, cfg)

        assert captured["step_names"] == pipeline.PRESETS["ingest"]
        assert captured["workspace"] == "demo-workspace"

    def test_rejects_invalid_workspace_name(self, monkeypatch):
        messages: list[str] = []

        def fail_run_pipeline(*_args, **_kwargs):
            raise AssertionError("run_pipeline should not be called for invalid workspace names")

        monkeypatch.setattr(cli, "ui", messages.append)
        monkeypatch.setattr(pipeline, "run_pipeline", fail_run_pipeline)

        args = Namespace(
            list_steps=False,
            preset="ingest",
            steps=None,
            dry_run=False,
            no_api=False,
            force=False,
            inspect=False,
            max_retries=2,
            rebuild=False,
            inbox=None,
            papers=None,
            workspace="../escape",
        )

        cli.cmd_pipeline(args, SimpleNamespace())

        assert messages == ["非法工作区名称: ../escape"]


class TestRunPipelineWorkspace:
    def test_non_inbox_steps_are_scoped_to_workspace(self, tmp_path, tmp_papers, monkeypatch):
        cfg = _build_config({"paths": {"papers_dir": "papers", "index_db": "index.db"}}, tmp_path)
        cfg.ensure_dirs()
        build_index(tmp_papers, cfg.index_db)

        ws_dir = tmp_path / "workspace" / "scope-ws"
        create(ws_dir)
        add(ws_dir, [], cfg.index_db, resolved=[{"id": "aaaa-1111", "dir_name": "Smith-2023-Turbulence"}])

        l3_calls: list[str] = []
        index_paper_ids: list[set[str]] = []

        def fake_l3(json_path, _cfg, _opts):
            l3_calls.append(Path(json_path).parent.name)
            return pipeline.StepResult.OK

        def fake_index(_papers_dir, _cfg, opts):
            index_paper_ids.append(set(opts.get("paper_ids") or []))
            return pipeline.StepResult.OK

        monkeypatch.setitem(
            pipeline.STEPS,
            "l3",
            pipeline.StepDef(fn=fake_l3, scope="papers", desc="fake l3"),
        )
        monkeypatch.setitem(
            pipeline.STEPS,
            "index",
            pipeline.StepDef(fn=fake_index, scope="global", desc="fake index"),
        )

        pipeline.run_pipeline(
            ["l3", "index"],
            cfg,
            {
                "dry_run": False,
                "force": False,
                "inspect": False,
                "max_retries": 2,
                "rebuild": False,
            },
            workspace="scope-ws",
        )

        assert l3_calls == ["Smith-2023-Turbulence"]
        assert index_paper_ids == [{"aaaa-1111"}]

    def test_only_persisted_ingests_are_added_to_workspace(self, tmp_path, monkeypatch):
        cfg = _build_config({"ingest": {"extractor": "regex"}}, tmp_path)
        cfg.ensure_dirs()

        inbox_dir = tmp_path / "data" / "inbox"
        _write_markdown(
            inbox_dir / "good.md",
            title="A Good Paper",
            authors="Alice Smith, Bob Doe",
            doi="10.1234/good.paper",
        )
        _write_markdown(
            inbox_dir / "duplicate.md",
            title="A Duplicate Paper",
            authors="Alice Smith, Bob Doe",
            doi="10.1234/good.paper",
        )
        _write_markdown(
            inbox_dir / "missing-doi.md",
            title="A Paper Without DOI",
            authors="Chris Roe",
        )

        monkeypatch.setitem(
            pipeline.STEPS,
            "toc",
            pipeline.StepDef(
                fn=lambda _json_path, _cfg, _opts: pipeline.StepResult.FAIL,
                scope="papers",
                desc="forced toc failure",
            ),
        )

        pipeline.run_pipeline(
            ["extract", "dedup", "ingest", "toc"],
            cfg,
            {
                "dry_run": False,
                "no_api": True,
                "force": False,
                "inspect": False,
                "max_retries": 2,
                "rebuild": False,
            },
            workspace="demo-workspace",
        )

        paper_dirs = sorted((tmp_path / "data" / "papers").iterdir())
        assert len(paper_dirs) == 1

        meta = json.loads((paper_dirs[0] / "meta.json").read_text(encoding="utf-8"))
        workspace_entries = json.loads(
            (tmp_path / "workspace" / "demo-workspace" / "papers.json").read_text(encoding="utf-8")
        )
        assert workspace_entries == [
            {
                "id": meta["id"],
                "dir_name": paper_dirs[0].name,
                "added_at": workspace_entries[0]["added_at"],
            }
        ]

        pending_dirs = {d.name for d in (tmp_path / "data" / "pending").iterdir() if d.is_dir()}
        assert "missing-doi" in pending_dirs
        assert len(pending_dirs) == 2
        assert pending_dirs & {"duplicate", "good"}

    def test_regular_ingest_persists_pmid_metadata(self, tmp_path, monkeypatch):
        cfg = _build_config({"ingest": {"extractor": "regex"}}, tmp_path)
        cfg.ensure_dirs()

        inbox_dir = tmp_path / "data" / "inbox"
        _write_markdown(
            inbox_dir / "pmid-paper.md",
            title="PMID persistence paper",
            authors="Alice Smith, Bob Doe",
            doi="10.1234/pmid.paper",
        )

        def fake_enrich(meta):
            meta.pmid = "34567890"
            meta.abstract = meta.abstract or "API abstract with PMID."
            return meta

        monkeypatch.setattr("autor.ingest.metadata.enrich_metadata", fake_enrich)

        pipeline.run_pipeline(
            ["extract", "dedup", "ingest"],
            cfg,
            {
                "dry_run": False,
                "no_api": False,
                "force": False,
                "inspect": False,
                "max_retries": 2,
                "rebuild": False,
            },
        )

        paper_dirs = sorted((tmp_path / "data" / "papers").iterdir())
        assert len(paper_dirs) == 1

        meta = json.loads((paper_dirs[0] / "meta.json").read_text(encoding="utf-8"))
        assert meta["pmid"] == "34567890"
        assert meta["ids"]["pmid"] == "34567890"

    def test_queue_mode_batches_index_for_ingested_samples(self, tmp_path, monkeypatch):
        cfg = _build_config({"ingest": {"extractor": "regex"}}, tmp_path)
        cfg.ensure_dirs()

        inbox_dir = tmp_path / "data" / "inbox"
        _write_markdown(
            inbox_dir / "queue-paper-a.md",
            title="Queue Mode Paper A",
            authors="Alice Smith",
            doi="10.1234/queue.paper.a",
        )
        _write_markdown(
            inbox_dir / "queue-paper-b.md",
            title="Queue Mode Paper B",
            authors="Bob Smith",
            doi="10.1234/queue.paper.b",
        )

        calls: list[tuple[str, set[str] | None]] = []

        def fake_index(_papers_dir, _cfg, opts):
            calls.append(("index", opts.get("paper_ids")))
            return pipeline.StepResult.OK

        monkeypatch.setitem(pipeline.STEPS, "index", pipeline.StepDef(fn=fake_index, scope="global", desc="fake index"))

        pipeline.run_pipeline(
            ["extract", "dedup", "ingest", "index"],
            cfg,
            {
                "dry_run": False,
                "no_api": True,
                "force": False,
                "inspect": False,
                "max_retries": 2,
                "rebuild": False,
            },
        )

        assert len(calls) == 1
        assert calls[0][0] == "index"
        assert all(isinstance(paper_ids, set) and len(paper_ids) == 2 for _, paper_ids in calls)
