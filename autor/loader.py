"""
loader.py — 分层内容加载 + TOC 提取 + L3 结论层提取
====================================================

L1: title / authors / year / journal / doi  ← JSON 字段
L2: abstract                                ← JSON 字段
L3: paper-level takeaway                    ← JSON 字段（需先运行 enrich_l3 提取）
L4: full markdown                           ← 读 .md 文件

TOC 提取（enrich_toc）
-----------------------
1. regex 提取所有 # 标题 + 行号
2. LLM 过滤 noise（author running headers、期刊名、论文标题重复等），
   并为每个真实节标题分配层级（level）
3. 写入 JSON["toc"]：[{"line": N, "level": N, "title": "..."}]

L3 提取（enrich_l3）
---------------------
L3 是论文级结论层，而不只是原文 Conclusion section。
若 JSON 已有 TOC，直接从中定位结论节（跳过第一次 LLM 调用）。
否则走 Primary path：LLM 从原始标题列表选出结论节 → Python 截取 → LLM 校验。
Fallback path：LLM 直接给出起止行号 → Python 截取 → LLM 校验。
若没有明确结论节，走 synthesis path：从摘要、结果、讨论、图表标题等候选源生成
受证据约束的 L3 结论卡片。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autor.config import Config

_log = logging.getLogger(__name__)

# Paper types for which L3 generation is skipped.
# These long-form or non-article documents don't have a standard
# article structure suitable for the current L3 strategy.
L3_SKIP_TYPES = frozenset(
    {
        "thesis",
        "dissertation",
        "book",
        "monograph",
        "edited-book",
        "reference-book",
        "book-chapter",
        "book-section",
        "book-part",
        "document",
        "technical-report",
        "lecture-notes",
        "patent",
    }
)


@dataclass(frozen=True)
class L3AttemptResult:
    """Structured outcome for a single L3 extraction path."""

    success: bool
    status: str
    stage: str
    reason: str
    conclusion: str | None = None
    method: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    record: dict[str, Any] | None = None


@dataclass(frozen=True)
class L3ValidationResult:
    """Validation result for a candidate conclusion excerpt."""

    status: str
    reason: str
    cleaned: str | None = None


_CONCLUSION_TITLE_PATTERNS = (
    "conclusion",
    "conclusions",
    "concluding",
    "concluding remarks",
    "concluding discussion",
    "summary",
    "summary and outlook",
    "summary and perspective",
    "discussion and conclusion",
    "discussion and conclusions",
    "conclusion and outlook",
    "conclusions and outlook",
    "conclusion and perspectives",
    "future directions",
    "future work",
    "outlook",
    "final remarks",
    "closing remarks",
    "closing",
    "结论",
    "总结",
    "结语",
    "小结",
    "讨论与结论",
    "结论与展望",
    "总结与展望",
    "研究结论",
)
_CONCLUSION_KEYWORDS = re.compile(
    "|".join(re.escape(term) for term in sorted(_CONCLUSION_TITLE_PATTERNS, key=len, reverse=True)),
    re.IGNORECASE,
)
_KNOWN_SECTION_TITLES = {
    "abstract",
    "background",
    "introduction",
    "materials and methods",
    "methods",
    "method",
    "results",
    "results and discussion",
    "discussion",
    "discussion and conclusion",
    "discussion and conclusions",
    "conclusion",
    "conclusions",
    "concluding remarks",
    "summary",
    "summary and outlook",
    "outlook",
    "references",
    "bibliography",
    "acknowledgments",
    "acknowledgements",
    "funding",
    "appendix",
    "supplementary information",
    "supplementary material",
    "data availability",
    "author contributions",
    "conflict of interest",
    "declaration of competing interest",
}
_KNOWN_SECTION_TITLES_ZH = {
    "摘要",
    "引言",
    "前言",
    "绪论",
    "方法",
    "材料与方法",
    "结果",
    "讨论",
    "结论",
    "总结",
    "结语",
    "小结",
    "讨论与结论",
    "结论与展望",
    "总结与展望",
    "参考文献",
    "致谢",
    "附录",
}
_HEADING_TYPE_HINTS = {
    "head",
    "heading",
    "header",
    "title",
    "section",
    "chapter",
    "h1",
    "h2",
    "h3",
    "h4",
}
_MAX_PLAIN_HEADING_LEN = 160
_MAX_HEADING_WORDS = 24
_FALLBACK_WINDOW_LINES = 320
_FALLBACK_WINDOW_OVERLAP = 100
_FALLBACK_SCAN_FRACTION = 0.40
_FALLBACK_MAX_WINDOWS = 6
_L3_SCHEMA_VERSION = "autor.l3.v2"
_L3_SOURCE_CHAR_BUDGET = 18000
_L3_SECTION_CHAR_LIMIT = 6000
_NUMERIC_SIGNAL_RE = re.compile(
    r"(?i)(?:\b\d+(?:\.\d+)?\s*(?:%|percent|fold|x|×|mg|µg|μg|ng|kg|ml|mL|"
    r"days?|weeks?|months?|years?|hours?|h|nM|µM|μM|mm|cm|cells?|patients?|mice|samples?)\b|"
    r"\bn\s*=\s*\d+|p\s*[<=>]\s*0?\.\d+|95\s*%\s*CI|HR\s*[=:]\s*\d|ORR|PFS|OS|CRS)"
)
_LIMITATION_RE = re.compile(
    r"(?i)\b(limitation|limited|however|although|caution|future|unclear|small sample|"
    r"retrospective|prospective|not yet|further|warranted)\b|"
    r"(局限|不足|然而|未来|尚不|不能|仍需|有待|样本量)"
)


# ============================================================================
#  Public load functions (L1–L4)
# ============================================================================


def load_l1(json_path: Path) -> dict:
    """加载 L1 层元数据（标题、作者、年份、期刊、DOI）。

    Args:
        json_path: 论文 JSON 元数据文件路径。

    Returns:
        包含 ``paper_id``, ``title``, ``authors``, ``year``,
        ``journal``, ``doi`` 的字典。
    """
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return {
        "paper_id": data.get("id") or json_path.parent.name,
        "title": data.get("title") or "",
        "authors": data.get("authors") or [],
        "year": data.get("year"),
        "journal": data.get("journal") or "",
        "doi": data.get("doi") or "",
        "paper_type": data.get("paper_type") or "",
        "citation_count": data.get("citation_count") or {},
        "ids": data.get("ids") or {},
    }


def load_l2(json_path: Path) -> str:
    """加载 L2 层摘要文本。

    Args:
        json_path: 论文 JSON 元数据文件路径。

    Returns:
        摘要文本，无摘要时返回 ``"[No abstract available]"``。
    """
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return data.get("abstract") or "[No abstract available]"


def load_l3(json_path: Path) -> str | None:
    """加载 L3 层结论卡片的可读文本。

    需先运行 :func:`enrich_l3` 提取或综合 L3 到 JSON。

    Args:
        json_path: 论文 JSON 元数据文件路径。

    Returns:
        L3 可读文本，尚未提取时返回 ``None``。
    """
    data = json.loads(json_path.read_text(encoding="utf-8"))
    record = data.get("l3")
    if isinstance(record, dict):
        return _render_l3_record(record)
    return None


def load_l3_record(json_path: Path) -> dict | None:
    """加载结构化 L3 记录。"""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    record = data.get("l3")
    if isinstance(record, dict):
        return record
    return None


def load_l4(md_path: Path) -> str:
    """加载 L4 层全文 Markdown。

    Args:
        md_path: MinerU 输出的 ``.md`` 文件路径。

    Returns:
        完整 Markdown 文本。
    """
    return md_path.read_text(encoding="utf-8", errors="replace")


# ============================================================================
#  Markdown chunking
# ============================================================================


@dataclass(frozen=True)
class MarkdownChunk:
    """A section-aware markdown chunk used for node-level retrieval.

    Attributes:
        section: The logical section label for the chunk.
        content: Prefixed chunk text stored in the evidence index.
    """

    section: str
    content: str


def chunk_markdown_text(
    markdown: str,
    *,
    title: str = "",
    max_chars: int = 800,
    overlap_chars: int = 100,
) -> list[MarkdownChunk]:
    """Split full-text markdown into section-aware overlapping chunks.

    Splitting is driven first by level-2 headings (``##``). Each section is
    then broken into paragraph-aware windows with a character overlap to avoid
    sharp semantic cuts near chunk boundaries.

    Args:
        markdown: Full markdown text, typically from :func:`load_l4`.
        title: Paper title used in the chunk prefix. When omitted, attempts to
            infer it from the first level-1 heading.
        max_chars: Maximum approximate body length per chunk.
        overlap_chars: Desired overlap between adjacent chunks in the same
            section.

    Returns:
        List of prefixed :class:`MarkdownChunk` objects.
    """
    text = markdown.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be non-negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    resolved_title = title.strip() or _infer_markdown_title(text)
    sections = _split_markdown_sections(text)
    chunks: list[MarkdownChunk] = []

    for section_title, section_text in sections:
        section_body = section_text.strip()
        if not section_body:
            continue
        bodies = _chunk_section_body(section_body, max_chars=max_chars, overlap_chars=overlap_chars)
        for body in bodies:
            prefix = f"Title: {resolved_title}\nSection: {section_title}\n"
            chunks.append(MarkdownChunk(section=section_title, content=prefix + body))

    return chunks


def _infer_markdown_title(markdown: str) -> str:
    m = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
    if m:
        return _normalize_chunk_text(m.group(1))
    return "Untitled"


def _split_markdown_sections(markdown: str) -> list[tuple[str, str]]:
    lines = markdown.splitlines()
    sections: list[tuple[str, str]] = []
    current_title = "Document"
    current_lines: list[str] = []
    seen_content = False

    for raw_line in lines:
        line = raw_line.rstrip()
        if not seen_content and not line.strip():
            continue
        if not seen_content and re.match(r"^#\s+", line):
            seen_content = True
            continue
        seen_content = True

        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = _normalize_chunk_text(m.group(1)) or "Document"
            current_lines = []
            continue
        current_lines.append(line)

    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return sections or [("Document", markdown)]


def _chunk_section_body(section_text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    paragraphs = [_normalize_chunk_text(p) for p in re.split(r"\n\s*\n+", section_text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_slice_with_overlap(paragraph, max_chars=max_chars, overlap_chars=overlap_chars))
            continue

        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue

        chunks.append(current)
        overlap = _extract_overlap(current, overlap_chars)
        current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph
        if len(current) > max_chars:
            chunks.extend(_slice_with_overlap(current, max_chars=max_chars, overlap_chars=overlap_chars))
            current = ""

    if current:
        chunks.append(current)

    return chunks


def _slice_with_overlap(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            soft_end = _retreat_to_boundary(text, end, max(start + max_chars // 2, start + 1))
            if soft_end > start:
                end = soft_end

        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= n:
            break

        next_start = max(0, end - overlap_chars)
        if next_start <= start:
            next_start = end
        else:
            next_start = _retreat_to_boundary(text, next_start, start + 1)
        start = next_start

    return pieces


def _extract_overlap(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or len(text) <= overlap_chars:
        return text.strip()
    start = len(text) - overlap_chars
    start = _retreat_to_boundary(text, start, 0)
    return text[start:].strip()


def _retreat_to_boundary(text: str, pos: int, floor: int) -> int:
    while pos > floor and not text[pos - 1].isspace():
        pos -= 1
    return pos


def _normalize_chunk_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ============================================================================
#  Agent notes (T2 persistent analysis notes)
# ============================================================================

_NOTES_FILENAME = "notes.md"


def load_notes(paper_dir: Path) -> str | None:
    """加载论文的 agent 分析笔记。

    笔记文件 (``notes.md``) 由 agent 在分析论文时自动创建和追加，
    用于跨会话、跨工作区复用分析结论。

    Args:
        paper_dir: 论文目录路径（包含 ``meta.json`` 的目录）。

    Returns:
        笔记文本，不存在时返回 ``None``。
    """
    notes_path = paper_dir / _NOTES_FILENAME
    if notes_path.exists():
        text = notes_path.read_text(encoding="utf-8")
        if not text.strip():
            return None
        return text
    return None


def append_notes(paper_dir: Path, section: str) -> None:
    """向论文笔记文件追加一条分析记录。

    如果 ``notes.md`` 不存在则创建。每条记录之间用空行分隔。

    Args:
        paper_dir: 论文目录路径。
        section: 要追加的笔记内容（Markdown 格式，建议以 ``## 日期 | 来源`` 开头）。
    """
    notes_path = paper_dir / _NOTES_FILENAME
    section = section.rstrip("\n")
    if notes_path.exists():
        # Only add enough newlines to get exactly one blank line separator
        tail = b""
        try:
            with open(notes_path, "rb") as f:
                f.seek(0, 2)
                pos = f.tell()
                n = min(pos, 4)
                f.seek(pos - n)
                tail = f.read(n)
        except OSError:
            pass
        trailing = 0
        for i in range(len(tail) - 1, -1, -1):
            if tail[i : i + 1] == b"\n":
                trailing += 1
            else:
                break
        prefix = "\n" * max(0, 2 - trailing)
        with open(notes_path, "a", encoding="utf-8") as f:
            f.write(prefix + section + "\n")
    else:
        notes_path.write_text(section + "\n", encoding="utf-8")
    _log.debug("appended notes to %s", notes_path)


# ============================================================================
#  L3 helpers
# ============================================================================


def _ok(
    stage: str,
    method: str,
    conclusion: str,
    *,
    reason: str = "",
    start_line: int | None = None,
    end_line: int | None = None,
    record: dict[str, Any] | None = None,
) -> L3AttemptResult:
    return L3AttemptResult(
        success=True,
        status="ok",
        stage=stage,
        reason=reason or "提取成功",
        conclusion=conclusion,
        method=method,
        start_line=start_line,
        end_line=end_line,
        record=record,
    )


def _fail(
    stage: str,
    status: str,
    reason: str,
    *,
    method: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> L3AttemptResult:
    return L3AttemptResult(
        success=False,
        status=status,
        stage=stage,
        reason=reason,
        method=method,
        start_line=start_line,
        end_line=end_line,
    )


def _write_l3_attempt_metadata(data: dict, result: L3AttemptResult) -> None:
    """Persist the latest L3 extraction attempt outcome into metadata."""
    data["l3_last_attempt_status"] = result.status
    data["l3_last_attempt_stage"] = result.stage
    data["l3_last_attempt_reason"] = result.reason
    data["l3_last_attempt_method"] = result.method or result.stage
    data["l3_last_attempt_at"] = datetime.now().isoformat(timespec="seconds")
    if result.start_line is not None:
        data["l3_last_attempt_start_line"] = result.start_line
    else:
        data.pop("l3_last_attempt_start_line", None)
    if result.end_line is not None:
        data["l3_last_attempt_end_line"] = result.end_line
    else:
        data.pop("l3_last_attempt_end_line", None)


def _select_l3_failure(attempts: list[L3AttemptResult], *, header_count: int) -> L3AttemptResult:
    """Choose the most informative final failure from attempted paths."""
    if not attempts:
        return _fail("extract", "bad_structure", "未执行任何 L3 提取路径")

    if header_count <= 1 and all(a.status in {"no_conclusion", "bad_structure", "no_sources"} for a in attempts):
        return _fail("primary", "bad_structure", f"正文结构不足：仅检测到 {header_count} 个候选节标题")

    for status in ("validation_reject", "llm_error", "too_short", "bad_structure", "no_sources", "no_conclusion"):
        for attempt in reversed(attempts):
            if attempt.status == status:
                return attempt

    return attempts[-1]


def _build_l3_record(
    *,
    mode: str,
    confidence: str,
    takeaway: str,
    method: str,
    source_spans: list[dict[str, Any]] | None = None,
    key_findings: list[dict[str, Any]] | None = None,
    quantitative_signals: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
    warnings: list[str] | None = None,
    source_excerpt: str | None = None,
) -> dict[str, Any]:
    """Build the canonical L3 v2 record."""
    safe_confidence = confidence if confidence in {"high", "medium", "low", "unknown"} else "medium"
    return {
        "schema_version": _L3_SCHEMA_VERSION,
        "mode": mode,
        "confidence": safe_confidence,
        "method": method,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "takeaway": takeaway.strip(),
        "key_findings": key_findings or [],
        "quantitative_signals": quantitative_signals or [],
        "limitations": limitations or [],
        "warnings": warnings or [],
        "source_spans": source_spans or [],
        "source_excerpt": source_excerpt or "",
    }


def _record_from_explicit_result(result: L3AttemptResult) -> dict[str, Any]:
    text = (result.conclusion or "").strip()
    source = {
        "source": "conclusion",
        "method": result.method or result.stage,
        "start_line": result.start_line,
        "end_line": result.end_line,
    }
    confidence = "high" if result.stage == "toc" else "medium"
    return _build_l3_record(
        mode="explicit_section",
        confidence=confidence,
        takeaway=text,
        method=result.method or result.stage,
        source_spans=[source],
        quantitative_signals=_extract_quantitative_signals(text, source="conclusion"),
        limitations=_extract_limitations(text),
        warnings=[] if result.stage in {"toc", "primary"} else ["conclusion_found_by_fallback_window"],
        source_excerpt=text,
    )


def _augment_explicit_l3_record(record: dict[str, Any], data: dict[str, Any], lines: list[str]) -> dict[str, Any]:
    """Supplement explicit conclusions with dense signals from nearby paper-level sources."""
    existing_quant = record.get("quantitative_signals")
    if not isinstance(existing_quant, list):
        existing_quant = []
    existing_limitations = record.get("limitations")
    if not isinstance(existing_limitations, list):
        existing_limitations = []

    sources = _collect_l3_synthesis_sources(data, lines)
    added_quant: list[dict[str, Any]] = []
    added_limits: list[str] = []
    seen_quant = {str(item.get("text") if isinstance(item, dict) else item).casefold() for item in existing_quant}
    seen_limits = {str(item).casefold() for item in existing_limitations}

    for source in sources:
        for item in _extract_quantitative_signals(source["text"], source=source["source"], limit=4):
            key = item["text"].casefold()
            if key in seen_quant:
                continue
            seen_quant.add(key)
            added_quant.append(item)
            if len(existing_quant) + len(added_quant) >= 10:
                break
        for item in _extract_limitations(source["text"], limit=3):
            key = item.casefold()
            if key in seen_limits:
                continue
            seen_limits.add(key)
            added_limits.append(item)
            if len(existing_limitations) + len(added_limits) >= 6:
                break
        if len(existing_quant) + len(added_quant) >= 10 and len(existing_limitations) + len(added_limits) >= 6:
            break

    if not added_quant and not added_limits:
        return record

    augmented = dict(record)
    augmented["mode"] = "hybrid"
    augmented["quantitative_signals"] = (existing_quant + added_quant)[:10]
    augmented["limitations"] = (existing_limitations + added_limits)[:6]
    warnings = list(augmented.get("warnings") if isinstance(augmented.get("warnings"), list) else [])
    warnings.append("explicit_conclusion_supplemented_with_result_bearing_sources")
    augmented["warnings"] = list(dict.fromkeys(str(w) for w in warnings if str(w).strip()))

    source_spans = list(augmented.get("source_spans") if isinstance(augmented.get("source_spans"), list) else [])
    for source in sources:
        if source.get("start_line") is None:
            continue
        source_spans.append(
            {
                "source": source["source"],
                "start_line": source.get("start_line"),
                "end_line": source.get("end_line"),
            }
        )
    augmented["source_spans"] = source_spans[:12]
    return augmented


def _render_l3_record(record: dict[str, Any]) -> str | None:
    """Render a structured L3 record as human-readable text."""
    takeaway = record.get("takeaway")
    if not isinstance(takeaway, str) or not takeaway.strip():
        return None

    findings = record.get("key_findings") if isinstance(record.get("key_findings"), list) else []
    quantitative = record.get("quantitative_signals") if isinstance(record.get("quantitative_signals"), list) else []
    limitations = record.get("limitations") if isinstance(record.get("limitations"), list) else []
    warnings = record.get("warnings") if isinstance(record.get("warnings"), list) else []

    # Keep old explicit-section displays uncluttered when no richer fields exist.
    if record.get("mode") == "explicit_section" and not findings and not quantitative and not limitations and not warnings:
        return takeaway.strip()

    parts = [f"Mode: {record.get('mode', 'unknown')} | Confidence: {record.get('confidence', 'unknown')}", ""]
    parts.extend(["Takeaway:", takeaway.strip()])

    if findings:
        parts.extend(["", "Key findings:"])
        for item in findings:
            if isinstance(item, dict):
                claim = str(item.get("claim") or item.get("text") or "").strip()
                basis = str(item.get("evidence_basis") or item.get("source") or "").strip()
                if claim:
                    suffix = f" ({basis})" if basis else ""
                    parts.append(f"- {claim}{suffix}")
            elif str(item).strip():
                parts.append(f"- {str(item).strip()}")

    if quantitative:
        parts.extend(["", "Quantitative signals:"])
        for item in quantitative:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("value") or item.get("metric") or "").strip()
                source = str(item.get("source") or "").strip()
                if text:
                    suffix = f" [{source}]" if source else ""
                    parts.append(f"- {text}{suffix}")
            elif str(item).strip():
                parts.append(f"- {str(item).strip()}")

    if limitations:
        parts.extend(["", "Limitations / boundaries:"])
        for item in limitations:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("limitation") or "").strip()
            else:
                text = str(item).strip()
            if text:
                parts.append(f"- {text}")

    if warnings:
        parts.extend(["", "Warnings:"])
        for item in warnings:
            text = str(item).strip()
            if text:
                parts.append(f"- {text}")

    return "\n".join(parts).strip()


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+", normalized) if s.strip()]


def _extract_quantitative_signals(text: str, *, source: str, limit: int = 8) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    seen: set[str] = set()
    for sentence in _split_sentences(text):
        if not _NUMERIC_SIGNAL_RE.search(sentence):
            continue
        compact = sentence[:500].strip()
        key = compact.casefold()
        if key in seen:
            continue
        seen.add(key)
        signals.append({"text": compact, "source": source})
        if len(signals) >= limit:
            break
    return signals


def _extract_limitations(text: str, *, limit: int = 5) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for sentence in _split_sentences(text):
        if not _LIMITATION_RE.search(sentence):
            continue
        compact = sentence[:500].strip()
        key = compact.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(compact)
        if len(items) >= limit:
            break
    return items


# ============================================================================
#  TOC extraction
# ============================================================================


def enrich_toc(
    json_path: Path,
    md_path: Path,
    config: Config,
    *,
    force: bool = False,
    inspect: bool = False,
) -> bool:
    """用 LLM 提取论文目录结构，写入 ``JSON["toc"]``。

    从 Markdown 中提取所有 ``#`` 标题，通过 LLM 过滤 running headers、
    期刊名、作者名等噪声，为真实节标题分配层级。

    Args:
        json_path: 论文 JSON 元数据文件路径（结果写回此文件）。
        md_path: 论文 Markdown 文件路径。
        config: 全局配置（用于 LLM 调用）。
        force: 为 ``True`` 时覆盖已有 TOC。
        inspect: 为 ``True`` 时打印过滤过程详情。

    Returns:
        提取成功返回 ``True``，失败返回 ``False``。
    """
    from autor.papers import read_meta, write_meta

    paper_d = json_path.parent
    data = read_meta(paper_d)

    if data.get("toc") and not force:
        _log.debug("existing TOC (%d entries), skipping", len(data["toc"]))
        return True

    lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()
    raw_headers = _extract_headers(lines, md_path=md_path)

    _log.debug("header extractor found %d candidates", len(raw_headers))

    # Threshold: if many headers, rules are more reliable than LLM
    # (LLM struggles to output 100+ JSON entries without format errors)
    _RULE_THRESHOLD = 80

    title = data.get("title", "")
    toc: list[dict] | None = None

    if len(raw_headers) >= _RULE_THRESHOLD:
        _log.debug("header count %d >= %d, using rule-based extraction", len(raw_headers), _RULE_THRESHOLD)
        toc = _toc_from_rules(raw_headers, title)
        if toc:
            _log.debug("rule-based extraction: %d entries", len(toc))

    if toc is None:
        # LLM path for normal papers
        _log.debug("sending %d heading candidates to LLM", len(raw_headers))
        prompt = (
            "The following are ALL heading candidates extracted from an academic paper "
            "markdown file (and optional MinerU structure artifacts). Some are real section headers; "
            "others are NOISE to discard: author running headers (e.g. '# Smith and others'), "
            "journal name headers (e.g. '# Journal of Fluid Mechanics'), repeated paper titles, "
            "or publisher metadata (e.g. '# ARTICLEINFO', '# AFFILIATIONS', '# Articles You May Be Interested In').\n\n"
            "KEEP the following as real headers (they are needed as section boundary markers):\n"
            "- Numbered/lettered sections and subsections\n"
            "- Introduction, Abstract, Conclusion, Conclusions, Concluding Remarks, Summary\n"
            "- References, Bibliography\n"
            "- Appendix (any variant)\n"
            "- Post-matter sections: Acknowledgments, Acknowledgements, Funding, "
            "CRediT authorship contribution statement, Declaration of competing interest, "
            "Conflict of interest, Data availability, Author contributions, Author ORCIDs, "
            "Declaration of interests\n\n"
            "Assign level: 1=top-level, 2=subsection (e.g. '2.1'), 3=sub-subsection (e.g. '2.1.1').\n\n"
            "Headers:\n"
            + "\n".join(f"Line {h['line']}: {'#' * h['level']} {h['text']}" for h in raw_headers)
            + "\n\nReturn JSON only:\n"
            '{"toc": [{"line": <N>, "level": <1|2|3>, "title": "<title>"}, ...]}'
        )

        try:
            result = _parse_json(_call_llm(prompt, config, timeout=config.llm.timeout_toc))
            toc = result.get("toc") or []
        except Exception as e:
            _log.error("TOC extraction failed: %s", e)
            # fallback: try rules even for small docs
            toc = _toc_from_rules(raw_headers, title)

    if not toc:
        _log.error("could not extract TOC (both rules and LLM failed)")
        return False

    _log.debug("final TOC: %d entries", len(toc))
    for entry in toc:
        indent = "  " * (entry.get("level", 1) - 1)
        _log.debug("  line %4d  %s%s", entry["line"], indent, entry["title"])

    data["toc"] = toc
    data["toc_extracted_at"] = datetime.now().isoformat(timespec="seconds")
    write_meta(paper_d, data)
    _log.debug("TOC written to JSON")
    return True


# ============================================================================
#  L3 generation entry point
# ============================================================================


def enrich_l3(
    json_path: Path,
    md_path: Path,
    config: Config,
    *,
    force: bool = False,
    max_retries: int = 2,
    inspect: bool = False,
) -> bool:
    """用 LLM 生成论文级 L3 结论卡片，写入 ``JSON["l3"]``。

    提取策略（按优先级）:
      1. 从已有 TOC 定位结论节 → Python 截取 → LLM 校验清洗
      2. Primary path: LLM 从标题列表选出结论节 → 截取 → 校验
      3. Fallback path: LLM 直接给出起止行号 → 截取 → 校验

    Args:
        json_path: 论文 JSON 元数据文件路径（结果写回此文件）。
        md_path: 论文 Markdown 文件路径。
        config: 全局配置（用于 LLM 调用）。
        force: 为 ``True`` 时覆盖已有结论。
        max_retries: 每条路径的最大重试次数。
        inspect: 为 ``True`` 时打印提取过程详情。

    Returns:
        提取成功返回 ``True``，失败返回 ``False``。
    """
    from autor.papers import read_meta, write_meta

    paper_d = json_path.parent
    data = read_meta(paper_d)

    # Skip L3 for non-article types (thesis, book, document, etc.)
    paper_type = (data.get("paper_type") or "").lower().strip()
    if paper_type in L3_SKIP_TYPES:
        if data.get("l3_extraction_method") == "skipped":
            return True  # already marked, idempotent
        _log.debug("skipping L3 for paper_type=%s: %s", paper_type, paper_d.name)
        data["l3"] = _build_l3_record(
            mode="skipped",
            confidence="unknown",
            takeaway="",
            method="skipped",
            warnings=[f"paper_type={paper_type}"],
        )
        data["l3_extraction_method"] = "skipped"
        data["l3_extracted_at"] = datetime.now().isoformat(timespec="seconds")
        _write_l3_attempt_metadata(
            data,
            L3AttemptResult(
                success=True,
                status="skipped",
                stage="skip",
                reason=f"paper_type={paper_type}",
                method="skipped",
            ),
        )
        write_meta(paper_d, data)
        return True

    if data.get("l3") and not force:
        _log.debug("existing L3 (method: %s), skipping", data.get("l3_extraction_method", "?"))
        return True

    lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()

    conclusion_result: L3AttemptResult | None = None
    attempts: list[L3AttemptResult] = []
    headers: list[dict] = []

    # --- Try locating conclusion via existing TOC (skip first LLM call) ---
    toc = data.get("toc")
    if not toc:
        _log.debug("[TOC] missing TOC, attempting automatic TOC extraction before L3")
        if enrich_toc(json_path, md_path, config, force=False, inspect=inspect):
            data = read_meta(paper_d)
            toc = data.get("toc")

    if toc:
        toc_result = _l3_from_toc(lines, toc, config, max_retries, inspect)
        attempts.append(toc_result)
        if toc_result.success:
            conclusion_result = toc_result

    # --- Primary path (when TOC is unavailable) ---
    if conclusion_result is None:
        headers = _extract_headers(lines, md_path=md_path)
        _log.debug("[Primary] found %d headers", len(headers))
        for h in headers:
            _log.debug(
                "  line %4d  %s %s [%s]",
                h["line"],
                "#" * h["level"],
                h["text"],
                h.get("source", "?"),
            )
        if headers:
            primary_result = _primary_path(lines, headers, config, max_retries, inspect)
        else:
            primary_result = _fail("primary", "bad_structure", "未识别到可用节标题", method="primary")
        attempts.append(primary_result)
        if primary_result.success:
            conclusion_result = primary_result

    # --- Fallback path ---
    if conclusion_result is None:
        _log.debug("[Fallback] Primary path failed, switching to fallback")
        fallback_result = _fallback_path(lines, config, max_retries, inspect)
        attempts.append(fallback_result)
        if fallback_result.success:
            conclusion_result = fallback_result

    # --- Synthesis path for papers without explicit conclusion sections ---
    if conclusion_result is None:
        _log.debug("[Synthesis] explicit conclusion paths failed, attempting paper-level L3 synthesis")
        synthesis_result = _synthesis_path(data, lines, config, inspect)
        attempts.append(synthesis_result)
        if synthesis_result.success:
            conclusion_result = synthesis_result

    if conclusion_result is None:
        failure = _select_l3_failure(attempts, header_count=len(headers))
        _write_l3_attempt_metadata(data, failure)
        write_meta(paper_d, data)
        _log.error("all paths failed to generate L3 (%s/%s): %s", failure.stage, failure.status, failure.reason)
        return False

    record = conclusion_result.record or _record_from_explicit_result(conclusion_result)
    if record.get("mode") == "explicit_section":
        record = _augment_explicit_l3_record(record, data, lines)
    data["l3"] = record
    data["l3_extraction_method"] = conclusion_result.method
    data["l3_extracted_at"] = datetime.now().isoformat(timespec="seconds")
    _write_l3_attempt_metadata(data, conclusion_result)
    write_meta(paper_d, data)
    _log.debug(
        "L3 written to JSON (method: %s, %d chars)",
        conclusion_result.method,
        len(conclusion_result.conclusion or ""),
    )
    return True


# ============================================================================
#  L3 from TOC (no extra LLM call for header identification)
# ============================================================================

def _l3_from_toc(
    lines: list[str],
    toc: list[dict],
    config: Config,
    max_retries: int,
    inspect: bool,
) -> L3AttemptResult:
    """用已有 TOC 定位结论节，Python 截取，LLM 校验。"""
    # Find conclusion entry in TOC
    conclusion_entry = None
    for entry in toc:
        if _is_conclusion_title(entry.get("title", "")):
            conclusion_entry = entry
            break

    if not conclusion_entry:
        _log.debug("[TOC] no conclusion section found in TOC, switching to Primary")
        return _fail("toc", "no_conclusion", "TOC 中未找到结论节标题", method="toc")

    start_line = conclusion_entry["line"]
    _log.debug("[TOC] found conclusion: line %d %s", start_line, conclusion_entry["title"])

    # Find end: next TOC entry after conclusion
    end_line = None
    found = False
    for entry in toc:
        if found:
            end_line = entry["line"] - 1
            break
        if entry["line"] == start_line:
            found = True

    extracted = _slice_lines(lines, start_line, end_line)
    _log.debug("[TOC] extracted lines %d-%s, %d chars", start_line, end_line or "EOF", len(extracted))

    validation = _validate_with_retries(extracted, config, attempts=max_retries + 1)
    _log.debug("[TOC] validate: %s %s", "PASS" if validation.cleaned else "FAIL", validation.reason)
    if validation.cleaned:
        return _ok(
            "toc",
            "toc",
            validation.cleaned,
            reason=validation.reason,
            start_line=start_line,
            end_line=end_line,
        )

    return _fail(
        "toc",
        validation.status,
        validation.reason,
        method="toc",
        start_line=start_line,
        end_line=end_line,
    )


# ============================================================================
#  Primary path
# ============================================================================


_REAL_SECTION_RE = re.compile(
    r"^(?:"
    r"\d[\d.．]*[\s.．]|"  # Arabic numbering: 1, 1.1, 2．, etc.
    r"[IVX]+[\s.)]|"  # 罗马数字: I., II., IV.
    r"[A-F][\s.)]|"  # 字母编号: A., B.
    r"(?:abstract|background|introduction|materials?|methods?|results?|discussion|"
    r"discussion\s+and\s+conclusions?|conclusions?|concluding|summary|outlook|future|"
    r"reference|bibliography|appendix|supplementary|acknowledge|funding|credit|"
    r"declaration|ethics|data\s+avail|author\s+contrib|conflict)\b"
    r")",
    re.IGNORECASE,
)


def _is_real_section(title: str) -> bool:
    """判断标题是否为真实节标题（非 running header）。"""
    stripped = title.strip()
    return bool(_REAL_SECTION_RE.match(stripped)) or _is_known_section_title(stripped)


def _extract_headers(lines: list[str], *, md_path: Path | None = None) -> list[dict]:
    """Collect heading candidates from markdown, plain text, and MinerU assets."""
    groups = [
        _extract_markdown_headers(lines),
        _extract_plaintext_headers(lines),
    ]
    if md_path is not None:
        groups.append(_extract_asset_headers(lines, md_path))

    merged: dict[tuple[int, str], dict[str, Any]] = {}
    priority = {"markdown": 0, "plaintext": 1}
    for headers in groups:
        for header in headers:
            clean_text = _clean_heading_text(header["text"])
            if not clean_text:
                continue
            key = (header["line"], _normalize_heading_text(clean_text))
            current = merged.get(key)
            new_pri = priority.get(header.get("source", ""), 2)
            cur_pri = priority.get(current.get("source", ""), 99) if current else 99
            if current is None or new_pri < cur_pri:
                merged[key] = {
                    "line": header["line"],
                    "level": max(1, min(int(header.get("level", 1)), 3)),
                    "text": clean_text,
                    "source": header.get("source", "unknown"),
                }

    return sorted(merged.values(), key=lambda h: (h["line"], h["level"], h["text"].lower()))


def _extract_markdown_headers(lines: list[str]) -> list[dict]:
    headers = []
    for i, line in enumerate(lines, start=1):
        m = re.match(r"^(#{1,6})\s+(.+)", line.rstrip())
        if m:
            headers.append(
                {
                    "line": i,
                    "level": len(m.group(1)),
                    "text": m.group(2).strip(),
                    "source": "markdown",
                }
            )
    return headers


def _extract_plaintext_headers(lines: list[str]) -> list[dict]:
    headers = []
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not _looks_like_plain_heading(stripped):
            continue
        headers.append(
            {
                "line": i,
                "level": _infer_heading_level(stripped),
                "text": stripped,
                "source": "plaintext",
            }
        )
    return headers


def _extract_asset_headers(lines: list[str], md_path: Path) -> list[dict]:
    headers = []
    normalized_lines = {i: _normalize_heading_text(line) for i, line in enumerate(lines, start=1)}

    for asset_path in _iter_structure_assets(md_path.parent):
        try:
            payload = json.loads(asset_path.read_text(encoding="utf-8"))
        except Exception as e:
            _log.debug("failed to read structure asset %s: %s", asset_path.name, e)
            continue

        for candidate in _iter_structure_heading_candidates(payload):
            text = _clean_heading_text(candidate.get("text", ""))
            if not _looks_like_asset_heading(text, candidate.get("level")):
                continue
            line_no = _locate_heading_line(text, normalized_lines)
            if line_no is None:
                continue
            headers.append(
                {
                    "line": line_no,
                    "level": candidate.get("level") or _infer_heading_level(text),
                    "text": lines[line_no - 1].lstrip("#").strip() or text,
                    "source": asset_path.name,
                }
            )

    return headers


# -- regex-based TOC extraction (no LLM) ------------------------------------

# Numbered section pattern: "1", "1.2", "1.2.3", with optional trailing dot
# Also matches "1.", "2.1.", "1.2.3." (common in some journals/books)
# Allows number followed by space, ASCII letters, or CJK chars.
_RE_NUMBERED = re.compile(r"^(\d+(?:[.．]\d+)*)[.．]?(?:\s+|(?=[A-Za-z\u4e00-\u9fff]))")
_RE_NUMBERED_PREFIX = re.compile(r"^(\d+(?:[.．]\d+)*)[.．]?\s*")
# "Chapter 1 Title" or Chinese "第一章" / "第1章" pattern
_RE_CHAPTER = re.compile(r"^Chapter\s+(\d+)\b", re.IGNORECASE)
_RE_CHAPTER_ZH = re.compile(r"^第\s*([一二三四五六七八九十百\d]+)\s*章")
_RE_ROMAN_PREFIX = re.compile(r"^([IVXLCDM]+)[\s.)]+", re.IGNORECASE)
_RE_LETTER_PREFIX = re.compile(r"^([A-Z])[\s.)]+")
# TOC-area entries have trailing page numbers like "Title 123" or "Title . 123"
# Require >= 2 digits to avoid matching "Chapter 1", "Part 2", etc.
_RE_TRAILING_PAGE = re.compile(r"[.\s]\s*\d{2,4}\s*$")
# Well-known structural sections (unnumbered)
_KNOWN_SECTIONS = _KNOWN_SECTION_TITLES | {"preface", "foreword", "index", "glossary", "nomenclature", "notation"}


def _toc_from_rules(raw_headers: list[dict], title: str) -> list[dict] | None:
    """Try to build TOC purely from rules. Returns list of toc entries or None.

    Strategy:
    1. Detect and skip a TOC area (headers with trailing page numbers).
    2. Filter noise: repeated paper title, author lines, metadata lines.
    3. Infer level from numbering (1 → l1, 1.2 → l2, 1.2.3 → l3).
    4. Keep well-known unnumbered sections as level 1.
    """
    if not raw_headers:
        return None

    # normalised title words for matching
    title_lower = title.lower().strip() if title else ""

    # --- pass 1: skip TOC/front-matter area ---
    # PDF books have a printed table-of-contents with trailing page numbers
    # ("1.2 Title ... 23"), followed by front-matter (preface, notation,
    # etc.) before the real body starts.  We find the last page-number
    # header in the first 10% of lines, then advance past any remaining
    # front-matter until we hit a real body-start marker.
    total_lines = raw_headers[-1]["line"] if raw_headers else 1
    toc_cutoff_line = max(total_lines * 0.10, 500)
    page_indices = [
        idx for idx, h in enumerate(raw_headers) if h["line"] <= toc_cutoff_line and _RE_TRAILING_PAGE.search(h["text"])
    ]
    if len(page_indices) >= 5:
        body_start = page_indices[-1] + 1
    else:
        body_start = 0

    # Advance past remaining front-matter noise until we hit a body-start
    # marker: "Chapter 1", numbered section "1" or "1.1", or known
    # front-matter sections (Preface, Foreword, Introduction, Notation).
    _FRONT_SECTIONS = {
        "preface",
        "foreword",
        "notation",
        "symbols",
        "acknowledgments",
        "acknowledgements",
        "introduction",
    }
    for idx in range(body_start, len(raw_headers)):
        h = raw_headers[idx]
        text = h["text"]
        text_lower = text.lower().strip()
        # "Chapter 1" or "Chapter N" or "第一章"
        if _RE_CHAPTER.match(text) or _RE_CHAPTER_ZH.match(text):
            body_start = idx
            break
        # Numbered section starting from "1" (top-level chapter)
        m = _RE_NUMBERED.match(text)
        if m and m.group(1).split(".")[0] == "1":
            body_start = idx
            break
        # Known front-matter sections that appear before Chapter 1
        if (
            text_lower.split(" to ")[0].strip().rstrip("s")
            in (
                "preface",
                "foreword",
                "notation",
                "symbol",
                "acknowledgment",
                "acknowledgement",
            )
            or text_lower.startswith("preface")
            or text_lower
            in (
                "摘要",
                "前言",
                "序言",
                "绪论",
            )
        ):
            body_start = idx
            break
    body_headers = raw_headers[body_start:]

    if not body_headers:
        body_headers = raw_headers  # fallback: no TOC area detected

    # --- pass 2: detect running headers (appear >= 3 times) ---
    from collections import Counter

    text_counts = Counter(h["text"].lower().strip() for h in body_headers)
    running_headers = {t for t, c in text_counts.items() if c >= 3}

    # --- pass 3: filter noise ---
    toc = []
    for h in body_headers:
        text = h["text"]
        text_lower = text.lower().strip()

        # skip running headers (repeated page headers from PDF)
        if text_lower in running_headers:
            continue

        # skip if it matches the paper/book title
        if title_lower and _similar_title(text_lower, title_lower):
            continue
        # skip common metadata noise
        if text_lower in (
            "contents",
            "table of contents",
            "acronyms",
            "abbreviations",
            "articleinfo",
            "affiliations",
            "目录",
            "插图目录",
            "表格目录",
        ):
            continue

        # --- infer level ---
        m_num = _RE_NUMBERED.match(text)
        m_chap = _RE_CHAPTER.match(text)
        m_chap_zh = _RE_CHAPTER_ZH.match(text)
        if m_chap:
            # "Chapter 3 Title" → level 1, strip "Chapter N" prefix for clean title
            clean = text[m_chap.end() :].strip()
            num = m_chap.group(1)
            final_title = f"{num} {clean}" if clean else f"Chapter {num}"
            toc.append({"line": h["line"], "level": 1, "title": final_title})
        elif m_chap_zh:
            # "第一章 绪论" → level 1, keep original text
            toc.append({"line": h["line"], "level": 1, "title": text})
        elif m_num:
            num_str = m_num.group(1)
            depth = num_str.count(".") + 1  # "1"→1, "1.2"→2, "1.2.3"→3
            level = min(depth, 3)
            # strip trailing page-number-like remnants (shouldn't exist in body, but be safe)
            clean_text = _RE_TRAILING_PAGE.sub("", text).strip().rstrip(".")
            toc.append({"line": h["line"], "level": level, "title": clean_text})
        elif _is_known_section_title(text):
            toc.append({"line": h["line"], "level": 1, "title": text})
        # else: skip (unnumbered, unknown → likely noise)

    return toc if toc else None


def _similar_title(a: str, b: str) -> bool:
    """Check if two titles are similar enough to be considered duplicates."""
    # simple: one contains the other, or >80% word overlap
    if a == b or a in b or b in a:
        return True
    wa, wb = set(a.split()), set(b.split())
    if not wa or not wb:
        return False
    overlap = len(wa & wb) / max(len(wa), len(wb))
    return overlap > 0.8


def _clean_heading_text(text: str) -> str:
    text = text.strip().lstrip("#").strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" :：")


def _normalize_heading_text(text: str) -> str:
    cleaned = _clean_heading_text(text).casefold().replace("．", ".")
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_conclusion_title(text: str) -> bool:
    if not text:
        return False
    cleaned = _clean_heading_text(text)
    return bool(_CONCLUSION_KEYWORDS.search(cleaned))


def _is_known_section_title(text: str) -> bool:
    if not text:
        return False
    cleaned = _clean_heading_text(_strip_section_prefix(text))
    lowered = cleaned.lower().split(",", 1)[0].strip().rstrip(":：")
    zh_compact = re.sub(r"\s+", "", cleaned)
    if lowered in _KNOWN_SECTIONS or any(lowered.startswith(s) for s in ("appendix", "supplementary")):
        return True
    return any(zh_compact.startswith(term) for term in _KNOWN_SECTION_TITLES_ZH)


def _strip_section_prefix(text: str) -> str:
    stripped = text.strip()
    for pattern in (_RE_CHAPTER, _RE_CHAPTER_ZH, _RE_NUMBERED_PREFIX, _RE_ROMAN_PREFIX, _RE_LETTER_PREFIX):
        m = pattern.match(stripped)
        if m:
            return stripped[m.end() :].strip()
    return stripped


def _looks_like_plain_heading(text: str) -> bool:
    cleaned = _clean_heading_text(text)
    lowered = cleaned.lower()

    if not cleaned or len(cleaned) > _MAX_PLAIN_HEADING_LEN:
        return False
    if len(cleaned.split()) > _MAX_HEADING_WORDS:
        return False
    if "http://" in lowered or "https://" in lowered or "@" in cleaned:
        return False
    if re.search(r"\b(doi|copyright|received|accepted|published|correspondence|affiliation|license)\b", lowered):
        return False

    punctuation_count = sum(ch in ",;:!?。" for ch in cleaned)
    if punctuation_count > 3:
        return False

    if (
        _RE_NUMBERED.match(cleaned)
        or _RE_CHAPTER.match(cleaned)
        or _RE_CHAPTER_ZH.match(cleaned)
        or _RE_ROMAN_PREFIX.match(cleaned)
        or _RE_LETTER_PREFIX.match(cleaned)
    ):
        tail = _strip_section_prefix(cleaned)
        if not tail:
            return False
        if len(tail.split()) > _MAX_HEADING_WORDS:
            return False
        if len(cleaned) > 90 and sum(ch in ".!?;" for ch in tail) > 1:
            return False
        return True

    if _is_known_section_title(cleaned):
        return True

    return bool(re.fullmatch(r"[A-Z][A-Z0-9\s/&()\-]{2,80}", cleaned)) and len(cleaned.split()) <= 12


def _looks_like_asset_heading(text: str, level: int | None) -> bool:
    cleaned = _clean_heading_text(text)
    lowered = cleaned.lower()
    if not cleaned or len(cleaned) > _MAX_PLAIN_HEADING_LEN:
        return False
    if len(cleaned.split()) > _MAX_HEADING_WORDS:
        return False
    if "http://" in lowered or "https://" in lowered or "@" in cleaned:
        return False
    if _looks_like_plain_heading(cleaned):
        return True
    return level is not None and sum(ch in ".!?;" for ch in cleaned) <= 1


def _infer_heading_level(text: str) -> int:
    stripped = text.strip()
    m_num = _RE_NUMBERED_PREFIX.match(stripped)
    if m_num and _strip_section_prefix(stripped):
        num_str = m_num.group(1).replace("．", ".")
        return min(num_str.count(".") + 1, 3)
    return 1


def _iter_structure_assets(paper_d: Path) -> list[Path]:
    assets: list[Path] = []
    for pattern in ("*_content_list.json", "content_list.json", "*_layout.json", "layout.json"):
        assets.extend(sorted(paper_d.glob(pattern)))
    return assets


def _iter_structure_heading_candidates(node: Any):
    if isinstance(node, dict):
        if _node_has_heading_hint(node):
            text = _first_str(node, ("text", "title", "content", "value", "raw_text"))
            if text:
                yield {"text": text, "level": _extract_node_level(node)}
        for value in node.values():
            yield from _iter_structure_heading_candidates(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_structure_heading_candidates(item)


def _node_has_heading_hint(node: dict[str, Any]) -> bool:
    for key in ("type", "kind", "category", "block_type", "tag", "role", "label"):
        value = node.get(key)
        if isinstance(value, str):
            lowered = value.lower()
            if any(token in lowered for token in _HEADING_TYPE_HINTS):
                return True

    for key in ("text_level", "level", "section_level", "title_level"):
        value = node.get(key)
        if isinstance(value, (int, float)) and 0 < int(value) <= 6:
            return True
        if isinstance(value, str) and re.fullmatch(r"h?[1-6]", value.lower()):
            return True

    return False


def _extract_node_level(node: dict[str, Any]) -> int | None:
    for key in ("text_level", "level", "section_level", "title_level"):
        value = node.get(key)
        if isinstance(value, (int, float)):
            return max(1, min(int(value), 3))
        if isinstance(value, str):
            m = re.fullmatch(r"h?([1-6])", value.lower())
            if m:
                return max(1, min(int(m.group(1)), 3))
    return None


def _first_str(node: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _locate_heading_line(candidate_text: str, normalized_lines: dict[int, str]) -> int | None:
    candidate_norm = _normalize_heading_text(candidate_text)
    if not candidate_norm:
        return None

    for line_no, line_norm in normalized_lines.items():
        if line_norm == candidate_norm:
            return line_no

    for line_no, line_norm in normalized_lines.items():
        if candidate_norm in line_norm or line_norm in candidate_norm:
            if len(line_norm) >= max(8, len(candidate_norm) // 2):
                return line_no

    return None


def _iter_fallback_windows(lines: list[str]):
    n = len(lines)
    if n == 0:
        return

    if n <= _FALLBACK_WINDOW_LINES:
        yield 1, n, _render_line_window(lines, 1, n)
        return

    floor = max(1, int(n * _FALLBACK_SCAN_FRACTION))
    end = n
    emitted = 0
    while emitted < _FALLBACK_MAX_WINDOWS:
        start = max(floor, end - _FALLBACK_WINDOW_LINES + 1)
        yield start, end, _render_line_window(lines, start, end)
        emitted += 1
        if start <= floor:
            break
        end = max(start + _FALLBACK_WINDOW_OVERLAP - 1, start)


def _render_line_window(lines: list[str], start: int, end: int) -> str:
    return "\n".join(f"{line_no}: {lines[line_no - 1]}" for line_no in range(start, end + 1))


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 else None
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        if m:
            parsed = int(m.group())
            return parsed if parsed > 0 else None
    return None


def _primary_path(
    lines: list[str],
    headers: list[dict],
    config: Config,
    max_retries: int,
    inspect: bool,
) -> L3AttemptResult:
    header_list = "\n".join(f"Line {h['line']}: {'#' * h['level']} {h['text']}" for h in headers)
    prompt = (
        "Below are all section headers (with line numbers) from an academic paper markdown file.\n"
        "Identify the header that marks the START of the conclusion section "
        "(may be named 'Conclusion', 'Conclusions', 'Concluding Remarks', 'Summary', "
        "'Discussion and Conclusion', 'Conclusion and Outlook', etc.).\n\n"
        f"{header_list}\n\n"
        'Return JSON only: {"line": <line_number>, "header": "<header_text>"}\n'
        'If no conclusion section exists, return: {"line": null, "header": null}'
    )

    last = _fail("primary", "no_conclusion", "LLM 未识别到结论节标题", method="primary")
    # 1 initial attempt + max_retries retries; range(1, ...) so attempt number is 1-based
    for attempt in range(1, max_retries + 2):
        method = f"primary-attempt{attempt}"
        try:
            result = _parse_json(_call_llm(prompt, config))
            start_line = _as_int(result.get("line"))
            if not start_line:
                _log.debug("[Primary #%d] LLM found no conclusion", attempt)
                last = _fail("primary", "no_conclusion", "LLM 未识别到结论节标题", method=method)
                continue

            # Find end: next REAL section header after start_line
            # Skip running headers (no section number, short text)
            end_line = None
            for h in headers:
                if h["line"] > start_line and _is_real_section(h["text"]):
                    end_line = h["line"] - 1
                    break

            extracted = _slice_lines(lines, start_line, end_line)
            _log.debug(
                "[Primary #%d] extracted lines %d-%s, %d chars", attempt, start_line, end_line or "EOF", len(extracted)
            )

            validation = _validate_and_clean(extracted, config)
            _log.debug(
                "[Primary #%d] validate: %s %s",
                attempt,
                "PASS" if validation.cleaned else "FAIL",
                validation.reason,
            )
            if validation.cleaned:
                return _ok(
                    "primary",
                    method,
                    validation.cleaned,
                    reason=validation.reason,
                    start_line=start_line,
                    end_line=end_line,
                )
            last = _fail(
                "primary",
                validation.status,
                validation.reason,
                method=method,
                start_line=start_line,
                end_line=end_line,
            )

        except Exception as e:
            _log.debug("[Primary #%d] exception: %s", attempt, e)
            last = _fail("primary", "llm_error", f"定位结论标题失败：{e}", method=method)

    return last


# ============================================================================
#  Fallback path
# ============================================================================


def _fallback_path(
    lines: list[str],
    config: Config,
    max_retries: int,
    inspect: bool,
) -> L3AttemptResult:
    last = _fail("fallback", "no_conclusion", "滑窗扫描未找到结论节", method="fallback")

    for window_idx, (window_start, window_end, sample) in enumerate(_iter_fallback_windows(lines), start=1):
        method = f"fallback-window{window_idx}"
        prompt = (
            "Find the conclusion section in the following excerpt from an academic paper. "
            "The excerpt is already annotated with GLOBAL 1-indexed line numbers. "
            "If the conclusion section appears in this excerpt, return the global line number "
            "where it STARTS and the global line number where it ENDS "
            "(last line before References/Appendix/end of the conclusion).\n\n"
            f"[Excerpt lines {window_start}–{window_end}]\n{sample}\n\n"
            'Return JSON only: {"start_line": <N>, "end_line": <N>}\n'
            'If no conclusion section exists in this excerpt, return: {"start_line": null, "end_line": null}'
        )

        try:
            result = _parse_json(_call_llm(prompt, config))
            start_line = _as_int(result.get("start_line"))
            end_line = _as_int(result.get("end_line"))
            if not start_line:
                _log.debug("[Fallback %s] LLM found no conclusion", method)
                last = _fail(
                    "fallback",
                    "no_conclusion",
                    f"窗口 {window_start}-{window_end} 未找到结论节",
                    method=method,
                )
                continue
            if end_line is not None and end_line < start_line:
                end_line = start_line

            extracted = _slice_lines(lines, start_line, end_line)
            _log.debug(
                "[Fallback %s] extracted lines %d-%s, %d chars",
                method,
                start_line,
                end_line or "EOF",
                len(extracted),
            )

            validation = _validate_and_clean(extracted, config)
            _log.debug(
                "[Fallback %s] validate: %s %s",
                method,
                "PASS" if validation.cleaned else "FAIL",
                validation.reason,
            )
            if validation.cleaned:
                return _ok(
                    "fallback",
                    method,
                    validation.cleaned,
                    reason=validation.reason,
                    start_line=start_line,
                    end_line=end_line,
                )

            last = _fail(
                "fallback",
                validation.status,
                validation.reason,
                method=method,
                start_line=start_line,
                end_line=end_line,
            )
        except Exception as e:
            _log.debug("[Fallback %s] exception: %s", method, e)
            last = _fail(
                "fallback",
                "llm_error",
                f"滑窗 {window_start}-{window_end} 定位失败：{e}",
                method=method,
            )

    return last


# ============================================================================
#  Synthesis path for papers without an explicit conclusion section
# ============================================================================


def _synthesis_path(
    data: dict[str, Any],
    lines: list[str],
    config: Config,
    inspect: bool,
) -> L3AttemptResult:
    sources = _collect_l3_synthesis_sources(data, lines)
    if not sources:
        return _fail(
            "synthesis",
            "no_sources",
            "未找到可用于综合 L3 的摘要、结果、讨论或图表标题候选源",
            method="synthesis",
        )

    source_text = _render_l3_sources(sources)
    prompt = (
        "You are building L3 for an academic-paper knowledge base.\n"
        "L3 is a paper-level takeaway card, not merely a copied conclusion section.\n"
        "The paper appears to lack a clear standalone conclusion section, or the explicit conclusion extraction failed.\n"
        "Use ONLY the supplied source snippets. Do not add facts from general knowledge.\n\n"
        "Tasks:\n"
        "1. Write a concise paper-level takeaway.\n"
        "2. Extract 2-6 key findings that are directly supported by the snippets.\n"
        "3. Extract quantitative signals when present: sample size, effect size, rate, P value, CI, dose, time, endpoint, model, or measurement.\n"
        "4. Extract limitations or boundary conditions when present.\n"
        "5. Set confidence to high only when abstract/results/discussion support the same takeaway; otherwise medium or low.\n\n"
        "Return JSON only with this schema:\n"
        "{"
        '"takeaway": "<paper-level conclusion>", '
        '"key_findings": [{"claim": "...", "evidence_basis": "<source label>"}], '
        '"quantitative_signals": [{"text": "...", "source": "<source label>"}], '
        '"limitations": ["..."], '
        '"confidence": "high|medium|low", '
        '"warnings": ["..."]'
        "}\n\n"
        f"{source_text}"
    )

    try:
        timeout = getattr(getattr(config, "llm", None), "timeout_clean", None)
        parsed = _parse_json(_call_llm(prompt, config, timeout=timeout))
    except Exception as e:
        return _fail("synthesis", "llm_error", f"综合 L3 失败：{e}", method="synthesis")

    takeaway = str(parsed.get("takeaway") or "").strip()
    if len(takeaway) < 50:
        return _fail("synthesis", "validation_reject", "综合 L3 未返回足够具体的 takeaway", method="synthesis")

    key_findings = _normalize_l3_dict_list(parsed.get("key_findings"), default_key="claim", limit=6)
    quantitative = _normalize_l3_dict_list(parsed.get("quantitative_signals"), default_key="text", limit=10)
    if not quantitative:
        for source in sources:
            quantitative.extend(_extract_quantitative_signals(source["text"], source=source["source"], limit=4))
            if len(quantitative) >= 10:
                quantitative = quantitative[:10]
                break
    limitations = _normalize_l3_string_list(parsed.get("limitations"), limit=6)
    if not limitations:
        for source in sources:
            limitations.extend(_extract_limitations(source["text"], limit=3))
            if len(limitations) >= 6:
                limitations = limitations[:6]
                break
    warnings = _normalize_l3_string_list(parsed.get("warnings"), limit=8)
    warnings.extend(["no_explicit_conclusion_section", "inferred_from_non_conclusion_sources"])
    warnings = list(dict.fromkeys(warnings))

    record = _build_l3_record(
        mode="inferred_synthesis",
        confidence=str(parsed.get("confidence") or "medium").strip().lower(),
        takeaway=takeaway,
        method="synthesis",
        source_spans=[
            {
                "source": s["source"],
                "start_line": s.get("start_line"),
                "end_line": s.get("end_line"),
            }
            for s in sources
        ],
        key_findings=key_findings,
        quantitative_signals=quantitative,
        limitations=limitations,
        warnings=warnings,
        source_excerpt=source_text[:4000],
    )
    rendered = _render_l3_record(record) or takeaway
    _log.debug("[Synthesis] L3 generated from %d sources, %d chars", len(sources), len(rendered))
    return _ok("synthesis", "synthesis", rendered, reason="综合生成 L3", record=record)


def _collect_l3_synthesis_sources(data: dict[str, Any], lines: list[str]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    abstract = data.get("abstract")
    if isinstance(abstract, str) and abstract.strip() and abstract.strip() != "[No abstract available]":
        sources.append({"source": "abstract", "start_line": None, "end_line": None, "text": abstract.strip()})

    headers = _extract_headers(lines)
    for idx, header in enumerate(headers):
        label = _l3_source_label(header.get("text", ""))
        if not label:
            continue
        start_line = int(header["line"])
        end_line = len(lines)
        for next_header in headers[idx + 1 :]:
            if _is_real_section(next_header["text"]):
                end_line = int(next_header["line"]) - 1
                break
        text = _slice_lines(lines, start_line, end_line)
        text = _compact_l3_source_text(text)
        if text:
            sources.append({"source": label, "start_line": start_line, "end_line": end_line, "text": text})

    sources.extend(_collect_caption_sources(lines))
    return _dedupe_l3_sources(sources)


def _l3_source_label(title: str) -> str | None:
    cleaned = _clean_heading_text(_strip_section_prefix(title)).casefold()
    zh = re.sub(r"\s+", "", cleaned)
    if cleaned in {"abstract", "summary", "highlights", "key points", "significance statement"} or zh in {
        "摘要",
        "要点",
        "亮点",
        "意义声明",
    }:
        return "abstract_or_highlights"
    if cleaned in {"results", "results and discussion"} or zh.startswith("结果"):
        return "results"
    if cleaned in {"discussion", "general discussion"} or zh.startswith("讨论"):
        return "discussion"
    return None


def _compact_l3_source_text(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _L3_SECTION_CHAR_LIMIT:
        return stripped
    head = stripped[: int(_L3_SECTION_CHAR_LIMIT * 0.45)].rstrip()
    tail = stripped[-int(_L3_SECTION_CHAR_LIMIT * 0.45) :].lstrip()
    return f"{head}\n\n[...middle omitted for L3 synthesis...]\n\n{tail}"


def _collect_caption_sources(lines: list[str]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    caption_start = re.compile(r"^\s*(?:#+\s*)?(?:fig(?:ure)?\.?\s*\d+|table\s*\d+|图\s*\d+|表\s*\d+)", re.IGNORECASE)
    for idx, line in enumerate(lines, start=1):
        if not caption_start.match(line):
            continue
        chunk = [line.strip()]
        for extra in range(idx, min(len(lines), idx + 4)):
            nxt = lines[extra].strip()
            if not nxt:
                break
            if re.match(r"^#{1,6}\s+", nxt):
                break
            chunk.append(nxt)
        text = " ".join(chunk)
        if _NUMERIC_SIGNAL_RE.search(text) or len(text) >= 80:
            sources.append({"source": "figure_or_table_caption", "start_line": idx, "end_line": idx + len(chunk) - 1, "text": text})
    return sources[:8]


def _dedupe_l3_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    used_chars = 0
    for source in sources:
        text = str(source.get("text") or "").strip()
        if len(text) < 40:
            continue
        key = (str(source.get("source") or ""), text[:200].casefold())
        if key in seen:
            continue
        seen.add(key)
        remaining = _L3_SOURCE_CHAR_BUDGET - used_chars
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining].rstrip()
        item = dict(source)
        item["text"] = text
        deduped.append(item)
        used_chars += len(text)
    return deduped


def _render_l3_sources(sources: list[dict[str, Any]]) -> str:
    blocks = []
    for idx, source in enumerate(sources, start=1):
        line_info = ""
        if source.get("start_line") is not None:
            line_info = f" lines {source.get('start_line')}-{source.get('end_line')}"
        blocks.append(f"[SOURCE {idx}: {source['source']}{line_info}]\n{source['text']}")
    return "\n\n".join(blocks)


def _normalize_l3_string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("claim") or item.get("limitation") or "").strip()
        else:
            text = str(item).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text[:600])
        if len(out) >= limit:
            break
    return out


def _normalize_l3_dict_list(value: Any, *, default_key: str, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            normalized = {str(k): v for k, v in item.items() if isinstance(k, str)}
            text = str(normalized.get(default_key) or normalized.get("text") or normalized.get("claim") or "").strip()
        else:
            text = str(item).strip()
            normalized = {default_key: text}
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized[default_key] = text[:600]
        out.append(normalized)
        if len(out) >= limit:
            break
    return out


# ============================================================================
#  LLM validation + cleaning
# ============================================================================


def _validate_and_clean(text: str, config: Config) -> L3ValidationResult:
    """校验并清理提取的结论文本。

    Returns:
        Structured validation result. ``cleaned`` is present only when the
        excerpt contains valid conclusion content.
    """
    if len(text.strip()) < 100:
        return L3ValidationResult(status="too_short", reason="文本过短")

    prompt = (
        "The following text was extracted as the conclusion section of an academic paper. "
        "Your tasks:\n"
        "1. Check if it contains actual conclusion content (summary of findings, contributions, or future work).\n"
        "2. If yes, return a CLEANED version:\n"
        "   - Remove the section header line (e.g. '# 6. Conclusion', '# Concluding Remarks')\n"
        "   - Remove any in-text running headers (e.g. '# Author and others', '# Journal Name')\n"
        "   - Remove everything AFTER the conclusion ends: Acknowledgments, Funding statements, "
        "CRediT authorship statements, Declaration of interests/competing interest, "
        "Data availability, Author ORCIDs, Author contributions, conflict of interest, etc.\n"
        "   - Keep only the actual conclusion/summary paragraphs. Do NOT truncate mid-sentence.\n"
        "   - Preserve information density: retain concrete findings, mechanisms, quantitative results, "
        "limitations, and future directions that are present in the source.\n"
        "   - Do not aggressively summarize, paraphrase, or generalize; clean the extracted text rather than rewriting it.\n"
        "3. If it contains NO conclusion content at all, set conclusion to null.\n\n"
        f"{text}\n\n"
        'Return JSON only: {"conclusion": "<cleaned text or null>", "reason": "<one sentence>"}'
    )
    try:
        result = _parse_json(_call_llm(prompt, config, timeout=config.llm.timeout_clean))
        cleaned = result.get("conclusion")
        reason = result.get("reason") or ""
        if not isinstance(cleaned, str) or len(cleaned.strip()) < 50:
            return L3ValidationResult(status="validation_reject", reason=reason or "无有效结论内容")
        return L3ValidationResult(status="ok", reason=reason or "校验通过", cleaned=cleaned.strip())
    except Exception as e:
        return L3ValidationResult(status="llm_error", reason=f"校验异常：{e}")


def _validate_with_retries(text: str, config: Config, *, attempts: int) -> L3ValidationResult:
    result = _validate_and_clean(text, config)
    for _ in range(1, max(1, attempts)):
        if result.status != "llm_error":
            break
        result = _validate_and_clean(text, config)
    return result


# ============================================================================
#  LLM + JSON utilities
# ============================================================================


def _call_llm(prompt: str, config: Config, timeout: int | None = None) -> str:
    from autor.metrics import call_llm

    result = call_llm(prompt, config, timeout=timeout, purpose="loader")
    return result.content


def _parse_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```\w*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fix unescaped backslashes (e.g. LaTeX: \alpha, \vec, \frac).
        # Only runs when initial parse fails. Valid JSON escapes are
        # preserved: \" \\ \/ \b \f \n \r \t \uXXXX
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            # If escaping made things worse, raise with original text
            return json.loads(text)


def _slice_lines(lines: list[str], start: int, end: int | None) -> str:
    """1-indexed, inclusive on both ends."""
    s = max(0, start - 1)
    e = end if end is not None else len(lines)
    return "\n".join(lines[s:e]).strip()
