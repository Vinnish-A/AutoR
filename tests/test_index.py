"""Contract tests for the FTS5 search index.

Verifies: build_index creates a searchable database, search returns
matching results with expected structure.
Does NOT test: SQLite internals, exact ranking scores, hash logic.
"""

from __future__ import annotations

import json
import sqlite3

from autor.index import (
    build_index,
    build_index_atomic,
    find_exact_matches,
    index_status,
    lookup_paper,
    research_bundle,
    search,
    search_nodes,
)


class TestBuildAndSearch:
    """End-to-end index contract: build → search → results."""

    def test_build_then_search_by_title(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        results = search("turbulence", tmp_db)
        assert len(results) >= 1
        titles = [r["title"] for r in results]
        assert any("Turbulence" in t or "turbulence" in t for t in titles)

    def test_search_returns_expected_fields(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        results = search("turbulence", tmp_db)
        assert len(results) >= 1
        r = results[0]
        # Contract: search results contain at minimum these keys
        for key in ("paper_id", "title", "authors", "year", "journal"):
            assert key in r, f"Missing key: {key}"

    def test_search_no_match_returns_empty(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        results = search("xyznonexistent", tmp_db)
        assert results == []

    def test_search_by_abstract_content(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        results = search("novel turbulence model boundary", tmp_db)
        assert len(results) >= 1

    def test_rebuild_is_idempotent(self, tmp_papers, tmp_db):
        """Building twice should not duplicate entries."""
        build_index(tmp_papers, tmp_db)
        build_index(tmp_papers, tmp_db)
        results = search("turbulence", tmp_db)
        # Should still find exactly one match for this query, not duplicates
        turbulence_results = [r for r in results if "Turbulence" in r.get("title", "")]
        assert len(turbulence_results) == 1

    def test_atomic_rebuild_uses_final_index_path(self, tmp_papers, tmp_db, tmp_path):
        count = build_index_atomic(tmp_papers, tmp_db, rebuild=True, temp_dir=tmp_path / "tmp-index")

        status = index_status(tmp_db)

        assert count == 2
        assert status["exists"] is True
        assert status["ok"] is True
        assert status["tables"]["papers_registry"] == 2

    def test_build_index_accepts_reference_dicts(self, tmp_path, tmp_db):
        papers_dir = tmp_path / "papers"
        paper_dir = papers_dir / "Smith-2023-Turbulence"
        paper_dir.mkdir(parents=True)
        (paper_dir / "meta.json").write_text(
            json.dumps(
                {
                    "id": "aaaa-1111",
                    "title": "Turbulence modeling in boundary layers",
                    "authors": ["Smith, John"],
                    "first_author_lastname": "Smith",
                    "year": 2023,
                    "journal": "Journal of Fluid Mechanics",
                    "doi": "10.1234/jfm.2023.001",
                    "abstract": "We propose a novel turbulence model for boundary layers.",
                    "paper_type": "journal-article",
                    "references": [
                        {"doi": "10.1000/classic"},
                        {"externalIds": {"DOI": "10.1000/second"}},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (paper_dir / "paper.md").write_text("# Turbulence\n\nFull text.", encoding="utf-8")

        build_index(papers_dir, tmp_db)

        with sqlite3.connect(tmp_db) as conn:
            rows = conn.execute(
                "SELECT target_doi FROM citations WHERE source_id = ? ORDER BY target_doi",
                ("aaaa-1111",),
            ).fetchall()
        assert [row[0] for row in rows] == ["10.1000/classic", "10.1000/second"]

    def test_build_index_can_limit_updates_to_target_paper_ids(self, tmp_papers, tmp_db):
        count = build_index(tmp_papers, tmp_db, paper_ids={"aaaa-1111"})

        with sqlite3.connect(tmp_db) as conn:
            rows = conn.execute("SELECT paper_id FROM papers ORDER BY paper_id").fetchall()

        assert count == 1
        assert rows == [("aaaa-1111",)]

    def test_build_index_creates_node_evidence_index(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)

        with sqlite3.connect(tmp_db) as conn:
            node_count = conn.execute("SELECT COUNT(*) FROM paper_nodes").fetchone()[0]
            fts_count = conn.execute("SELECT COUNT(*) FROM paper_node_fts").fetchone()[0]

        assert node_count >= 2
        assert fts_count == node_count

    def test_search_nodes_returns_snippet_and_ref_path(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)

        results = search_nodes("boundary layers", tmp_db, top_k=3)

        assert results
        assert {"node_id", "paper_id", "snippet", "ref_path"}.issubset(results[0])

    def test_research_bundle_writes_round_artifacts(self, tmp_papers, tmp_db, tmp_path):
        build_index(tmp_papers, tmp_db)

        result = research_bundle("boundary layers", tmp_db, run_dir=tmp_path / "run", top_k=2)

        assert result["verify"]["has_evidence"] is True
        assert (tmp_path / "run" / "bundle.round01.md").exists()
        assert (tmp_path / "run" / "trace.round01.json").exists()
        assert (tmp_path / "run" / "verify.round01.json").exists()


class TestLookupPaper:
    """lookup_paper contract: find by UUID, dir_name, DOI, PMID, or publication_number."""

    def test_lookup_by_uuid(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        result = lookup_paper(tmp_db, "aaaa-1111")
        assert result is not None
        assert result["id"] == "aaaa-1111"

    def test_lookup_by_doi(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        result = lookup_paper(tmp_db, "10.1234/jfm.2023.001")
        assert result is not None
        assert result["doi"] == "10.1234/jfm.2023.001"

    def test_lookup_by_doi_prefix(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        result = lookup_paper(tmp_db, "DOI:10.1234/JFM.2023.001")
        assert result is not None
        assert result["id"] == "aaaa-1111"

    def test_lookup_by_pmid(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        result = lookup_paper(tmp_db, "12345678")
        assert result is not None
        assert result["pmid"] == "12345678"

    def test_lookup_pmid_prefixed_input_matches_pmid_dir_prefix(self, tmp_path, tmp_db):
        papers_dir = tmp_path / "papers"
        paper_dir = papers_dir / "PMID-32467386-Cell"
        paper_dir.mkdir(parents=True)
        (paper_dir / "meta.json").write_text(
            json.dumps(
                {
                    "id": "pmid-dir-001",
                    "title": "A paper with weak metadata",
                    "authors": ["Author"],
                    "year": 2020,
                    "journal": "Cell",
                    "doi": "",
                    "pmid": "",
                    "abstract": "Abstract.",
                    "paper_type": "journal-article",
                }
            ),
            encoding="utf-8",
        )
        (paper_dir / "paper.md").write_text("# A paper with weak metadata\n\nContent.", encoding="utf-8")
        build_index(papers_dir, tmp_db)

        result = lookup_paper(tmp_db, "PMID:32467386")

        assert result is not None
        assert result["dir_name"] == "PMID-32467386-Cell"

    def test_lookup_by_publication_number(self, tmp_path, tmp_db):
        """Patent lookup normalizes to uppercase for matching."""
        papers_dir = tmp_path / "papers"
        pa = papers_dir / "Inventor-2023-Patent"
        pa.mkdir(parents=True)
        (pa / "meta.json").write_text(
            json.dumps(
                {
                    "id": "patent-001",
                    "title": "A patent invention",
                    "authors": ["Inventor"],
                    "first_author_lastname": "Inventor",
                    "year": 2023,
                    "journal": "",
                    "doi": "",
                    "abstract": "Patent abstract.",
                    "paper_type": "patent",
                    "ids": {"patent_publication_number": "CN112345678A"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (pa / "paper.md").write_text("# Patent\n\nContent.", encoding="utf-8")
        build_index(papers_dir, tmp_db)
        # Lookup with lowercase should still match (normalization)
        result = lookup_paper(tmp_db, "cn112345678a")
        assert result is not None
        assert result["id"] == "patent-001"

    def test_lookup_numeric_identifier_prefers_pmid_over_publication_number(self, tmp_path, tmp_db):
        """Numeric patent publication numbers must remain resolvable when PMID collides."""
        papers_dir = tmp_path / "papers"

        paper_dir = papers_dir / "Smith-2023-PMID"
        paper_dir.mkdir(parents=True)
        (paper_dir / "meta.json").write_text(
            json.dumps(
                {
                    "id": "paper-001",
                    "title": "A PubMed indexed paper",
                    "authors": ["John Smith"],
                    "first_author_lastname": "Smith",
                    "year": 2023,
                    "journal": "Journal of Test Cases",
                    "doi": "10.1234/test.paper",
                    "pmid": "12345678",
                    "abstract": "Paper abstract.",
                    "paper_type": "journal-article",
                    "ids": {"pmid": "12345678"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (paper_dir / "paper.md").write_text("# Paper\n\nContent.", encoding="utf-8")

        patent_dir = papers_dir / "Inventor-2024-Patent"
        patent_dir.mkdir(parents=True)
        (patent_dir / "meta.json").write_text(
            json.dumps(
                {
                    "id": "patent-001",
                    "title": "A numeric publication number patent",
                    "authors": ["Inventor"],
                    "first_author_lastname": "Inventor",
                    "year": 2024,
                    "journal": "",
                    "doi": "",
                    "abstract": "Patent abstract.",
                    "paper_type": "patent",
                    "ids": {"patent_publication_number": "12345678"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (patent_dir / "paper.md").write_text("# Patent\n\nContent.", encoding="utf-8")

        build_index(papers_dir, tmp_db)

        patent = lookup_paper(tmp_db, "12345678")
        assert patent is not None
        assert patent["id"] == "paper-001"

        paper = lookup_paper(tmp_db, "PMID:12345678")
        assert paper is not None
        assert paper["id"] == "paper-001"

    def test_lookup_nonexistent_returns_none(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        assert lookup_paper(tmp_db, "nonexistent-id") is None


class TestFindExactMatches:
    def test_exact_matches_group_by_field(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        matches = find_exact_matches(
            tmp_db,
            doi="10.1234/jfm.2023.001",
            pmid="12345678",
            title="Turbulence modeling in boundary layers",
        )
        assert [row["id"] for row in matches["records"]] == ["aaaa-1111"]
        assert [row["id"] for row in matches["doi"]] == ["aaaa-1111"]
        assert [row["id"] for row in matches["pmid"]] == ["aaaa-1111"]
        assert [row["id"] for row in matches["title"]] == ["aaaa-1111"]

    def test_exact_matches_respect_paper_id_scope(self, tmp_papers, tmp_db):
        build_index(tmp_papers, tmp_db)
        matches = find_exact_matches(
            tmp_db,
            doi="10.1234/jfm.2023.001",
            paper_ids={"bbbb-2222"},
        )
        assert matches["records"] == []

    def test_exact_matches_requires_built_index(self, tmp_db):
        try:
            find_exact_matches(tmp_db, doi="10.1234/missing.index")
        except FileNotFoundError as exc:
            assert "Index not built" in str(exc)
        else:
            raise AssertionError("find_exact_matches should fail when index.db is missing")
