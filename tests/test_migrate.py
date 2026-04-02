"""Tests for autor.migrate — flat-to-directory migration."""

from __future__ import annotations

import json

from autor.migrate import migrate_to_dirs


class TestMigrateToDirs:
    def test_no_flat_files(self, tmp_path):
        papers = tmp_path / "papers"
        papers.mkdir()
        stats = migrate_to_dirs(papers, dry_run=False)
        assert stats["migrated"] == 0
        assert stats["skipped"] == 0

    def test_nonexistent_dir(self, tmp_path):
        stats = migrate_to_dirs(tmp_path / "nope", dry_run=False)
        assert stats == {"migrated": 0, "skipped": 0, "failed": 0}

    def test_migrate_flat_json(self, tmp_path):
        papers = tmp_path / "papers"
        papers.mkdir()

        # Create flat files
        meta = {"title": "Test Paper", "authors": ["Smith"]}
        (papers / "Smith-2023-Test.json").write_text(json.dumps(meta))
        (papers / "Smith-2023-Test.md").write_text("# Test\n\nContent.")

        stats = migrate_to_dirs(papers, dry_run=False)
        assert stats["migrated"] == 1

        # Verify migration result
        new_dir = papers / "Smith-2023-Test"
        assert new_dir.is_dir()
        assert (new_dir / "meta.json").exists()
        assert (new_dir / "paper.md").exists()
        # Old flat files should be gone
        assert not (papers / "Smith-2023-Test.json").exists()
        assert not (papers / "Smith-2023-Test.md").exists()

    def test_uuid_injected(self, tmp_path):
        papers = tmp_path / "papers"
        papers.mkdir()
        meta = {"title": "Test"}
        (papers / "Test.json").write_text(json.dumps(meta))

        migrate_to_dirs(papers, dry_run=False)

        new_meta = json.loads((papers / "Test" / "meta.json").read_text())
        assert "id" in new_meta
        assert len(new_meta["id"]) > 0

    def test_existing_uuid_preserved(self, tmp_path):
        papers = tmp_path / "papers"
        papers.mkdir()
        meta = {"title": "Test", "id": "keep-this-uuid"}
        (papers / "Test.json").write_text(json.dumps(meta))

        migrate_to_dirs(papers, dry_run=False)

        new_meta = json.loads((papers / "Test" / "meta.json").read_text())
        assert new_meta["id"] == "keep-this-uuid"

    def test_already_migrated_skipped(self, tmp_path):
        papers = tmp_path / "papers"
        papers.mkdir()

        # Create already-migrated structure
        d = papers / "Smith-2023-Test"
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({"title": "Test"}))
        # Also have the old flat json (leftover)
        (papers / "Smith-2023-Test.json").write_text(json.dumps({"title": "Test"}))

        stats = migrate_to_dirs(papers, dry_run=False)
        assert stats["skipped"] == 1

    def test_orphan_md_rescued(self, tmp_path):
        papers = tmp_path / "papers"
        papers.mkdir()

        # Partially migrated: directory exists with meta.json, but .md still flat
        d = papers / "Smith-2023-Test"
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({"title": "Test"}))
        (papers / "Smith-2023-Test.md").write_text("# Content")
        (papers / "Smith-2023-Test.json").write_text(json.dumps({"title": "Test"}))

        migrate_to_dirs(papers, dry_run=False)
        assert (d / "paper.md").exists()
        assert not (papers / "Smith-2023-Test.md").exists()

    def test_dry_run_no_changes(self, tmp_path):
        papers = tmp_path / "papers"
        papers.mkdir()
        (papers / "Test.json").write_text(json.dumps({"title": "Test"}))
        (papers / "Test.md").write_text("content")

        stats = migrate_to_dirs(papers, dry_run=True)
        assert stats["migrated"] == 1
        # But files should still be flat
        assert (papers / "Test.json").exists()
        assert not (papers / "Test").is_dir()

    def test_invalid_json_counted_as_failed(self, tmp_path):
        papers = tmp_path / "papers"
        papers.mkdir()
        (papers / "Bad.json").write_text("not valid json {{{")

        stats = migrate_to_dirs(papers, dry_run=False)
        assert stats["failed"] == 1

    def test_stale_faiss_deleted(self, tmp_path):
        papers = tmp_path / "papers"
        papers.mkdir()
        # Create stale faiss files in data/ (parent of papers/)
        (tmp_path / "faiss.index").write_text("stale")
        (tmp_path / "faiss_ids.json").write_text("stale")

        (papers / "Test.json").write_text(json.dumps({"title": "Test"}))
        migrate_to_dirs(papers, dry_run=False)

        assert not (tmp_path / "faiss.index").exists()
        assert not (tmp_path / "faiss_ids.json").exists()
