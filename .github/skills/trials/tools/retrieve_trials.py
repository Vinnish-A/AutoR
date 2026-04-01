#!/usr/bin/env python3
"""Retrieve and normalize clinical trial records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clinical_trials_common import (
    SearchInput,
    build_api_requests,
    build_provider_targets,
    build_unresolved_questions,
    extract_trial_records,
    fetch_query_variants,
    normalize_query,
)


def load_fixture(path: str) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    studies = payload.get("studies")
    if not isinstance(studies, list):
        raise SystemExit("Fixture must contain a top-level 'studies' array.")
    return studies



def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve clinical trial records.")
    parser.add_argument("query", nargs="*", help="Free-text theme when --theme is omitted.")
    parser.add_argument("--theme", help="Free-text theme, e.g. 'CAR-T 序贯治疗'.")
    parser.add_argument("--condition", help="Disease or condition.")
    parser.add_argument("--intervention", help="Drug or intervention.")
    parser.add_argument("--phase", help="Optional clinical phase filter.")
    parser.add_argument("--status", help="Optional trial status filter.")
    parser.add_argument("--location", help="Optional geographic filter.")
    parser.add_argument("--page-size", type=int, default=20, help="Per-request page size.")
    parser.add_argument("--max-records", type=int, default=25, help="Maximum number of unique records to keep.")
    parser.add_argument("--input-response", help="Offline fixture JSON with a top-level 'studies' array.")
    parser.add_argument("--output", help="Optional output JSON path.")
    args = parser.parse_args()

    theme = args.theme or " ".join(args.query)
    normalized = normalize_query(
        SearchInput(
            theme=theme,
            condition=args.condition,
            intervention=args.intervention,
            phase=args.phase,
            status=args.status,
            location=args.location,
        )
    )
    api_requests = build_api_requests(normalized, page_size=args.page_size)

    if args.input_response:
        studies = load_fixture(args.input_response)
        fetch_log = [{"name": "fixture", "url": args.input_response, "returned_studies": len(studies), "unique_total": len(studies)}]
    else:
        studies, fetch_log = fetch_query_variants(api_requests, max_records=args.max_records)

    results = extract_trial_records(studies, normalized)
    payload = {
        "query": normalized["query_label"],
        "normalized_query": normalized,
        "provider_targets": build_provider_targets(normalized, api_requests),
        "api_requests": api_requests,
        "fetch_log": fetch_log,
        "results": results,
        "unresolved_questions": build_unresolved_questions(results, normalized),
    }

    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
