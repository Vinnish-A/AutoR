from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import autor.loader as loader
from autor.config import Config

_UNUSED_CONFIG = cast(Config, None)


def _make_article(tmp_path: Path, name: str = "Paper-2026-Test") -> tuple[Path, Path]:
    paper_dir = tmp_path / name
    paper_dir.mkdir(parents=True)
    (paper_dir / "meta.json").write_text(
        json.dumps(
            {
                "id": "paper-1",
                "title": "Test paper",
                "paper_type": "journal-article",
            }
        ),
        encoding="utf-8",
    )
    md_path = paper_dir / "paper.md"
    return paper_dir, md_path


class TestHeaderExtraction:
    def test_extract_headers_detects_plaintext_section_headings(self):
        lines = [
            "Test paper title",
            "",
            "1. Introduction",
            "Intro body.",
            "",
            "4. Conclusions",
            "Conclusion body.",
        ]

        headers = loader._extract_headers(lines)

        assert [(h["line"], h["text"]) for h in headers] == [
            (3, "1. Introduction"),
            (6, "4. Conclusions"),
        ]

    def test_extract_headers_uses_content_list_asset_when_available(self, tmp_path: Path):
        paper_dir, md_path = _make_article(tmp_path, "Asset-2026-Test")
        md_path.write_text(
            "Paper title\n\nExperimental Section\nMethods body.\n\nConclusion\nDone.\n",
            encoding="utf-8",
        )
        (paper_dir / "asset_content_list.json").write_text(
            json.dumps(
                [
                    {"type": "heading", "text": "Experimental Section", "level": 1},
                    {"type": "heading", "text": "Conclusion", "level": 1},
                ]
            ),
            encoding="utf-8",
        )

        headers = loader._extract_headers(md_path.read_text(encoding="utf-8").splitlines(), md_path=md_path)

        experimental = next(h for h in headers if h["text"] == "Experimental Section")
        assert experimental["line"] == 3
        assert experimental["source"] == "asset_content_list.json"


class TestFallbackWindows:
    def test_iter_fallback_windows_scans_back_forty_percent(self):
        lines = [f"line {i}" for i in range(1, 1001)]

        windows = list(loader._iter_fallback_windows(lines))

        assert windows
        assert windows[0][1] == 1000
        assert windows[-1][0] == 400
        assert len(windows) <= 6


class TestEnrichL3Diagnostics:
    def test_enrich_l3_records_failure_reason_and_status(self, tmp_path: Path, monkeypatch):
        paper_dir, md_path = _make_article(tmp_path, "Fail-2026-Test")
        md_path.write_text("# Title\n\nBody only.\n", encoding="utf-8")

        monkeypatch.setattr(loader, "enrich_toc", lambda *args, **kwargs: False)
        monkeypatch.setattr(
            loader,
            "_primary_path",
            lambda *args, **kwargs: loader._fail(
                "primary",
                "no_conclusion",
                "LLM 未识别到结论节标题",
                method="primary-attempt1",
            ),
        )
        monkeypatch.setattr(
            loader,
            "_fallback_path",
            lambda *args, **kwargs: loader._fail(
                "fallback",
                "no_conclusion",
                "滑窗扫描未找到结论节",
                method="fallback-window1",
            ),
        )

        ok = loader.enrich_l3(paper_dir / "meta.json", md_path, config=_UNUSED_CONFIG)

        assert ok is False
        data = json.loads((paper_dir / "meta.json").read_text(encoding="utf-8"))
        assert data["l3_last_attempt_status"] == "bad_structure"
        assert "仅检测到 1 个候选节标题" in data["l3_last_attempt_reason"]

    def test_enrich_l3_auto_populates_toc_when_missing(self, tmp_path: Path, monkeypatch):
        paper_dir, md_path = _make_article(tmp_path, "AutoTOC-2026-Test")
        md_path.write_text("Paper title\n\n1. Intro\nBody\n\nConclusions\nDone.\n", encoding="utf-8")

        called = {"toc": False}

        def fake_enrich_toc(json_path: Path, _md_path: Path, _config, *, force: bool = False, inspect: bool = False):
            del force, inspect
            called["toc"] = True
            data = json.loads(json_path.read_text(encoding="utf-8"))
            data["toc"] = [{"line": 6, "level": 1, "title": "Conclusions"}]
            json_path.write_text(json.dumps(data), encoding="utf-8")
            return True

        monkeypatch.setattr(loader, "enrich_toc", fake_enrich_toc)
        monkeypatch.setattr(
            loader,
            "_l3_from_toc",
            lambda *args, **kwargs: loader._ok(
                "toc",
                "toc",
                "Validated conclusion text.",
                reason="校验通过",
                start_line=6,
                end_line=7,
            ),
        )

        ok = loader.enrich_l3(paper_dir / "meta.json", md_path, config=_UNUSED_CONFIG)

        assert ok is True
        assert called["toc"] is True
        data = json.loads((paper_dir / "meta.json").read_text(encoding="utf-8"))
        assert data["l3_extraction_method"] == "toc"
        assert data["l3_last_attempt_status"] == "ok"
        assert data["l3"]["schema_version"] == "autor.l3.v2"
        assert data["l3"]["mode"] == "explicit_section"

    def test_enrich_l3_synthesizes_when_no_explicit_conclusion(self, tmp_path: Path, monkeypatch):
        paper_dir, md_path = _make_article(tmp_path, "Synthesis-2026-Test")
        meta_path = paper_dir / "meta.json"
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        data["abstract"] = "In 42 patients, treatment improved response from 20% to 55% while toxicity remained limited."
        meta_path.write_text(json.dumps(data), encoding="utf-8")
        md_path.write_text(
            "# Test paper\n\n"
            "## Results\n"
            "The cohort included n = 42 patients. The response rate increased to 55% after treatment.\n\n"
            "## Discussion\n"
            "These data suggest clinically meaningful activity, although follow-up was short and validation is needed.\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(loader, "enrich_toc", lambda *args, **kwargs: False)
        monkeypatch.setattr(
            loader,
            "_primary_path",
            lambda *args, **kwargs: loader._fail("primary", "no_conclusion", "no conclusion", method="primary"),
        )
        monkeypatch.setattr(
            loader,
            "_fallback_path",
            lambda *args, **kwargs: loader._fail("fallback", "no_conclusion", "no conclusion", method="fallback"),
        )

        def fake_call_llm(prompt: str, _config, timeout=None):
            assert "paper-level takeaway card" in prompt
            return json.dumps(
                {
                    "takeaway": "The paper supports a treatment-activity conclusion, with improved response in a small cohort but limited follow-up.",
                    "key_findings": [
                        {"claim": "Response improved after treatment.", "evidence_basis": "abstract/results"}
                    ],
                    "quantitative_signals": [
                        {"text": "n = 42 patients; response increased to 55%.", "source": "results"}
                    ],
                    "limitations": ["Follow-up was short and validation is needed."],
                    "confidence": "medium",
                    "warnings": [],
                }
            )

        monkeypatch.setattr(loader, "_call_llm", fake_call_llm)

        ok = loader.enrich_l3(meta_path, md_path, config=_UNUSED_CONFIG)

        assert ok is True
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data["l3_extraction_method"] == "synthesis"
        assert data["l3"]["mode"] == "inferred_synthesis"
        assert data["l3"]["quantitative_signals"]
        assert "no_explicit_conclusion_section" in data["l3"]["warnings"]
        rendered = loader.load_l3(meta_path)
        assert rendered is not None
        assert "Quantitative signals" in rendered

    def test_explicit_l3_can_be_augmented_with_quantitative_signals(self, tmp_path: Path, monkeypatch):
        paper_dir, md_path = _make_article(tmp_path, "Hybrid-2026-Test")
        md_path.write_text(
            "# Test paper\n\n"
            "## Results\n"
            "The trial enrolled n = 42 patients and achieved a 55% response rate.\n\n"
            "## Conclusions\n"
            "The study supports clinically meaningful treatment activity and warrants further validation.\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(loader, "enrich_toc", lambda *args, **kwargs: False)
        monkeypatch.setattr(
            loader,
            "_primary_path",
            lambda *args, **kwargs: loader._ok(
                "primary",
                "primary-attempt1",
                "The study supports clinically meaningful treatment activity and warrants further validation.",
                reason="校验通过",
                start_line=6,
                end_line=7,
            ),
        )

        ok = loader.enrich_l3(paper_dir / "meta.json", md_path, config=_UNUSED_CONFIG)

        assert ok is True
        data = json.loads((paper_dir / "meta.json").read_text(encoding="utf-8"))
        assert data["l3"]["mode"] == "hybrid"
        assert any("55%" in item["text"] for item in data["l3"]["quantitative_signals"])
