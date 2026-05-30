from __future__ import annotations

import json

from autor.config import _build_config
from autor.write_agent.contracts import load_writing_contracts
from autor.write_agent.runner import build, preflight


def _write_planning_package(ws_dir):
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "references.bib").write_text(
        "@article{Smith2024,\n title={Direct evidence}\n}\n@article{Jones2023,\n title={Adjacent evidence}\n}\n",
        encoding="utf-8",
    )
    (ws_dir / "reference-map.json").write_text(
        json.dumps(
            {
                "references": [
                    {"citekey": "Smith2024", "bibliographic_validity": "citable", "citation_policy": "must_cite"},
                    {"citekey": "Jones2023", "bibliographic_validity": "citable", "citation_policy": "cite_if_relevant"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (ws_dir / "review-plan.md").write_text(
        "# S1 Direct evidence\n\nSmith shows the direct finding [@Smith2024].\n",
        encoding="utf-8",
    )
    (ws_dir / "evidence-ledger.md").write_text(
        "| section | claim | key |\n|---|---|---|\n| S1 | direct evidence leads | [@Smith2024] |\n",
        encoding="utf-8",
    )
    (ws_dir / "table-figure-plan.md").write_text(
        "S1 requires T1 and F1.\nJones2023 is a table-only boundary row for T1, not S1 prose-support evidence.\n",
        encoding="utf-8",
    )


class TestWriteAgentPreflight:
    def test_missing_canonical_files_blocks(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        cfg.ensure_dirs()
        result = preflight("missing-ws", cfg)

        assert result.status == "BLOCKED_BY_MISSING_INPUT"
        assert "references.bib" in result.details["missing_files"]

    def test_valid_package_builds_kernels_and_seeds(self, tmp_path):
        cfg = _build_config({"write_agent": {"seed_count": 2}}, tmp_path)
        cfg.ensure_dirs()
        ws_dir = tmp_path / "workspace" / "write-ws"
        _write_planning_package(ws_dir)

        result = build("write-ws", cfg)

        assert result.status == "SEEDS_GENERATED"
        assert (ws_dir / "sidecars" / "section-kernels.jsonl").exists()
        assert (ws_dir / "sidecars" / "seed-bank.jsonl").exists()
        assert (ws_dir / "sidecars" / "human-move-bank.json").exists()
        assert (ws_dir / "sidecars" / "anti-ai-patterns.json").exists()
        assert (ws_dir / "sidecars" / "section-pattern-contracts.jsonl").exists()
        assert (ws_dir / "sidecars" / "section-writing-contract.jsonl").exists()
        assert "### S1: Direct evidence" in (ws_dir / "write.md").read_text(encoding="utf-8")

        contract = load_writing_contracts(ws_dir)["S1"]
        assert "Smith2024" in contract.prose_allowed_citekeys
        assert "Jones2023" in contract.table_only_citekeys
        assert "Jones2023" not in contract.prose_allowed_citekeys
