"""
sources/local.py — 扫描 data/papers/ 目录，产出论文记录
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

from autor.papers import iter_paper_dirs, read_meta

_log = logging.getLogger(__name__)


def iter_papers(papers_dir: Path) -> Iterator[tuple[str, dict, Path]]:
    """遍历论文目录，逐篇产出元数据。

    扫描 ``papers_dir`` 中每篇一目录的子目录结构，
    要求 ``meta.json`` 和 ``paper.md`` 均存在。

    Args:
        papers_dir: 已入库论文目录（每篇一目录结构）。

    Yields:
        ``(paper_id, meta_dict, md_path)`` 三元组。
        ``paper_id`` 为 ``meta.json["id"]``（UUID），
        回退到目录名。跳过缺少 ``paper.md`` 或解析失败的目录。
    """
    for pdir in iter_paper_dirs(papers_dir):
        md_file = pdir / "paper.md"
        if not md_file.exists():
            _log.warning("missing paper.md, skipping: %s", pdir.name)
            continue
        try:
            meta = read_meta(pdir)
        except (ValueError, FileNotFoundError) as e:
            _log.debug("failed to read meta.json in %s: %s", pdir.name, e)
            continue
        paper_id = meta.get("id") or pdir.name
        yield paper_id, meta, md_file
