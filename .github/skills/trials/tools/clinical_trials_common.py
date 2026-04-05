#!/usr/bin/env python3
"""Shared helpers for the clinical trials retrieval skill."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CLINICALTRIALS_ENDPOINT = "https://clinicaltrials.gov/api/v2/studies"

CONDITION_TRANSLATIONS = {
    "非小细胞肺癌": "non-small cell lung cancer",
    "小细胞肺癌": "small cell lung cancer",
    "肺癌": "lung cancer",
    "乳腺癌": "breast cancer",
    "结直肠癌": "colorectal cancer",
    "淋巴瘤": "lymphoma",
    "b细胞淋巴瘤": "B-cell lymphoma",
    "非霍奇金淋巴瘤": "non-Hodgkin lymphoma",
    "急性淋巴细胞白血病": "acute lymphoblastic leukemia",
    "急性髓系白血病": "acute myeloid leukemia",
    "白血病": "leukemia",
    "多发性骨髓瘤": "multiple myeloma",
    "胃癌": "gastric cancer",
    "肝癌": "liver cancer",
}

INTERVENTION_ALIASES = {
    "CAR-T": [
        "car-t",
        "car t",
        "cart",
        "chimeric antigen receptor t-cell",
        "chimeric antigen receptor t-cells",
        "嵌合抗原受体t细胞",
        "嵌合抗原受体 t 细胞",
        "car-t细胞",
        "cart细胞",
    ],
    "PD-1": ["pd-1", "pd1", "pd 1"],
    "Pembrolizumab": ["pembrolizumab", "keytruda", "k药", "k 药"],
    "Nivolumab": ["nivolumab", "opdivo", "o药", "o 药"],
    "Trastuzumab": ["trastuzumab", "herceptin", "赫赛汀"],
}

PHASE_ALIASES = {
    "early phase 1": ["EARLY_PHASE1"],
    "phase 1": ["PHASE1"],
    "phase i": ["PHASE1"],
    "phase 1/phase 2": ["PHASE1", "PHASE2"],
    "phase 1/2": ["PHASE1", "PHASE2"],
    "phase i/ii": ["PHASE1", "PHASE2"],
    "phase 2": ["PHASE2"],
    "phase ii": ["PHASE2"],
    "phase 2/3": ["PHASE2", "PHASE3"],
    "phase ii/iii": ["PHASE2", "PHASE3"],
    "phase 3": ["PHASE3"],
    "phase iii": ["PHASE3"],
    "phase 4": ["PHASE4"],
    "phase iv": ["PHASE4"],
}

STATUS_ALIASES = {
    "recruiting": "RECRUITING",
    "招募中": "RECRUITING",
    "active/not recruiting": "ACTIVE_NOT_RECRUITING",
    "active not recruiting": "ACTIVE_NOT_RECRUITING",
    "进行中，未招募": "ACTIVE_NOT_RECRUITING",
    "completed": "COMPLETED",
    "已完成": "COMPLETED",
    "terminated": "TERMINATED",
    "已终止": "TERMINATED",
    "not yet recruiting": "NOT_YET_RECRUITING",
    "尚未招募": "NOT_YET_RECRUITING",
    "suspended": "SUSPENDED",
    "withdrawn": "WITHDRAWN",
    "enrolling by invitation": "ENROLLING_BY_INVITATION",
}

LOCATION_ALIASES = {
    "china": "China",
    "中国": "China",
    "cn": "China",
    "us": "United States",
    "usa": "United States",
    "united states": "United States",
    "美国": "United States",
    "global": "Global",
    "全球": "Global",
    "europe": "Europe",
    "eu": "Europe",
}

TERM_REPLACEMENTS = [
    ("序贯治疗", "sequential therapy"),
    ("序贯", "sequential"),
    ("桥接", "bridging"),
    ("维持", "maintenance"),
    ("巩固", "consolidation"),
    ("输注后", "post-infusion"),
    ("之后", "followed by"),
    ("疗法", "therapy"),
]

MODIFIER_ALIASES = {
    "sequential": ["sequential", "sequential therapy", "序贯", "序贯治疗"],
    "bridging": ["bridging", "bridging therapy", "桥接"],
    "maintenance": ["maintenance", "booster", "维持"],
    "consolidation": ["consolidation", "巩固"],
    "post_infusion": ["post-infusion", "post infusion", "输注后"],
}

MODIFIER_SEARCH_EXPANSIONS = {
    "sequential": ["sequential", "maintenance", "bridging", "consolidation"],
    "bridging": ["bridging", "sequential"],
    "maintenance": ["maintenance", "sequential"],
    "consolidation": ["consolidation", "sequential"],
    "post_infusion": ["post-infusion", "bridging", "sequential"],
}

SEQUENTIAL_SIGNAL_TERMS = [
    "sequential",
    "maintenance",
    "bridging",
    "consolidation",
    "booster",
    "post-infusion",
    "prior to",
]


@dataclass
class SearchInput:
    theme: str | None = None
    condition: str | None = None
    intervention: str | None = None
    phase: str | None = None
    status: str | None = None
    location: str | None = None


def normalize_spaces(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()



def compact_text(text: str | None, limit: int = 240) -> str:
    value = normalize_spaces(text)
    if not value:
        return "unknown"
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."



def lower(text: str | None) -> str:
    return normalize_spaces(text).lower()



def contains_term(text: str, needle: str) -> bool:
    haystack = lower(text)
    token = lower(needle)
    if not token:
        return False
    if any(ord(char) > 127 for char in token):
        return token in haystack
    pattern = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None



def unique_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = normalize_spaces(value)
        if not item:
            continue
        marker = item.lower()
        if marker in seen:
            continue
        seen.add(marker)
        output.append(item)
    return output



def canonicalize_condition(value: str | None) -> str | None:
    text = normalize_spaces(value)
    if not text:
        return None
    lowered = text.lower()
    for source, target in CONDITION_TRANSLATIONS.items():
        if source.lower() == lowered:
            return target
    return text



def canonicalize_intervention(value: str | None) -> str | None:
    text = normalize_spaces(value)
    if not text:
        return None
    lowered = text.lower()
    for canonical, aliases in INTERVENTION_ALIASES.items():
        if lowered == canonical.lower() or any(lower(alias) == lowered for alias in aliases):
            return canonical
    return text



def canonicalize_phase(value: str | None) -> dict[str, Any]:
    text = lower(value)
    if not text:
        return {"raw": None, "tokens": [], "api_expression": None}
    for alias, tokens in PHASE_ALIASES.items():
        if text == alias:
            api_expression = f"AREA[Phase]{tokens[0]}" if len(tokens) == 1 else None
            return {"raw": value, "tokens": tokens, "api_expression": api_expression}
    if text.startswith("phase"):
        digits = re.findall(r"\d+", text)
        if digits:
            tokens = [f"PHASE{digit}" for digit in digits]
            api_expression = f"AREA[Phase]{tokens[0]}" if len(tokens) == 1 else None
            return {"raw": value, "tokens": tokens, "api_expression": api_expression}
    return {"raw": value, "tokens": [], "api_expression": None}



def canonicalize_status(value: str | None) -> str | None:
    text = lower(value)
    if not text:
        return None
    return STATUS_ALIASES.get(text, value)



def canonicalize_location(value: str | None) -> str | None:
    text = lower(value)
    if not text:
        return None
    return LOCATION_ALIASES.get(text, normalize_spaces(value))



def translate_theme(text: str | None) -> str | None:
    value = normalize_spaces(text)
    if not value:
        return None
    translated = value
    for source, target in TERM_REPLACEMENTS:
        translated = re.sub(re.escape(source), target, translated, flags=re.IGNORECASE)
    return normalize_spaces(translated)



def detect_intervention_from_text(text: str | None) -> str | None:
    source = normalize_spaces(text)
    if not source:
        return None
    for canonical, aliases in INTERVENTION_ALIASES.items():
        if contains_term(source, canonical) or any(contains_term(source, alias) for alias in aliases):
            return canonical
    return None



def detect_condition_from_text(text: str | None) -> str | None:
    source = normalize_spaces(text)
    if not source:
        return None
    for condition, translated in CONDITION_TRANSLATIONS.items():
        if contains_term(source, condition) or contains_term(source, translated):
            return translated
    return None



def detect_modifier_concepts(text: str | None) -> list[str]:
    source = normalize_spaces(text)
    if not source:
        return []
    hits: list[str] = []
    for canonical, aliases in MODIFIER_ALIASES.items():
        if any(contains_term(source, alias) for alias in aliases):
            hits.append(canonical)
    return unique_keep_order(hits)



def build_modifier_search_terms(concepts: Sequence[str]) -> list[str]:
    terms: list[str] = []
    for concept in concepts:
        terms.extend(MODIFIER_SEARCH_EXPANSIONS.get(concept, [concept]))
    return unique_keep_order(terms)



def build_query_label(search_input: SearchInput) -> str:
    if search_input.theme:
        return normalize_spaces(search_input.theme)
    parts = [
        normalize_spaces(search_input.condition),
        normalize_spaces(search_input.intervention),
        normalize_spaces(search_input.phase),
        normalize_spaces(search_input.status),
        normalize_spaces(search_input.location),
    ]
    return " | ".join(part for part in parts if part)



def normalize_query(search_input: SearchInput) -> dict[str, Any]:
    theme = normalize_spaces(search_input.theme)
    theme_english = translate_theme(theme)
    condition = canonicalize_condition(search_input.condition) or detect_condition_from_text(theme_english or theme)
    intervention = canonicalize_intervention(search_input.intervention) or detect_intervention_from_text(theme_english or theme)
    phase_info = canonicalize_phase(search_input.phase)
    status = canonicalize_status(search_input.status)
    location = canonicalize_location(search_input.location)
    modifier_concepts = detect_modifier_concepts(theme_english or theme)
    modifier_search_terms = build_modifier_search_terms(modifier_concepts)

    if not (theme or condition or intervention):
        raise ValueError("Provide a theme or at least one of condition/intervention.")

    fallback_term = normalize_spaces(theme_english or theme)
    if not condition and not intervention and not fallback_term:
        raise ValueError("Could not derive a searchable condition or intervention from the input.")

    query_label = build_query_label(search_input)
    return {
        "query_label": query_label,
        "theme": theme or None,
        "theme_english": theme_english or None,
        "condition": condition,
        "intervention": intervention,
        "phase": phase_info,
        "status": status,
        "location": location,
        "modifier_concepts": modifier_concepts,
        "modifier_search_terms": modifier_search_terms,
        "fallback_term": fallback_term or None,
        "intervention_terms": unique_keep_order(
            [intervention, *INTERVENTION_ALIASES.get(intervention or "", [])]
        ) if intervention else [],
    }



def build_api_requests(normalized_query: dict[str, Any], page_size: int = 20, max_pages: int = 2) -> list[dict[str, Any]]:
    base_params: dict[str, Any] = {"format": "json", "pageSize": page_size}
    if normalized_query.get("condition"):
        base_params["query.cond"] = normalized_query["condition"]
    if normalized_query.get("intervention"):
        base_params["query.intr"] = normalized_query["intervention"]
    if normalized_query.get("location") and normalized_query["location"] != "Global":
        base_params["query.locn"] = normalized_query["location"]
    if normalized_query.get("status"):
        base_params["filter.overallStatus"] = normalized_query["status"]
    if normalized_query.get("phase", {}).get("api_expression"):
        base_params["filter.advanced"] = normalized_query["phase"]["api_expression"]

    requests: list[dict[str, Any]] = []
    modifier_terms = normalized_query.get("modifier_search_terms", [])
    if modifier_terms:
        for index, term in enumerate(modifier_terms, start=1):
            params = dict(base_params)
            params["query.term"] = term
            requests.append(
                {
                    "name": f"modifier-{index}",
                    "purpose": f"modifier expansion: {term}",
                    "endpoint": CLINICALTRIALS_ENDPOINT,
                    "params": params,
                    "max_pages": max_pages,
                }
            )
    else:
        requests.append(
            {
                "name": "structured-primary",
                "purpose": "condition/intervention structured search",
                "endpoint": CLINICALTRIALS_ENDPOINT,
                "params": dict(base_params),
                "max_pages": max_pages,
            }
        )
        fallback_term = normalized_query.get("fallback_term")
        if fallback_term and fallback_term.lower() not in {
            lower(normalized_query.get("condition")),
            lower(normalized_query.get("intervention")),
            "",
        }:
            params = dict(base_params)
            params["query.term"] = fallback_term
            requests.append(
                {
                    "name": "theme-fallback",
                    "purpose": "theme-based recall expansion",
                    "endpoint": CLINICALTRIALS_ENDPOINT,
                    "params": params,
                    "max_pages": max_pages,
                }
            )

    if not requests:
        params = dict(base_params)
        if normalized_query.get("fallback_term"):
            params["query.term"] = normalized_query["fallback_term"]
        requests.append(
            {
                "name": "theme-only",
                "purpose": "free-text fallback",
                "endpoint": CLINICALTRIALS_ENDPOINT,
                "params": params,
                "max_pages": max_pages,
            }
        )

    for request in requests:
        request["url"] = build_url(request["endpoint"], request["params"])
    return requests



def build_url(endpoint: str, params: dict[str, Any]) -> str:
    return endpoint + "?" + urlencode(params, doseq=True)



def build_provider_targets(normalized_query: dict[str, Any], api_requests: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    query_text = normalized_query.get("theme_english") or normalized_query.get("query_label") or "clinical trial"
    return [
        {
            "name": "ClinicalTrials.gov",
            "implemented": True,
            "access_mode": "json_api",
            "endpoint": CLINICALTRIALS_ENDPOINT,
            "notes": "Primary live data source. Supports structured JSON via API v2.",
            "example_request": api_requests[0]["url"] if api_requests else CLINICALTRIALS_ENDPOINT,
        },
        {
            "name": "CTIS / EU CTR",
            "implemented": False,
            "access_mode": "public_search_portal",
            "search_url": "https://euclinicaltrials.eu/search-for-clinical-trials/",
            "legacy_search_url": "https://www.clinicaltrialsregister.eu/ctr-search/search",
            "notes": "No stable public REST API verified; community tooling usually scrapes the web interface.",
            "suggested_query": query_text,
        },
        {
            "name": "ChiCTR",
            "implemented": False,
            "access_mode": "public_search_portal",
            "search_url": "https://www.chictr.org.cn/searchprojEN.html",
            "notes": "No official open REST API verified; individual records can be exported from the website and community tools scrape filtered URLs.",
            "suggested_query": query_text,
        },
        {
            "name": "WHO ICTRP",
            "implemented": False,
            "access_mode": "portal_plus_request_web_service",
            "search_url": "https://trialsearch.who.int/",
            "web_service_url": "https://www.who.int/tools/clinical-trials-registry-platform/the-ictrp-search-portal/ictrp-search-portal-web-service",
            "notes": "Public search portal is open; XML web service access is by request rather than a self-service public API.",
            "suggested_query": query_text,
        },
    ]



def fetch_json(endpoint: str, params: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    request = Request(
        build_url(endpoint, params),
        headers={"User-Agent": "clinical-trials-retrieval-skill/0.1"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))



def fetch_query_variants(api_requests: Sequence[dict[str, Any]], max_records: int = 25) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen: dict[str, dict[str, Any]] = {}
    fetch_log: list[dict[str, Any]] = []
    for request in api_requests:
        if len(seen) >= max_records:
            break
        params = dict(request["params"])
        page_token: str | None = None
        page_count = 0
        while True:
            if page_token:
                params["pageToken"] = page_token
            else:
                params.pop("pageToken", None)
            payload = fetch_json(request["endpoint"], params)
            studies = payload.get("studies", [])
            for study in studies:
                nct_id = get_nct_id(study)
                if nct_id and nct_id not in seen:
                    seen[nct_id] = study
                if len(seen) >= max_records:
                    break
            fetch_log.append(
                {
                    "name": request["name"],
                    "url": build_url(request["endpoint"], params),
                    "returned_studies": len(studies),
                    "unique_total": len(seen),
                }
            )
            page_token = payload.get("nextPageToken")
            page_count += 1
            if not page_token or len(seen) >= max_records or page_count >= int(request.get("max_pages", 1)):
                break
    return list(seen.values()), fetch_log



def get_nested(source: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = source
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current



def get_nct_id(study: dict[str, Any]) -> str | None:
    return get_nested(study, "protocolSection", "identificationModule", "nctId")



def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]



def extract_intervention_names(study: dict[str, Any]) -> list[str]:
    interventions = get_nested(study, "protocolSection", "armsInterventionsModule", "interventions", default=[])
    return unique_keep_order(str(item.get("name", "")) for item in interventions if isinstance(item, dict))



def extract_arm_groups(study: dict[str, Any]) -> list[dict[str, Any]]:
    arms = get_nested(study, "protocolSection", "armsInterventionsModule", "armGroups", default=[])
    return [item for item in arms if isinstance(item, dict)]



def extract_locations(study: dict[str, Any]) -> list[dict[str, str]]:
    locations = get_nested(study, "protocolSection", "contactsLocationsModule", "locations", default=[])
    output: list[dict[str, str]] = []
    for item in locations:
        if not isinstance(item, dict):
            continue
        city = normalize_spaces(item.get("city"))
        country = normalize_spaces(item.get("country"))
        facility = normalize_spaces(item.get("facility"))
        output.append({"city": city or "unknown", "country": country or "unknown", "facility": facility or "unknown"})
    return output



def resolved_status(study: dict[str, Any]) -> str:
    status = normalize_spaces(get_nested(study, "protocolSection", "statusModule", "overallStatus"))
    last_known = normalize_spaces(get_nested(study, "protocolSection", "statusModule", "lastKnownStatus"))
    if status and status != "UNKNOWN":
        return status
    if last_known:
        return last_known
    return status or "unknown"



def phase_tokens(study: dict[str, Any]) -> list[str]:
    phases = get_nested(study, "protocolSection", "designModule", "phases", default=[])
    return unique_keep_order(str(item) for item in phases)



def build_text_blob(study: dict[str, Any]) -> str:
    sections = [
        get_nested(study, "protocolSection", "identificationModule", "briefTitle", default=""),
        get_nested(study, "protocolSection", "identificationModule", "officialTitle", default=""),
        get_nested(study, "protocolSection", "descriptionModule", "briefSummary", default=""),
        get_nested(study, "protocolSection", "descriptionModule", "detailedDescription", default=""),
        " ".join(extract_intervention_names(study)),
        " ".join(str(item) for item in get_nested(study, "protocolSection", "conditionsModule", "conditions", default=[])),
        " ".join(str(item.get("description", "")) for item in extract_arm_groups(study)),
        " ".join(str(item.get("label", "")) for item in extract_arm_groups(study)),
    ]
    return normalize_spaces(" ".join(section for section in sections if section))



def detect_modifier_hits(study: dict[str, Any], normalized_query: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    title_text = normalize_spaces(
        " ".join(
            [
                get_nested(study, "protocolSection", "identificationModule", "briefTitle", default=""),
                get_nested(study, "protocolSection", "identificationModule", "officialTitle", default=""),
            ]
        )
    )
    arm_text = normalize_spaces(
        " ".join(
            [
                str(item.get("label", "")) + " " + str(item.get("description", ""))
                for item in extract_arm_groups(study)
            ]
        )
    )
    summary_text = normalize_spaces(
        " ".join(
            [
                get_nested(study, "protocolSection", "descriptionModule", "briefSummary", default=""),
                get_nested(study, "protocolSection", "descriptionModule", "detailedDescription", default=""),
            ]
        )
    )
    intervention_model = normalize_spaces(
        get_nested(study, "protocolSection", "designModule", "designInfo", "interventionModel", default="")
    )

    if intervention_model.upper() == "SEQUENTIAL":
        hits.append("design:SEQUENTIAL")

    focused_terms = ["maintenance", "bridging", "consolidation", "booster", "post-infusion", "prior to"]
    for term in focused_terms:
        if contains_term(title_text, term) or contains_term(arm_text, term) or contains_term(summary_text, term):
            hits.append(term)

    if "followed by" in lower(title_text) or "followed by" in lower(arm_text):
        hits.append("followed by")

    if "sequential" in lower(title_text) or "sequential" in lower(arm_text) or "sequential" in lower(summary_text):
        hits.append("sequential")

    return unique_keep_order(hits)



def matches_local_filters(study: dict[str, Any], normalized_query: dict[str, Any]) -> bool:
    requested_phases = normalized_query.get("phase", {}).get("tokens", [])
    if requested_phases:
        study_phases = {token.upper() for token in phase_tokens(study)}
        if not study_phases.intersection({token.upper() for token in requested_phases}):
            return False

    requested_status = normalized_query.get("status")
    if requested_status and resolved_status(study).upper() != str(requested_status).upper():
        return False

    requested_location = normalized_query.get("location")
    if requested_location and requested_location != "Global":
        location_blob = " ".join(
            f"{item.get('city', '')} {item.get('country', '')}" for item in extract_locations(study)
        )
        if requested_location.lower() not in location_blob.lower():
            return False

    modifier_concepts = normalized_query.get("modifier_concepts", [])
    return not modifier_concepts or bool(detect_modifier_hits(study, normalized_query))



def calculate_relevance_score(study: dict[str, Any], normalized_query: dict[str, Any]) -> int:
    score = 0
    blob = build_text_blob(study)
    intervention = normalized_query.get("intervention")
    condition = normalized_query.get("condition")
    if intervention and contains_term(blob, intervention):
        score += 5
    if condition and contains_term(blob, condition):
        score += 3
    modifier_hits = detect_modifier_hits(study, normalized_query)
    score += 4 * len(modifier_hits)
    if study.get("hasResults"):
        score += 1
    return score



def summarize_locations(locations: Sequence[dict[str, str]]) -> str:
    if not locations:
        return "unknown"
    labels = []
    for item in locations:
        city = item.get("city")
        country = item.get("country")
        if city and city != "unknown" and country and country != "unknown":
            labels.append(f"{city}, {country}")
        elif country and country != "unknown":
            labels.append(country)
    return "; ".join(unique_keep_order(labels)) or "unknown"



def summarize_comparison(arm_groups: Sequence[dict[str, Any]]) -> dict[str, Any]:
    comparators: list[str] = []
    experimental: list[str] = []
    for arm in arm_groups:
        label = normalize_spaces(arm.get("label")) or "unnamed arm"
        arm_type = normalize_spaces(arm.get("type"))
        if arm_type in {"PLACEBO_COMPARATOR", "ACTIVE_COMPARATOR", "SHAM_COMPARATOR", "NO_INTERVENTION"}:
            comparators.append(f"{label} ({arm_type})")
        elif arm_type == "EXPERIMENTAL":
            experimental.append(label)
    if comparators:
        return {"comparators": comparators, "summary": "; ".join(comparators)}
    if len(arm_groups) <= 1:
        return {"comparators": [], "summary": "single-arm / no explicit comparator"}
    if experimental:
        return {"comparators": [], "summary": "multi-arm study without explicit comparator labels"}
    return {"comparators": [], "summary": "unknown"}



def extract_primary_outcomes(study: dict[str, Any]) -> list[dict[str, str]]:
    outcomes = get_nested(study, "protocolSection", "outcomesModule", "primaryOutcomes", default=[])
    records: list[dict[str, str]] = []
    for item in outcomes:
        if not isinstance(item, dict):
            continue
        records.append(
            {
                "measure": normalize_spaces(item.get("measure")) or "unknown",
                "description": compact_text(item.get("description"), limit=280),
                "time_frame": normalize_spaces(item.get("timeFrame")) or "unknown",
            }
        )
    return records



def extract_effect_summary(study: dict[str, Any]) -> str:
    if not study.get("hasResults"):
        return "unknown"
    outcomes = get_nested(study, "resultsSection", "outcomeMeasuresModule", "outcomeMeasures", default=[])
    if not outcomes:
        return "posted results available; inspect ClinicalTrials.gov results page"
    primary = None
    for item in outcomes:
        if str(item.get("type", "")).upper() == "PRIMARY":
            primary = item
            break
    if primary is None:
        primary = outcomes[0]
    title = normalize_spaces(primary.get("title")) or "Primary outcome"
    time_frame = normalize_spaces(primary.get("timeFrame"))
    unit = normalize_spaces(primary.get("unitOfMeasure")) or "participants"

    value = None
    for outcome_class in primary.get("classes", []):
        for category in outcome_class.get("categories", []):
            for measurement in category.get("measurements", []):
                current = normalize_spaces(measurement.get("value"))
                if current:
                    value = current
                    break
            if value:
                break
        if value:
            break

    denom = None
    for denom_block in primary.get("denoms", []):
        for count in denom_block.get("counts", []):
            current = normalize_spaces(count.get("value"))
            if current:
                denom = current
                break
        if denom:
            break

    if value and denom:
        suffix = f" ({time_frame})" if time_frame else ""
        return f"{title}: {value}/{denom} {unit}{suffix}"
    if value:
        suffix = f" ({time_frame})" if time_frame else ""
        return f"{title}: {value} {unit}{suffix}".strip()
    return f"posted results available for {title}"



def extract_trial_record(study: dict[str, Any], normalized_query: dict[str, Any]) -> dict[str, Any]:
    nct_id = get_nct_id(study) or "unknown"
    arm_groups = extract_arm_groups(study)
    interventions = extract_intervention_names(study)
    locations = extract_locations(study)
    conditions = unique_keep_order(
        str(item) for item in get_nested(study, "protocolSection", "conditionsModule", "conditions", default=[])
    )
    phase_list = phase_tokens(study) or ["unknown"]
    sponsor = normalize_spaces(
        get_nested(study, "protocolSection", "sponsorCollaboratorsModule", "leadSponsor", "name", default="")
    ) or "unknown"
    eligibility = get_nested(study, "protocolSection", "eligibilityModule", "eligibilityCriteria", default="")
    comparison = summarize_comparison(arm_groups)
    primary_outcomes = extract_primary_outcomes(study)
    modifier_hits = detect_modifier_hits(study, normalized_query)
    effect_summary = extract_effect_summary(study)
    enrollment_count = get_nested(study, "protocolSection", "designModule", "enrollmentInfo", "count")
    enrollment_type = normalize_spaces(
        get_nested(study, "protocolSection", "designModule", "enrollmentInfo", "type", default="")
    ) or "unknown"

    evidence = unique_keep_order(
        [
            f"Status: {resolved_status(study)}.",
            f"Phase: {', '.join(phase_list)}.",
            f"Intervention(s): {', '.join(interventions) if interventions else 'unknown'}.",
            f"Primary endpoint: {primary_outcomes[0]['measure']} ({primary_outcomes[0]['time_frame']})." if primary_outcomes else "Primary endpoint: unknown.",
            f"Sequential signals: {', '.join(modifier_hits)}." if modifier_hits else "",
            f"Posted result summary: {effect_summary}." if effect_summary != "unknown" else "",
        ]
    )

    return {
        "trial_id": nct_id,
        "source": "ClinicalTrials.gov",
        "title": normalize_spaces(get_nested(study, "protocolSection", "identificationModule", "briefTitle", default="")) or "unknown",
        "official_title": normalize_spaces(get_nested(study, "protocolSection", "identificationModule", "officialTitle", default="")) or "unknown",
        "url": f"https://clinicaltrials.gov/study/{nct_id}",
        "phase": phase_list,
        "status": resolved_status(study),
        "study_type": normalize_spaces(get_nested(study, "protocolSection", "designModule", "studyType", default="")) or "unknown",
        "has_posted_results": bool(study.get("hasResults")),
        "relevance_score": calculate_relevance_score(study, normalized_query),
        "matched_modifiers": modifier_hits,
        "sponsor": sponsor,
        "locations": locations,
        "pico": {
            "P": {
                "conditions": conditions,
                "enrollment": {
                    "count": enrollment_count if enrollment_count is not None else "unknown",
                    "type": enrollment_type,
                },
                "sex": normalize_spaces(get_nested(study, "protocolSection", "eligibilityModule", "sex", default="")) or "unknown",
                "minimum_age": normalize_spaces(get_nested(study, "protocolSection", "eligibilityModule", "minimumAge", default="")) or "unknown",
                "maximum_age": normalize_spaces(get_nested(study, "protocolSection", "eligibilityModule", "maximumAge", default="")) or "unknown",
                "eligibility_excerpt": compact_text(eligibility, limit=300),
            },
            "I": {
                "interventions": interventions,
                "intervention_types": unique_keep_order(
                    str(item.get("type", "")) for item in get_nested(study, "protocolSection", "armsInterventionsModule", "interventions", default=[])
                    if isinstance(item, dict)
                ),
                "arms": [
                    {
                        "label": normalize_spaces(item.get("label")) or "unknown",
                        "type": normalize_spaces(item.get("type")) or "unknown",
                        "description": compact_text(item.get("description"), limit=220),
                    }
                    for item in arm_groups
                ],
            },
            "C": comparison,
            "O": {
                "primary_endpoints": primary_outcomes,
                "effect_summary": effect_summary,
            },
        },
        "location_summary": summarize_locations(locations),
        "evidence": evidence,
    }



def extract_trial_records(studies: Sequence[dict[str, Any]], normalized_query: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for study in studies:
        if not matches_local_filters(study, normalized_query):
            continue
        records.append(extract_trial_record(study, normalized_query))
    records.sort(key=lambda item: (-item["relevance_score"], not item["has_posted_results"], item["trial_id"]))
    return records



def build_unresolved_questions(results: Sequence[dict[str, Any]], normalized_query: dict[str, Any]) -> list[str]:
    questions: list[str] = []
    if not results:
        questions.append("No trial matched the current structured filters; consider broadening the theme or adding an explicit disease context.")
    if results and all(item["pico"]["O"]["effect_summary"] == "unknown" for item in results):
        questions.append("Most matched trials do not have posted efficacy results yet; manual review of publications may still be needed.")
    if normalized_query.get("modifier_concepts") and results and not any(item["matched_modifiers"] for item in results):
        questions.append("Sequential-treatment intent was not explicitly supported by returned trial text and may need manual confirmation.")
    return questions
