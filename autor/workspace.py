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
