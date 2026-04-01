#!/usr/bin/env python3
"""Build a search plan for the clinical trials retrieval skill."""

from __future__ import annotations

import argparse
import json

from clinical_trials_common import SearchInput, build_api_requests, build_provider_targets, normalize_query


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a clinical trials search plan.")
    parser.add_argument("query", nargs="*", help="Free-text theme when --theme is omitted.")
    parser.add_argument("--theme", help="Free-text theme, e.g. 'CAR-T 序贯治疗'.")
    parser.add_argument("--condition", help="Disease or condition.")
    parser.add_argument("--intervention", help="Drug or intervention.")
    parser.add_argument("--phase", help="Optional clinical phase filter.")
    parser.add_argument("--status", help="Optional trial status filter.")
    parser.add_argument("--location", help="Optional geographic filter.")
    parser.add_argument("--page-size", type=int, default=20, help="Per-request page size for live retrieval plans.")
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
    payload = {
        "query": normalized["query_label"],
        "normalized_query": normalized,
        "provider_targets": build_provider_targets(normalized, api_requests),
        "api_requests": api_requests,
        "recommended_steps": [
            "Run retrieve_trials.py for live ClinicalTrials.gov retrieval when network access is available.",
            "Use render_trial_summary.py to turn the normalized JSON into a compact Markdown table.",
            "If needed, expand manually to CTIS/EU CTR, ChiCTR, or WHO ICTRP using the provider targets included in this plan.",
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
