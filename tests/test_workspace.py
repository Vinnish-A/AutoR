"""Contract tests for workspace management.

Verifies: create initializes workspace, read_paper_ids returns correct set,
internal consistency of papers.json is maintained.
Does NOT test: add/remove (requires index DB with lookup_paper).
"""

from __future__ import annotations

import json

import pytest

from autor.index import build_index
from autor.workspace import (
    add,
    create,
    dump_metadata,
    export_metadata,
    identify_exact,
    list_workspaces,
    read_paper_ids,
    rename,
    validate_workspace_name,
)


class TestWorkspaceCreate:
    """Workspace creation contract."""

    def test_create_initializes_directory(self, tmp_path):
        ws_dir = tmp_path / "workspace" / "test-ws"
        create(ws_dir)
        assert ws_dir.is_dir()
        assert (ws_dir / "papers.json").exists()

    def test_create_idempotent(self, tmp_path):
        ws_dir = tmp_path / "workspace" / "test-ws"
        create(ws_dir)
        create(ws_dir)
        # Should not corrupt existing papers.json
        data = json.loads((ws_dir / "papers.json").read_text())
        assert data == []


class TestReadPaperIds:
    """read_paper_ids contract: returns set of UUIDs from papers.json."""

    def test_empty_workspace(self, tmp_path):
        ws_dir = tmp_path / "ws"
        create(ws_dir)
        assert read_paper_ids(ws_dir) == set()

    def test_reads_ids_from_papers_json(self, tmp_path):
        ws_dir = tmp_path / "ws"
        create(ws_dir)
        # Write entries directly to simulate add()
        entries = [
            {"id": "aaaa-1111", "dir_name": "Smith-2023-Test", "added_at": "2024-01-01"},
            {"id": "bbbb-2222", "dir_name": "Wang-2024-Test", "added_at": "2024-01-01"},
        ]
        (ws_dir / "papers.json").write_text(json.dumps(entries))

        ids = read_paper_ids(ws_dir)
        assert ids == {"aaaa-1111", "bbbb-2222"}

    def test_nonexistent_workspace_returns_empty(self, tmp_path):
        ids = read_paper_ids(tmp_path / "nonexistent")
        assert ids == set()


class TestAddResolved:
    """add(resolved=...) contract: batch-add pre-resolved papers."""

    def test_adds_and_deduplicates(self, tmp_path):
        ws_dir = tmp_path / "ws"
        create(ws_dir)
        resolved = [
            {"id": "aaaa-1111", "dir_name": "Smith-2023-Test"},
            {"id": "bbbb-2222", "dir_name": "Wang-2024-Test"},
        ]
        added = add(ws_dir, [], tmp_path / "unused.db", resolved=resolved)
        assert len(added) == 2
        assert read_paper_ids(ws_dir) == {"aaaa-1111", "bbbb-2222"}

        # Second call with overlap — only new paper added
        resolved2 = [
            {"id": "bbbb-2222", "dir_name": "Wang-2024-Test"},
            {"id": "cccc-3333", "dir_name": "Li-2025-New"},
        ]
        added2 = add(ws_dir, [], tmp_path / "unused.db", resolved=resolved2)
        assert len(added2) == 1
        assert added2[0]["id"] == "cccc-3333"
        assert read_paper_ids(ws_dir) == {"aaaa-1111", "bbbb-2222", "cccc-3333"}


class TestIdentifyExact:
    def test_identifies_matches_inside_workspace(self, tmp_path, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        ws_dir = tmp_path / "workspace" / "car-t-sequential"
        create(ws_dir)
        add(ws_dir, [], tmp_db, resolved=[{"id": "aaaa-1111", "dir_name": "Smith-2023-Turbulence"}])

        matches = identify_exact(
            ws_dir,
            tmp_db,
            doi="10.1234/jfm.2023.001",
            pmid="12345678",
            title="Turbulence modeling in boundary layers",
        )

        assert [row["id"] for row in matches["records"]] == ["aaaa-1111"]


class TestListWorkspaces:
    """list_workspaces contract: discovers workspace directories."""

    def test_lists_created_workspaces(self, tmp_path):
        ws_root = tmp_path / "workspace"
        create(ws_root / "alpha")
        create(ws_root / "beta")

        names = list_workspaces(ws_root)
        assert set(names) == {"alpha", "beta"}

    def test_ignores_dirs_without_papers_json(self, tmp_path):
        ws_root = tmp_path / "workspace"
        create(ws_root / "real")
        (ws_root / "fake").mkdir(parents=True)

        names = list_workspaces(ws_root)
        assert names == ["real"]


class TestExportMetadata:
    def test_exports_workspace_metadata_from_papers_json(self, tmp_path, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        ws_dir = tmp_path / "workspace" / "meta-ws"
        create(ws_dir)
        add(
            ws_dir,
            [],
            tmp_db,
            resolved=[
                {"id": "aaaa-1111", "dir_name": "Smith-2023-Turbulence"},
                {"id": "bbbb-2222", "dir_name": "Wang-2024-DeepLearning"},
            ],
        )

        rows = export_metadata(ws_dir, tmp_papers, tmp_db)

        assert [row["id"] for row in rows] == ["aaaa-1111", "bbbb-2222"]
        assert rows[0]["doi"] == "10.1234/jfm.2023.001"
        assert rows[0]["pmid"] == "12345678"
        assert rows[1]["doi"] == ""

    def test_dump_metadata_supports_csv(self):
        rows = [
            {
                "id": "aaaa-1111",
                "dir_name": "Smith-2023-Turbulence",
                "title": "Turbulence modeling in boundary layers",
                "authors": ["John Smith", "Jane Doe"],
                "year": 2023,
                "journal": "Journal of Fluid Mechanics",
                "paper_type": "journal-article",
                "doi": "10.1234/jfm.2023.001",
                "pmid": "12345678",
                "publication_number": "",
                "added_at": "2026-01-01T00:00:00+00:00",
            }
        ]

        csv_text = dump_metadata(rows, fmt="csv")

        assert "id,dir_name,title,authors,year,journal,paper_type,doi,pmid,publication_number,added_at" in csv_text
        assert "John Smith; Jane Doe" in csv_text


class TestRenameWorkspace:
    """rename contract: moves workspace and validates source/target."""

    def test_rename_success(self, tmp_path):
        ws_root = tmp_path / "workspace"
        create(ws_root / "old")

        new_dir = rename(ws_root, "old", "new")

        assert new_dir == ws_root / "new"
        assert (ws_root / "new" / "papers.json").exists()
        assert not (ws_root / "old").exists()

    def test_rename_missing_source_raises(self, tmp_path):
        ws_root = tmp_path / "workspace"
        ws_root.mkdir(parents=True, exist_ok=True)

        with pytest.raises(FileNotFoundError, match="工作区不存在"):
            rename(ws_root, "missing", "new")

    def test_rename_target_exists_raises(self, tmp_path):
        ws_root = tmp_path / "workspace"
        create(ws_root / "old")
        create(ws_root / "new")

        with pytest.raises(FileExistsError, match="目标工作区已存在"):
            rename(ws_root, "old", "new")

    def test_rename_source_is_not_directory_raises(self, tmp_path):
        ws_root = tmp_path / "workspace"
        ws_root.mkdir(parents=True, exist_ok=True)
        (ws_root / "old").write_text("not a directory", encoding="utf-8")

        with pytest.raises(ValueError, match="不是有效工作区目录"):
            rename(ws_root, "old", "new")

    def test_rename_source_without_papers_json_raises(self, tmp_path):
        ws_root = tmp_path / "workspace"
        (ws_root / "old").mkdir(parents=True, exist_ok=True)

        with pytest.raises(ValueError, match=r"缺少 papers\.json"):
            rename(ws_root, "old", "new")

    def test_rename_rejects_invalid_old_name(self, tmp_path):
        ws_root = tmp_path / "workspace"
        create(ws_root / "old")

        with pytest.raises(ValueError, match="非法工作区名称"):
            rename(ws_root, "../old", "new")

    def test_rename_rejects_invalid_new_name(self, tmp_path):
        ws_root = tmp_path / "workspace"
        create(ws_root / "old")

        with pytest.raises(ValueError, match="非法工作区名称"):
            rename(ws_root, "old", "../new")


class TestValidateWorkspaceName:
    def test_accepts_regular_name(self):
        assert validate_workspace_name("my-ws_2026")

    def test_rejects_empty_or_path_like_name(self):
        assert not validate_workspace_name("")
        assert not validate_workspace_name("   ")
        assert not validate_workspace_name(".")
        assert not validate_workspace_name("../foo")
        assert not validate_workspace_name("foo/bar")
        assert not validate_workspace_name("foo\\bar")
        assert not validate_workspace_name("C:foo")
        assert not validate_workspace_name(" ws ")
