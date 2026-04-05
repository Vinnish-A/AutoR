#!/usr/bin/env python3
"""Render a compact Markdown summary from normalized clinical trial JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_payload(path: str | None) -> dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.load(sys.stdin)



def compact(text: str | None, limit: int = 120) -> str:
    value = " ".join((text or "").split())
    if not value:
        return "unknown"
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."



def join_list(values: list[str], limit: int = 3) -> str:
    if not values:
        return "unknown"
    trimmed = values[:limit]
    text = ", ".join(trimmed)
    if len(values) > limit:
        text += f" (+{len(values) - limit})"
    return text



def p_summary(record: dict[str, Any]) -> str:
    patient = record.get("pico", {}).get("P", {})
    conditions = join_list(patient.get("conditions", []), limit=2)
    enrollment = patient.get("enrollment", {})
    count = enrollment.get("count", "unknown")
    enrollment_type = enrollment.get("type", "unknown")
    return f"{conditions}<br>n={count} ({enrollment_type})"



def i_summary(record: dict[str, Any]) -> str:
    intervention = record.get("pico", {}).get("I", {})
    names = join_list(intervention.get("interventions", []), limit=3)
    return compact(names, limit=100)



def c_summary(record: dict[str, Any]) -> str:
    comparison = record.get("pico", {}).get("C", {})
    return compact(comparison.get("summary", "unknown"), limit=100)



def o_summary(record: dict[str, Any]) -> str:
    outcomes = record.get("pico", {}).get("O", {})
    primary = outcomes.get("primary_endpoints", [])
    endpoint = primary[0]["measure"] if primary else "unknown"
    effect = outcomes.get("effect_summary", "unknown")
    if effect != "unknown":
        return f"{compact(endpoint, 80)}<br>{compact(effect, 120)}"
    return compact(endpoint, 120)



def location_summary(record: dict[str, Any]) -> str:
    return compact(record.get("location_summary", "unknown"), limit=80)



def phase_summary(record: dict[str, Any]) -> str:
    phases = record.get("phase", [])
    if not phases:
        return "unknown"
    return ", ".join(phases)



def render_table(results: list[dict[str, Any]]) -> str:
    lines = [
        "| NCT ID | 标题 | P（患者/样本量） | I（干预） | C（对照） | O（主要终点/疗效） | Phase | Status | 地区 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for record in results:
        lines.append(
            "| {trial_id} | {title} | {p} | {i} | {c} | {o} | {phase} | {status} | {location} |".format(
                trial_id=record.get("trial_id", "unknown"),
                title=compact(record.get("title"), 90),
                p=p_summary(record),
                i=i_summary(record),
                c=c_summary(record),
                o=o_summary(record),
                phase=phase_summary(record),
                status=record.get("status", "unknown"),
                location=location_summary(record),
            )
        )
    return "\n".join(lines)



def render_evidence(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for record in results:
        lines.append(f"- **{record.get('trial_id', 'unknown')}**: {record.get('title', 'unknown')}")
        for item in record.get("evidence", [])[:4]:
            lines.append(f"  - {item}")
    return "\n".join(lines)



def main() -> None:
    parser = argparse.ArgumentParser(description="Render Markdown summary from normalized clinical trial JSON.")
    parser.add_argument("input", nargs="?", help="Normalized result JSON path. Reads stdin when omitted.")
    parser.add_argument("--top", type=int, default=10, help="Maximum number of trials to render.")
    args = parser.parse_args()

    payload = load_payload(args.input)
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise SystemExit("Input JSON must contain a 'results' array.")
    selected = results[: args.top]
    print(render_table(selected))
    print()
    print("证据摘要")
    print()
    print(render_evidence(selected))


if __name__ == "__main__":
    main()
