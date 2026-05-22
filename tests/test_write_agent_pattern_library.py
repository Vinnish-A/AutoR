from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

LIB = Path("autor/write_agent/pattern_library")


def _jsonl(name: str):
    return [json.loads(line) for line in (LIB / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def _sources():
    return {row["source_id"]: row for row in yaml.safe_load((LIB / "sources.yaml").read_text(encoding="utf-8"))}


def _license_rows():
    with (LIB / "license-audit.tsv").open(encoding="utf-8") as f:
        return {row["source_id"]: row for row in csv.DictReader(f, delimiter="\t")}


def test_library_minimum_counts():
    assert len(json.loads((LIB / "human-moves.json").read_text(encoding="utf-8"))) >= 10
    assert len(json.loads((LIB / "negative-patterns.json").read_text(encoding="utf-8"))) >= 20
    assert len(_jsonl("positive-passages.jsonl")) >= 100
    assert len(_jsonl("failure-cases.jsonl")) >= 80
    assert len(_jsonl("lexical-ai-markers.jsonl")) >= 120
    assert len(_jsonl("table-patterns.jsonl")) >= 30


def test_every_entry_has_known_source_and_license_audit():
    sources = _sources()
    audit = _license_rows()
    for name in [
        "positive-passages.jsonl",
        "failure-cases.jsonl",
        "lexical-ai-markers.jsonl",
        "table-patterns.jsonl",
        "rewrite-recipes.jsonl",
    ]:
        for row in _jsonl(name):
            assert row.get("source_id"), row
            assert row["source_id"] in sources
            assert row["source_id"] in audit


def test_no_non_open_source_stores_long_verbatim_excerpt():
    audit = _license_rows()
    for name, field in [("positive-passages.jsonl", "verbatim_excerpt"), ("failure-cases.jsonl", "real_excerpt")]:
        for row in _jsonl(name):
            excerpt = row.get(field) or ""
            if not excerpt:
                continue
            license_text = audit[row["source_id"]]["license"]
            max_words = int(audit[row["source_id"]]["max_verbatim_words"])
            assert len(excerpt.split()) <= max_words
            if "CC BY" not in license_text:
                assert len(excerpt.split()) <= 25
