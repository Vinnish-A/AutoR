"""
workspace.py — 工作区论文子集管理
===================================

每个工作区是 ``workspace/<name>/`` 目录，内含 ``papers.json`` 索引文件
指向 ``data/papers/`` 中的论文。工作区内可自由存放笔记、代码、草稿等。
"""

from __future__ import annotations

import json
import logging
import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


# ============================================================================
#  Internal helpers
# ============================================================================


def _papers_json(ws_dir: Path) -> Path:
    return ws_dir / "papers.json"


def _read(ws_dir: Path) -> list[dict]:
    pj = _papers_json(ws_dir)
    if not pj.exists():
        return []
    try:
        raw = json.loads(pj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"papers.json 格式损坏，操作中止: {pj}") from e
    if not isinstance(raw, list):
        raise RuntimeError(f"papers.json 格式异常（期望 list，实际 {type(raw).__name__}）: {pj}")
    # Filter out malformed entries missing required "id" field
    valid = [e for e in raw if isinstance(e, dict) and "id" in e]
    if len(valid) < len(raw):
        _log.warning("papers.json 中有 %d 条缺少 id 的记录已跳过 (%s)", len(raw) - len(valid), pj)
    return valid


def _write(ws_dir: Path, entries: list[dict]) -> None:
    pj = _papers_json(ws_dir)
    tmp = pj.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(pj)


def _is_dup_dir_name(dir_name: str | None) -> bool:
    return str(dir_name or "").startswith("DUP-")


def _read_meta_for_dir(papers_dir: Path, dir_name: str) -> dict:
    meta_path = papers_dir / dir_name / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# ============================================================================
#  Public API
# ============================================================================


def create(ws_dir: Path) -> Path:
    """创建工作区目录并初始化空 papers.json。

    Args:
        ws_dir: 工作区目录路径。

    Returns:
        papers.json 文件路径。
    """
    ws_dir.mkdir(parents=True, exist_ok=True)
    pj = _papers_json(ws_dir)
    if not pj.exists():
        _write(ws_dir, [])
    return pj


def add(
    ws_dir: Path,
    paper_refs: list[str],
    db_path: Path,
    *,
    resolved: list[dict] | None = None,
) -> list[dict]:
    """添加论文到工作区。

    通过 UUID、目录名、DOI 或 PMID 解析论文，去重后追加到 papers.json。

    当调用方已持有解析好的论文信息时，可通过 *resolved* 参数直接传入，
    跳过逐个 ``lookup_paper()`` 查询（避免 O(N) 次 DB 连接开销）。

    Args:
        ws_dir: 工作区目录路径。
        paper_refs: 论文引用列表（UUID / 目录名 / DOI / PMID）。
            当 *resolved* 不为 ``None`` 时本参数被忽略。
        db_path: index.db 路径，用于 lookup_paper。
        resolved: 预解析的论文列表，每个元素须含 ``"id"`` 和
            ``"dir_name"`` 键。提供时跳过 lookup_paper 查询。

    Returns:
        新增条目列表。
    """
    entries = _read(ws_dir)
    existing_ids = {e["id"] for e in entries}
    added: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    if resolved is not None:
        required_keys = {"id", "dir_name"}
        for idx, rec in enumerate(resolved):
            if not isinstance(rec, dict):
                raise ValueError(
                    f"resolved[{idx}] must be a dict with keys {sorted(required_keys)}, got {type(rec).__name__!s}"
                )
            missing = required_keys.difference(rec.keys())
            if missing:
                raise ValueError(f"resolved[{idx}] is missing required keys {sorted(missing)}: {rec!r}")
            uid = rec["id"]
            if _is_dup_dir_name(rec.get("dir_name")):
                _log.warning("DUP 条目不加入工作区: %s", rec.get("dir_name"))
                continue
            if uid in existing_ids:
                continue
            entry = {"id": uid, "dir_name": rec["dir_name"], "added_at": now}
            entries.append(entry)
            existing_ids.add(uid)
            added.append(entry)
    else:
        from autor.index import lookup_paper

        for ref in paper_refs:
            record = lookup_paper(db_path, ref)
            if record is None:
                _log.warning("无法解析论文引用: %s", ref)
                continue
            uid = record["id"]
            if _is_dup_dir_name(record.get("dir_name")):
                _log.warning("DUP 条目不加入工作区: %s", record.get("dir_name"))
                continue
            if uid in existing_ids:
                _log.debug("已存在，跳过: %s", ref)
                continue
            entry = {"id": uid, "dir_name": record["dir_name"], "added_at": now}
            entries.append(entry)
            existing_ids.add(uid)
            added.append(entry)

    if added:
        _write(ws_dir, entries)
    return added


def dedup(ws_dir: Path, db_path: Path) -> dict[str, object]:
    """Remove duplicate and DUP-prefixed records from a workspace.

    The cleanup is intentionally conservative: records whose current registry
    dir_name or saved dir_name starts with ``DUP-`` are removed, and repeated
    UUIDs are collapsed to their first occurrence.
    """
    from autor.index import lookup_paper

    entries = _read(ws_dir)
    kept: list[dict] = []
    removed: list[dict] = []
    seen_ids: set[str] = set()
    changed = False

    for entry in entries:
        paper_id = entry.get("id")
        record = lookup_paper(db_path, paper_id) if paper_id else None
        current_dir = record["dir_name"] if record else entry.get("dir_name", "")
        reason = ""
        if not paper_id:
            reason = "missing_id"
        elif paper_id in seen_ids:
            reason = "duplicate_id"
        elif _is_dup_dir_name(entry.get("dir_name")) or _is_dup_dir_name(current_dir):
            reason = "dup_dir_name"

        if reason:
            removed_entry = dict(entry)
            removed_entry["dedup_reason"] = reason
            if current_dir:
                removed_entry["current_dir_name"] = current_dir
            removed.append(removed_entry)
            changed = True
            continue

        if current_dir and current_dir != entry.get("dir_name"):
            entry = dict(entry)
            entry["dir_name"] = current_dir
            changed = True
        kept.append(entry)
        seen_ids.add(paper_id)

    if changed:
        _write(ws_dir, kept)
    return {"kept": kept, "removed": removed, "kept_count": len(kept), "removed_count": len(removed)}


def classify_scope(meta: dict, scope: str, cfg=None) -> dict[str, object]:
    """Classify whether one paper fits a topical workspace scope.

    Uses the configured LLM when available. If no key is configured or the LLM
    call fails, falls back to a transparent token-overlap heuristic and marks
    low-overlap records as ``uncertain`` instead of silently excluding them.
    """
    title = str(meta.get("title") or "")
    abstract = str(meta.get("abstract") or meta.get("summary") or "")
    paper_text = f"{title}\n{abstract}".strip()
    if not scope.strip():
        return {"decision": "uncertain", "reason": "empty scope"}

    if cfg is not None:
        try:
            if cfg.resolved_api_key():
                from autor.metrics import call_llm

                prompt = (
                    "Classify whether this paper belongs in the target review workspace.\n"
                    'Return JSON only: {"decision":"in_scope|out_of_scope|uncertain","reason":"..."}.\n\n'
                    f"Scope:\n{scope}\n\nPaper title and abstract:\n{paper_text[:5000]}"
                )
                result = call_llm(prompt, cfg, purpose="workspace.scope_filter", max_tokens=300)
                payload = json.loads(result.content)
                decision = str(payload.get("decision") or "").lower()
                if decision in {"in_scope", "out_of_scope", "uncertain"}:
                    return {"decision": decision, "reason": str(payload.get("reason") or "")}
        except Exception as e:
            _log.warning("LLM scope check failed, using heuristic fallback: %s", e)

    scope_tokens = {
        t
        for t in re.findall(r"[A-Za-z0-9]+", scope.lower())
        if len(t) >= 4 and t not in {"with", "from", "into", "this", "that", "review", "paper", "cancer", "tumor"}
    }
    paper_tokens = set(re.findall(r"[A-Za-z0-9]+", paper_text.lower()))
    overlap = sorted(scope_tokens & paper_tokens)
    if len(overlap) >= 2:
        return {"decision": "in_scope", "reason": f"scope token overlap: {', '.join(overlap[:8])}"}
    if not overlap:
        return {"decision": "out_of_scope", "reason": "no overlap with scope terms"}
    return {"decision": "uncertain", "reason": f"weak scope token overlap: {', '.join(overlap)}"}


def filter_resolved_by_scope(
    resolved: list[dict],
    papers_dir: Path,
    scope: str,
    *,
    cfg=None,
    keep_uncertain: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Filter pre-resolved workspace additions by title/abstract topical scope."""
    kept: list[dict] = []
    rejected: list[dict] = []
    for rec in resolved:
        meta = _read_meta_for_dir(papers_dir, str(rec.get("dir_name") or ""))
        verdict = classify_scope(meta, scope, cfg=cfg)
        decision = verdict["decision"]
        annotated = dict(rec)
        annotated["scope_decision"] = decision
        annotated["scope_reason"] = verdict.get("reason", "")
        if decision == "in_scope" or (decision == "uncertain" and keep_uncertain):
            kept.append(annotated)
        else:
            rejected.append(annotated)
    return kept, rejected


def remove(ws_dir: Path, paper_refs: list[str], db_path: Path) -> list[dict]:
    """从工作区移除论文。

    Args:
        ws_dir: 工作区目录路径。
        paper_refs: 论文引用列表（UUID / 目录名 / DOI / PMID）。
        db_path: index.db 路径。

    Returns:
        被移除的条目列表。
    """
    from autor.index import lookup_paper

    entries = _read(ws_dir)
    remove_ids: set[str] = set()
    for ref in paper_refs:
        record = lookup_paper(db_path, ref)
        if record:
            remove_ids.add(record["id"])
        else:
            # Try direct UUID match
            remove_ids.add(ref)

    removed = [e for e in entries if e["id"] in remove_ids]
    if removed:
        entries = [e for e in entries if e["id"] not in remove_ids]
        _write(ws_dir, entries)
    return removed


def list_workspaces(ws_root: Path) -> list[str]:
    """列出所有含 papers.json 的工作区。

    Args:
        ws_root: workspace/ 根目录。

    Returns:
        工作区名称列表（排序）。
    """
    if not ws_root.is_dir():
        return []
    return sorted(d.name for d in ws_root.iterdir() if d.is_dir() and _papers_json(d).exists())


def validate_workspace_name(name: str) -> bool:
    """Return True if *name* is a safe workspace identifier.

    Rejects empty names, ``.``/``..`` names, leading/trailing whitespace,
    absolute paths, path separators, Windows drive-like names (``:``),
    and any name containing ``..`` to prevent path traversal outside
    ``workspace/``.

    Args:
        name: Candidate workspace name from user input.

    Returns:
        ``True`` when the name is safe for path construction.
    """
    if not name:
        return False
    normalized = name.strip()
    if not normalized:
        return False
    # Reject names with leading/trailing whitespace to avoid ambiguity.
    if normalized != name:
        return False
    if normalized in {".", ".."}:
        return False
    import os

    if os.path.isabs(normalized):
        return False
    # Reject Windows drive-like paths (e.g., C:foo).
    if ":" in normalized:
        return False
    if "/" in normalized or "\\" in normalized:
        return False
    return ".." not in normalized


def show(ws_dir: Path, db_path: Path) -> list[dict]:
    """查看工作区论文列表，刷新过期的 dir_name。

    Args:
        ws_dir: 工作区目录路径。
        db_path: index.db 路径。

    Returns:
        论文条目列表（含最新 dir_name）。
    """
    from autor.index import lookup_paper

    entries = _read(ws_dir)
    changed = False
    for e in entries:
        record = lookup_paper(db_path, e["id"])
        if record and record["dir_name"] != e.get("dir_name"):
            e["dir_name"] = record["dir_name"]
            changed = True
    if changed:
        _write(ws_dir, entries)
    return entries


def read_paper_ids(ws_dir: Path) -> set[str]:
    """返回工作区中所有论文的 UUID 集合。

    Args:
        ws_dir: 工作区目录路径。

    Returns:
        UUID 字符串集合，用于搜索过滤。
    """
    return {e["id"] for e in _read(ws_dir)}


def read_entries(ws_dir: Path) -> list[dict]:
    """Return workspace entries from ``papers.json``."""
    return list(_read(ws_dir))


def identify_exact(
    ws_dir: Path,
    db_path: Path,
    *,
    doi: str | None = None,
    pmid: str | None = None,
    title: str | None = None,
) -> dict[str, list[dict]]:
    """在工作区范围内执行 DOI / PMID / 标题精确匹配。

    Args:
        ws_dir: 工作区目录路径。
        db_path: index.db 路径。
        doi: 精确 DOI。
        pmid: 精确 PubMed ID。
        title: 精确标题（大小写不敏感）。

    Returns:
        ``autor.index.find_exact_matches()`` 的结果字典，但仅包含该工作区中的论文。
    """
    from autor.index import find_exact_matches

    return find_exact_matches(
        db_path,
        doi=doi,
        pmid=pmid,
        title=title,
        paper_ids=read_paper_ids(ws_dir),
    )


def rename(ws_root: Path, old_name: str, new_name: str) -> Path:
    """重命名工作区。

    Args:
        ws_root: workspace/ 根目录。
        old_name: 当前工作区名称。
        new_name: 新工作区名称。

    Returns:
        重命名后的工作区目录路径。

    Raises:
        ValueError: 工作区名称非法（路径穿越/绝对路径等）。
        FileNotFoundError: 源工作区不存在。
        FileExistsError: 目标工作区已存在。
    """
    if not validate_workspace_name(old_name):
        raise ValueError(f"非法工作区名称: {old_name}")
    if not validate_workspace_name(new_name):
        raise ValueError(f"非法工作区名称: {new_name}")
    old_dir = ws_root / old_name
    new_dir = ws_root / new_name
    if not old_dir.exists():
        raise FileNotFoundError(f"工作区不存在: {old_name}")
    if not old_dir.is_dir():
        raise ValueError(f"不是有效工作区目录: {old_name}")
    if not _papers_json(old_dir).exists():
        raise ValueError(f"缺少 papers.json，无法重命名工作区: {old_name}")
    if new_dir.exists():
        raise FileExistsError(f"目标工作区已存在: {new_name}")
    old_dir.rename(new_dir)
    return new_dir


def read_dir_names(ws_dir: Path, db_path: Path) -> set[str]:
    """返回工作区中所有论文的当前目录名集合。

    从 papers_registry 查找最新 dir_name（处理 rename 后的情况）。

    Args:
        ws_dir: 工作区目录路径。
        db_path: index.db 路径。

    Returns:
        目录名字符串集合，用于导出过滤。
    """
    from autor.index import lookup_paper

    names: set[str] = set()
    for e in _read(ws_dir):
        record = lookup_paper(db_path, e["id"])
        if record:
            names.add(record["dir_name"])
        elif e.get("dir_name"):
            names.add(e["dir_name"])
    return names


def export_metadata(
    ws_dir: Path,
    papers_dir: Path,
    db_path: Path,
) -> list[dict]:
    """导出工作区论文的常用元信息。

    按 ``papers.json`` 中记录的顺序读取，并尽量使用 registry 中的最新 dir_name。

    Args:
        ws_dir: 工作区目录路径。
        papers_dir: 主库 ``data/papers`` 目录。
        db_path: index.db 路径。

    Returns:
        元信息列表。每项至少包含 ``id`` / ``dir_name`` / ``title`` / ``doi`` / ``pmid``。
    """
    from autor.index import lookup_paper

    rows: list[dict] = []
    for entry in _read(ws_dir):
        paper_id = entry["id"]
        record = lookup_paper(db_path, paper_id)
        dir_name = record["dir_name"] if record else entry.get("dir_name", "")
        if not dir_name:
            _log.warning("工作区论文缺少 dir_name，已跳过: %s", paper_id)
            continue
        meta_path = papers_dir / dir_name / "meta.json"
        if not meta_path.exists():
            _log.warning("工作区论文 meta.json 不存在，已跳过: %s", dir_name)
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            _log.warning("读取元信息失败，已跳过 %s: %s", dir_name, e)
            continue

        ids = meta.get("ids") or {}
        rows.append(
            {
                "id": paper_id,
                "dir_name": dir_name,
                "title": meta.get("title") or "",
                "authors": meta.get("authors") or [],
                "year": meta.get("year"),
                "journal": meta.get("journal") or "",
                "paper_type": meta.get("paper_type") or "",
                "doi": meta.get("doi") or "",
                "pmid": meta.get("pmid") or ids.get("pmid", "") or "",
                "publication_number": ids.get("patent_publication_number", "") or "",
                "added_at": entry.get("added_at", ""),
            }
        )
    return rows


def _has_l3(meta: dict) -> bool:
    return bool(meta.get("l3"))


def _l3_payload(meta: dict) -> dict:
    l3 = meta.get("l3")
    if isinstance(l3, dict):
        return l3
    return {}


def status(ws_dir: Path, papers_dir: Path, db_path: Path, *, include_papers: bool = False) -> dict[str, Any]:
    """Return a machine-readable workspace health summary.

    Args:
        ws_dir: Workspace directory.
        papers_dir: Main ``data/papers`` directory.
        db_path: SQLite index path.
        include_papers: Include per-paper status rows.

    Returns:
        Summary with counts for metadata, full text and L3 availability.
    """
    entry_count = len(_read(ws_dir))
    rows = export_metadata(ws_dir, papers_dir, db_path)
    missing_rows = max(0, entry_count - len(rows))
    papers: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "workspace": ws_dir.name,
        "count": entry_count,
        "missing_meta": missing_rows,
        "missing_full_text": missing_rows,
        "with_l3": 0,
        "missing_l3": missing_rows,
        "paper_types": {},
        "years": {},
    }
    for row in rows:
        pdir = papers_dir / row["dir_name"]
        meta_path = pdir / "meta.json"
        md_path = pdir / "paper.md"
        meta: dict[str, Any] = {}
        if not meta_path.exists():
            summary["missing_meta"] += 1
        else:
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                summary["missing_meta"] += 1
                meta = {}
        has_full_text = md_path.exists()
        if not has_full_text:
            summary["missing_full_text"] += 1
        has_l3 = _has_l3(meta)
        summary["with_l3" if has_l3 else "missing_l3"] += 1
        ptype = row.get("paper_type") or "unknown"
        summary["paper_types"][ptype] = summary["paper_types"].get(ptype, 0) + 1
        year = str(row.get("year") or "unknown")
        summary["years"][year] = summary["years"].get(year, 0) + 1
        if include_papers:
            l3 = _l3_payload(meta)
            papers.append(
                {
                    **row,
                    "full_text_status": "full_text" if has_full_text else "metadata_only",
                    "has_l3": has_l3,
                    "l3_mode": l3.get("mode", ""),
                    "l3_confidence": l3.get("confidence", ""),
                    "l3_last_attempt_status": meta.get("l3_last_attempt_status", ""),
                }
            )
    if include_papers:
        summary["papers"] = papers
    return summary


def export_evidence(ws_dir: Path, papers_dir: Path, db_path: Path) -> list[dict[str, Any]]:
    """Export workspace metadata plus full-text/L3 evidence status.

    This is intended for agents and MCP clients that need one structured
    evidence layer instead of manually opening each ``meta.json`` file.
    """
    rows = export_metadata(ws_dir, papers_dir, db_path)
    evidence: list[dict[str, Any]] = []
    for row in rows:
        pdir = papers_dir / row["dir_name"]
        meta_path = pdir / "meta.json"
        md_path = pdir / "paper.md"
        meta: dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
        l3 = _l3_payload(meta)
        evidence.append(
            {
                **row,
                "abstract": meta.get("abstract", ""),
                "full_text_status": "full_text" if md_path.exists() else "metadata_only",
                "has_l3": _has_l3(meta),
                "l3_mode": l3.get("mode", ""),
                "l3_confidence": l3.get("confidence", ""),
                "l3_takeaway": l3.get("takeaway", ""),
                "l3_quantitative_signals": l3.get("quantitative_signals", []),
                "l3_last_attempt_status": meta.get("l3_last_attempt_status", ""),
                "l3_last_attempt_reason": meta.get("l3_last_attempt_reason", ""),
            }
        )
    return evidence


def _screen_score(row: dict[str, Any], criteria: str) -> tuple[int, list[str], list[str]]:
    text = " ".join(
        str(row.get(k) or "")
        for k in ("title", "abstract", "journal", "paper_type", "l3_takeaway")
    ).lower()
    tokens = [
        t
        for t in re.findall(r"[A-Za-z0-9]+", criteria.lower())
        if len(t) >= 3 and t not in {"and", "the", "for", "with", "review", "paper", "study"}
    ]
    matched = sorted({t for t in tokens if t in text})
    reasons: list[str] = []
    score = len(matched) * 5
    if row.get("has_l3"):
        score += 2
        reasons.append("has_l3")
    if row.get("full_text_status") == "full_text":
        score += 3
        reasons.append("full_text")
    title = str(row.get("title") or "").lower()
    if "review" in title:
        score += 1
        reasons.append("review_context")
    if int(row.get("year") or 0) >= 2020:
        score += 1
        reasons.append("recent")
    off_scope = [
        "prostate",
        "glioblastoma",
        "pancreatic",
        "colorectal",
        "renal",
        "leber",
        "microneedle",
        "bacteria",
    ]
    penalties = [t for t in off_scope if t in title]
    score -= len(penalties) * 20
    reasons.extend(f"matched:{m}" for m in matched[:10])
    reasons.extend(f"penalty:{p}" for p in penalties)
    return score, matched, reasons


def screen(
    ws_dir: Path,
    papers_dir: Path,
    db_path: Path,
    *,
    criteria: str,
    target_count: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Screen a workspace against criteria and optionally remove excluded papers."""
    rows = export_evidence(ws_dir, papers_dir, db_path)
    scored: list[dict[str, Any]] = []
    for row in rows:
        score, matched, reasons = _screen_score(row, criteria)
        scored.append({**row, "screen_score": score, "matched_criteria": matched, "screen_reasons": reasons})
    scored.sort(key=lambda r: (r["screen_score"], int(r.get("year") or 0)), reverse=True)
    if target_count is None or target_count >= len(scored):
        retained = scored
        excluded: list[dict[str, Any]] = []
    else:
        retained = scored[:target_count]
        excluded = scored[target_count:]

    removed: list[dict[str, Any]] = []
    if apply and excluded:
        removed = remove(ws_dir, [r["id"] for r in excluded], db_path)

    return {
        "workspace": ws_dir.name,
        "criteria": criteria,
        "target_count": target_count,
        "applied": apply,
        "input_count": len(rows),
        "retained_count": len(retained),
        "excluded_count": len(excluded),
        "removed_count": len(removed),
        "retained": retained,
        "excluded": excluded,
    }


_CITE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_:.#$%&+?<>~/|-]+)")


def _load_reference_map(ws_dir: Path) -> dict[str, Any]:
    refmap_path = ws_dir / "reference-map.json"
    if not refmap_path.exists():
        raise FileNotFoundError(f"缺少 reference-map.json: {refmap_path}")
    try:
        payload = json.loads(refmap_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"reference-map.json 格式损坏: {refmap_path}") from e
    if not isinstance(payload.get("references"), list):
        raise RuntimeError(f"reference-map.json 缺少 references 列表: {refmap_path}")
    return payload


def _extract_pandoc_citekeys(text: str) -> set[str]:
    keys = set()
    for match in _CITE_RE.finditer(text):
        key = match.group(1).rstrip(".,;:)]}")
        if key:
            keys.add(key)
    return keys


def _bibliographic_validity(ref: dict[str, Any]) -> str:
    validity = str(ref.get("bibliographic_validity") or "").strip()
    if validity:
        return validity
    policy = str(ref.get("citation_policy") or "").strip()
    if policy == "do_not_cite":
        return "not_citable"
    if ref.get("citekey"):
        return "citable"
    return "needs_metadata_fix"


def citation_coverage(
    ws_dir: Path,
    manuscript_path: Path | None = None,
    *,
    require: str = "retained",
) -> dict[str, Any]:
    """Compare manuscript citations with the workspace reference map.

    Args:
        ws_dir: Workspace directory.
        manuscript_path: Manuscript Markdown path. Defaults to ``final.md``.
        require: Which reference-map rows must appear in the manuscript:
            ``retained``, ``citable``, or ``must_cite``.

    Returns:
        Machine-readable coverage summary with missing and unknown citekeys.
    """
    if require not in {"retained", "citable", "must_cite"}:
        raise ValueError("require must be one of: retained, citable, must_cite")
    if manuscript_path is None:
        manuscript_path = ws_dir / "final.md"
    if not manuscript_path.exists():
        raise FileNotFoundError(f"缺少稿件文件: {manuscript_path}")

    refmap = _load_reference_map(ws_dir)
    refs = [r for r in refmap["references"] if isinstance(r, dict)]
    by_key = {str(r.get("citekey") or ""): r for r in refs if r.get("citekey")}
    cited = _extract_pandoc_citekeys(manuscript_path.read_text(encoding="utf-8"))

    def is_required(ref: dict[str, Any]) -> bool:
        policy = str(ref.get("citation_policy") or "").strip()
        is_citable = _bibliographic_validity(ref) == "citable"
        if require == "retained":
            return ref.get("status") == "retained"
        if require == "citable":
            return is_citable
        return ref.get("status") == "retained" and is_citable and policy == "must_cite"

    required = [r for r in refs if is_required(r)]
    missing = [r for r in required if str(r.get("citekey") or "") not in cited]
    unknown = sorted(k for k in cited if k not in by_key)

    by_layer: dict[str, dict[str, int]] = {}
    by_policy: dict[str, dict[str, int]] = {}
    by_validity: dict[str, dict[str, int]] = {}
    by_review_use: dict[str, dict[str, int]] = {}
    for ref in refs:
        key = str(ref.get("citekey") or "")
        layer = str(ref.get("corpus_layer") or "unknown")
        policy = str(ref.get("citation_policy") or "unspecified")
        validity = _bibliographic_validity(ref)
        review_use = str(ref.get("review_use") or "unspecified")
        for bucket, name in (
            (by_layer, layer),
            (by_policy, policy),
            (by_validity, validity),
            (by_review_use, review_use),
        ):
            stats = bucket.setdefault(name, {"total": 0, "cited": 0})
            stats["total"] += 1
            if key in cited:
                stats["cited"] += 1

    def compact(ref: dict[str, Any]) -> dict[str, Any]:
        return {
            "citekey": ref.get("citekey", ""),
            "title": ref.get("title", ""),
            "corpus_layer": ref.get("corpus_layer", ""),
            "bibliographic_validity": _bibliographic_validity(ref),
            "review_use": ref.get("review_use", ""),
            "citation_policy": ref.get("citation_policy", ""),
            "evidence_role": ref.get("evidence_role", []),
            "sections": ref.get("sections", []),
        }

    return {
        "workspace": ws_dir.name,
        "manuscript": str(manuscript_path),
        "require": require,
        "reference_count": len(refs),
        "cited_reference_count": len(cited & set(by_key)),
        "required_count": len(required),
        "cited_required_count": len(required) - len(missing),
        "missing_required_count": len(missing),
        "unknown_citekeys": unknown,
        "missing_required": [compact(r) for r in missing],
        "by_layer": by_layer,
        "by_policy": by_policy,
        "by_bibliographic_validity": by_validity,
        "by_review_use": by_review_use,
    }


def _planned_figures(ws_dir: Path) -> list[dict[str, str]]:
    plan_path = ws_dir / "table-figure-plan.md"
    if not plan_path.exists():
        raise FileNotFoundError(f"缺少 table-figure-plan.md: {plan_path}")
    figures: list[dict[str, str]] = []
    in_figures = False
    headers: list[str] = []
    for line in plan_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_figures = stripped.lower() == "## figures"
            headers = []
            continue
        if not in_figures or not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or set(cells[0]) <= {"-", ":"}:
            continue
        if cells[0].lower() in {"figure id", "figure"}:
            headers = cells
            continue
        if not headers or not cells[0].startswith("F"):
            continue
        row = {headers[i]: cells[i] if i < len(cells) else "" for i in range(len(headers))}
        figures.append(
            {
                "figure_id": row.get("Figure ID", cells[0]),
                "title": row.get("Title", ""),
                "status": row.get("Status", ""),
            }
        )
    return figures


def figure_status(ws_dir: Path) -> dict[str, Any]:
    """Check whether planned figures have exported files and manifest rows."""
    planned = _planned_figures(ws_dir)
    figure_dir = ws_dir / "figure"
    manifest_path = figure_dir / "figure-manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"figure-manifest.json 格式损坏: {manifest_path}") from e

    manifest_rows = manifest.get("figures") if isinstance(manifest, dict) else []
    by_id = {
        str(row.get("figure_id") or row.get("id") or ""): row
        for row in manifest_rows or []
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for fig in planned:
        fid = fig["figure_id"]
        manifest_row = by_id.get(fid, {})
        files = manifest_row.get("files") or []
        existing = [str(Path(f)) for f in files if Path(f).exists()]
        if not existing and figure_dir.exists():
            existing = [str(p) for p in sorted(figure_dir.glob(f"{fid}*")) if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".pdf"}]
        complete = bool(existing)
        row = {**fig, "complete": complete, "files": existing, "manifested": fid in by_id}
        rows.append(row)
        if not complete:
            missing.append(row)

    return {
        "workspace": ws_dir.name,
        "planned_count": len(planned),
        "complete_count": len(rows) - len(missing),
        "missing_count": len(missing),
        "manifest": str(manifest_path),
        "figures": rows,
        "missing": missing,
    }


def generate_planning_package(
    ws_dir: Path,
    papers_dir: Path,
    db_path: Path,
    *,
    title: str | None = None,
    criteria: str = "",
) -> dict[str, Any]:
    """Generate a lightweight canonical planning package for a workspace.

    The generated package is intentionally conservative: it creates stable
    identity and evidence files, but does not pretend to replace scholarly
    judgment for section design.
    """
    from autor.export import meta_to_bibtex

    rows = export_evidence(ws_dir, papers_dir, db_path)
    entries: list[str] = []
    citekey_by_dir: dict[str, str] = {}
    for row in rows:
        meta = _read_meta_for_dir(papers_dir, row["dir_name"])
        entry = meta_to_bibtex(meta)
        entries.append(entry)
        match = re.search(r"@\w+\{([^,]+),", entry)
        citekey_by_dir[row["dir_name"]] = match.group(1) if match else row["dir_name"]

    references_bib = "\n\n".join(entries)
    if references_bib:
        references_bib += "\n"
    (ws_dir / "references.bib").write_text(references_bib, encoding="utf-8")

    references = []
    for row in rows:
        references.append(
            {
                "citekey": citekey_by_dir[row["dir_name"]],
                "autor_id": row["id"],
                "dir_name": row["dir_name"],
                "pmid": row.get("pmid", ""),
                "doi": row.get("doi", ""),
                "title": row.get("title", ""),
                "year": str(row.get("year") or ""),
                "paper_type": row.get("paper_type", ""),
                "corpus_layer": "working",
                "status": "retained",
                "evidence_role": ["background"],
                "bibliographic_validity": "citable",
                "review_use": "included_main",
                "citation_policy": "cite_if_relevant",
                "sections": [],
                "full_text_status": row.get("full_text_status", ""),
                "exclusion_reason": "",
                "notes": "",
            }
        )
    refmap = {
        "schema_version": "autor.workflow.reference-map.v2",
        "workspace": ws_dir.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "citation_key_policy": "references.bib keys are canonical in workspace artifacts",
        "valid_reference_policy": (
            "Valid references are bibliographically citable records, including "
            "boundary, conflicting, excluded-but-citable, method, and background uses."
        ),
        "references": references,
        "trials": [],
    }
    (ws_dir / "reference-map.json").write_text(json.dumps(refmap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    review_title = title or f"{ws_dir.name} review planning package"
    (ws_dir / "review-plan.md").write_text(
        "# Review Plan\n\n"
        "## Task Brief\n"
        f"- Workspace: {ws_dir.name}\n"
        f"- Review title: {review_title}\n"
        "- Planning status: REPLAN_REQUIRED\n\n"
        "## Scope and Boundaries\n"
        f"- Screening criteria: {criteria or 'not specified'}\n\n"
        "## Corpus Summary\n"
        f"| Layer | Count | Meaning |\n|---|---:|---|\n| working | {len(rows)} | Retained workspace papers |\n\n"
        "## Handoff\n"
        "- FRAME_STATUS: REPLAN_REQUIRED\n",
        encoding="utf-8",
    )
    (ws_dir / "evidence-ledger.md").write_text(
        "# Evidence Ledger\n\n"
        "## Corpus Layers\n"
        "| Citekey | Layer | Status | Bibliographic validity | Review use | Citation policy | Paper type | Read level | L3 mode | Full-text status |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
        + "".join(
            f"| {citekey_by_dir[r['dir_name']]} | working | retained | citable | included_main | cite_if_relevant | {r.get('paper_type','')} | L2/L3/L4 | {r.get('l3_mode','')} | {r.get('full_text_status','')} |\n"
            for r in rows
        ),
        encoding="utf-8",
    )
    (ws_dir / "table-figure-plan.md").write_text(
        "# Table and Figure Plan\n\n"
        "## Figure Budget\n"
        "- full_review / large_review: plan 7-8 figures unless the target journal forbids it.\n"
        "- mini_review / focused_review: plan 4-5 figures.\n"
        "- Every planned figure requires PlotEnhance before generation and must be listed in figure/figure-manifest.json before export.\n\n"
        "- Figure files must be generated through `autor plot` or `autor.plot.generate_plot()`; manual drawing scripts are not acceptable substitutes.\n\n"
        "## Tables\n"
        "| Table ID | Title | Purpose | Section slot | Required citekeys | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| T1 | Corpus evidence map | Classify retained papers before writing | TBD | TBD | draft |\n\n"
        "## Figures\n"
        "| Figure ID | Title | Type | Section slot | Visual thesis | Source sections | Required citekeys | Trial IDs | PlotEnhance | Status |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
        "| F1 | Review architecture overview | Conceptual overview | TBD | Show the manuscript's central argument in one visual scaffold | TBD | TBD | none | required | draft |\n",
        encoding="utf-8",
    )
    return {
        "workspace": ws_dir.name,
        "count": len(rows),
        "files": [
            str(ws_dir / "references.bib"),
            str(ws_dir / "reference-map.json"),
            str(ws_dir / "review-plan.md"),
            str(ws_dir / "evidence-ledger.md"),
            str(ws_dir / "table-figure-plan.md"),
        ],
    }


def citation_network(ws_dir: Path, db_path: Path, *, min_shared: int = 2) -> dict[str, Any]:
    """Build a workspace-scoped citation-network summary from ``index.db``."""
    import sqlite3

    ids = sorted(read_paper_ids(ws_dir))
    citekey_by_id: dict[str, str] = {}
    refmap_path = ws_dir / "reference-map.json"
    if refmap_path.exists():
        try:
            refmap = json.loads(refmap_path.read_text(encoding="utf-8"))
            for ref in refmap.get("references", []):
                if isinstance(ref, dict) and ref.get("autor_id") and ref.get("citekey"):
                    citekey_by_id[str(ref["autor_id"])] = str(ref["citekey"])
        except json.JSONDecodeError:
            pass

    payload: dict[str, Any] = {
        "schema_version": "autor.workflow.citation-network.v1",
        "workspace": ws_dir.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_shared": min_shared,
        "paper_count": len(ids),
        "status": "blocked",
        "summary": {
            "reference_edge_count": 0,
            "internal_edge_count": 0,
            "sources_with_references": 0,
            "sources_without_references": len(ids),
            "shared_reference_count": 0,
        },
        "sources": [],
        "internal_edges": [],
        "shared_references": [],
    }
    if not ids or not db_path.exists():
        return payload

    placeholders = ",".join("?" for _ in ids)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        has_citations = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='citations'"
        ).fetchone()
        has_registry = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='papers_registry'"
        ).fetchone()
        if not has_citations or not has_registry:
            payload["error"] = "citations or papers_registry table missing; run autor index --rebuild"
            return payload

        registry_rows = conn.execute(
            f"SELECT id, dir_name, title, year, doi, first_author FROM papers_registry WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        registry = {row["id"]: dict(row) for row in registry_rows}

        count_rows = conn.execute(
            f"""SELECT source_id,
                       COUNT(*) AS reference_count,
                       SUM(CASE WHEN target_id IN ({placeholders}) THEN 1 ELSE 0 END) AS internal_reference_count
                FROM citations
                WHERE source_id IN ({placeholders})
                GROUP BY source_id""",
            [*ids, *ids],
        ).fetchall()
        counts = {row["source_id"]: dict(row) for row in count_rows}
        sources = []
        for paper_id in ids:
            reg = registry.get(paper_id, {})
            c = counts.get(paper_id, {})
            reference_count = int(c.get("reference_count") or 0)
            sources.append(
                {
                    "paper_id": paper_id,
                    "citekey": citekey_by_id.get(paper_id, ""),
                    "dir_name": reg.get("dir_name", ""),
                    "title": reg.get("title", ""),
                    "year": reg.get("year", ""),
                    "doi": reg.get("doi", ""),
                    "reference_count": reference_count,
                    "internal_reference_count": int(c.get("internal_reference_count") or 0),
                    "has_references": reference_count > 0,
                }
            )

        internal_rows = conn.execute(
            f"""SELECT c.source_id, c.target_id, c.target_doi,
                       sr.dir_name AS source_dir, sr.title AS source_title,
                       tr.dir_name AS target_dir, tr.title AS target_title
                FROM citations c
                LEFT JOIN papers_registry sr ON sr.id = c.source_id
                LEFT JOIN papers_registry tr ON tr.id = c.target_id
                WHERE c.source_id IN ({placeholders}) AND c.target_id IN ({placeholders})
                ORDER BY source_dir, target_dir""",
            [*ids, *ids],
        ).fetchall()
        internal_edges = [
            {
                "source_id": row["source_id"],
                "source_citekey": citekey_by_id.get(row["source_id"], ""),
                "source_dir": row["source_dir"],
                "source_title": row["source_title"],
                "target_id": row["target_id"],
                "target_citekey": citekey_by_id.get(row["target_id"], ""),
                "target_dir": row["target_dir"],
                "target_title": row["target_title"],
                "target_doi": row["target_doi"],
            }
            for row in internal_rows
        ]

        shared_rows = conn.execute(
            f"""SELECT LOWER(c.target_doi) AS target_doi,
                       COUNT(DISTINCT c.source_id) AS shared_count,
                       GROUP_CONCAT(DISTINCT c.source_id) AS source_ids,
                       c.target_id,
                       pr.dir_name, pr.title, pr.year
                FROM citations c
                LEFT JOIN papers_registry pr ON c.target_id = pr.id
                WHERE c.source_id IN ({placeholders})
                GROUP BY LOWER(c.target_doi)
                HAVING shared_count >= ?
                ORDER BY shared_count DESC, target_doi""",
            [*ids, min_shared],
        ).fetchall()
        shared_references = []
        for row in shared_rows:
            source_ids = [s for s in str(row["source_ids"] or "").split(",") if s]
            shared_references.append(
                {
                    "target_doi": row["target_doi"],
                    "shared_count": row["shared_count"],
                    "source_ids": source_ids,
                    "source_citekeys": [citekey_by_id.get(s, "") for s in source_ids],
                    "target_id": row["target_id"],
                    "target_citekey": citekey_by_id.get(row["target_id"], "") if row["target_id"] else "",
                    "dir_name": row["dir_name"],
                    "title": row["title"],
                    "year": row["year"],
                }
            )

    reference_edge_count = sum(s["reference_count"] for s in sources)
    payload["sources"] = sources
    payload["internal_edges"] = internal_edges
    payload["shared_references"] = shared_references
    payload["summary"] = {
        "reference_edge_count": reference_edge_count,
        "internal_edge_count": len(internal_edges),
        "sources_with_references": sum(1 for s in sources if s["has_references"]),
        "sources_without_references": sum(1 for s in sources if not s["has_references"]),
        "shared_reference_count": len(shared_references),
    }
    payload["status"] = "completed" if reference_edge_count else "blocked"
    return payload


def dump_metadata(rows: list[dict], *, fmt: str = "json") -> str:
    """序列化工作区元信息导出内容。"""
    fmt = (fmt or "json").lower()
    if fmt == "json":
        return json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
    if fmt == "jsonl":
        return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    if fmt == "csv":
        import io

        fieldnames = [
            "id",
            "dir_name",
            "title",
            "authors",
            "year",
            "journal",
            "paper_type",
            "doi",
            "pmid",
            "publication_number",
            "added_at",
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row["authors"] = "; ".join(csv_row.get("authors") or [])
            writer.writerow(csv_row)
        return buf.getvalue()
    raise ValueError(f"不支持的导出格式: {fmt}")
