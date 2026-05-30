"""
cli.py — autor 命令行入口
================================

命令：
    autor index [--rebuild] [--status] [--background]
    autor search <query> [--top N] [--year Y] [--journal J] [--type T]
    autor search-author <query> [--top N] [--year Y] [--journal J] [--type T]
    autor research <query> [--run-dir DIR]
    autor show <paper-id> [--layer 1|2|3|4]
    autor enrich-toc [<paper-id> | --all] [--force] [--inspect]
    autor enrich-l3 [<paper-id> | --all | --workspace NAME] [--only-missing] [--force] [--inspect] [--max-retries N]
    autor top-cited [--top N] [--year Y] [--journal J] [--type T]
    autor refs <paper-id>
    autor citing <paper-id>
    autor shared-refs <id1> <id2> ... [--min N]
    autor refetch [<paper-id> | --workspace NAME | --all] [--force]
    autor rename [<paper-id> | --all] [--dry-run]
    autor audit [--severity error|warning|info]
    autor repair <paper-id> --title "..." [--doi DOI] [--author NAME] [--year Y] [--no-api] [--dry-run]
    autor backfill-abstract [--dry-run]
    autor pipeline <preset> | --steps <s1,s2,...> [--list] [--dry-run] ...
    autor metrics [--summary] [--last N] [--category CAT] [--since DATE]
    autor setup [check] [--lang en|zh]
    autor migrate-dirs [--execute]
    autor explore fetch --issn <ISSN> [--name NAME] [--year-range Y]
    autor explore search --name <NAME> <query> [--top N]
    autor explore list
    autor explore info [--name NAME]
    autor export bibtex [<paper-id> ...] [--all] [--year Y] [--journal J] [-o FILE]
    autor import-endnote <file.xml|file.ris> [--no-api] [--dry-run] [--no-convert]
    autor import-zotero [--api-key KEY] [--library-id ID] [--local PATH] [--list-collections] ...
    autor attach-pdf <paper-id> <path/to/paper.pdf>
    autor citation-check [<file>] [--ws <workspace-name>]
    autor plot <prompt> [--ws <workspace-name>] [--name STEM]
    autor ws init <name>
    autor ws add <name> <paper-refs...> [--search Q] [--all]
    autor ws remove <name> <paper-refs...>
    autor ws list
    autor ws show <name>
    autor ws search <name> <query> [--top N]
    autor ws rename <old-name> <new-name>
    autor ws export <name> [-o FILE]
    autor ws export-meta <name> [-o FILE] [--format json|jsonl|csv]
    autor ws status <name> [--papers]
    autor ws export-evidence <name> [-o FILE]
    autor ws screen <name> --criteria TEXT [--target N] [--apply]
    autor ws plan-package <name> [--title TITLE] [--criteria TEXT]
    autor ws citation-coverage <name> [--manuscript FILE] [--require retained|citable|must_cite]
    autor ws citation-network <name> [--min-shared N] [-o FILE]
    autor ws figure-status <name> [--fail-if-missing]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from autor.config import load_config
from autor.log import ui

_log = logging.getLogger(__name__)


# ============================================================================
#  Filter args helper
# ============================================================================


def _resolve_top(args: argparse.Namespace, default: int) -> int:
    return args.top if args.top is not None else default


def _record_search_metrics(
    store,
    name: str,
    query: str,
    results: list[dict],
    elapsed: float,
    args: argparse.Namespace,
) -> None:
    """Record a search event to the metrics store, silently ignoring failures."""
    if not store:
        return
    try:
        store.record(
            category="search",
            name=name,
            duration_s=elapsed,
            detail={
                "query": query,
                "result_count": len(results),
                "top_dois": [r["doi"] for r in results[:5] if r.get("doi")],
                "filters": {
                    "year": getattr(args, "year", None),
                    "journal": getattr(args, "journal", None),
                    "paper_type": getattr(args, "paper_type", None),
                },
            },
        )
    except Exception as _e:
        _log.debug("metrics record failed: %s", _e)


def _add_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--year", type=str, default=None, help="年份过滤：2023 / 2020-2024 / 2020-")
    parser.add_argument("--journal", type=str, default=None, help="期刊名过滤（模糊匹配）")
    parser.add_argument(
        "--type",
        type=str,
        default=None,
        dest="paper_type",
        help="论文类型过滤：review / journal-article 等（模糊匹配）",
    )


def _resolve_ws_paper_ids(args: argparse.Namespace, cfg) -> set[str] | None:
    ws_name = getattr(args, "ws", None)
    if not ws_name:
        return None
    from autor import workspace

    if not workspace.validate_workspace_name(ws_name):
        raise ValueError(f"非法工作区名称: {ws_name}")

    ws_dir = cfg._root / "workspace" / ws_name
    pids = workspace.read_paper_ids(ws_dir)
    if not pids:
        ui(f"工作区 {ws_name} 为空或不存在")
    return pids


# ============================================================================
#  Dependency check helpers
# ============================================================================

_INSTALL_HINTS: dict[str, str] = {
    "endnote_utils": "pip install autor[import]",
    "pyzotero": "pip install autor[import]",
}


def _check_import_error(e: ImportError) -> None:
    """Log a user-friendly message for missing optional dependencies, then exit."""
    mod = getattr(e, "name", "") or ""
    # Match the top-level package name
    top = mod.split(".")[0] if mod else ""
    hint = _INSTALL_HINTS.get(top, "")
    if hint:
        _log.error("缺少依赖: %s\n  安装: %s", mod, hint)
    else:
        _log.error("缺少依赖: %s\n  请安装所需的 Python 包", e)
    sys.exit(1)


# ============================================================================
#  Commands
# ============================================================================


def cmd_index(args: argparse.Namespace, cfg) -> None:
    from autor.index import build_index, build_index_atomic, index_status

    papers_dir = cfg.papers_dir
    db_path = cfg.index_db

    if getattr(args, "status", False):
        status = index_status(db_path)
        run_dir = cfg._root / ".run"
        job_file = run_dir / "index-job.json"
        if job_file.exists():
            try:
                job = json.loads(job_file.read_text(encoding="utf-8"))
                pid = int(job.get("pid") or 0)
                running = False
                if pid:
                    try:
                        os.kill(pid, 0)
                        running = True
                    except OSError:
                        running = False
                status["background_job"] = {**job, "running": running}
            except (OSError, json.JSONDecodeError, ValueError):
                status["background_job"] = {"status": "unreadable", "path": str(job_file)}
        ui(json.dumps(status, indent=2, ensure_ascii=False))
        return

    if not papers_dir.exists():
        _log.error("论文目录不存在: %s", papers_dir)
        sys.exit(1)

    if getattr(args, "background", False):
        run_dir = cfg._root / ".run"
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "index-rebuild.log"
        job_file = run_dir / "index-job.json"
        cmd = [sys.executable, "-m", "autor.cli", "index"]
        if args.rebuild:
            cmd.append("--rebuild")
        if getattr(args, "direct", False):
            cmd.append("--direct")
        if getattr(args, "tmp_dir", None):
            cmd.extend(["--tmp-dir", str(args.tmp_dir)])
        env = os.environ.copy()
        env["AUTOR_ROOT"] = str(cfg._root)
        out = log_path.open("ab")
        proc = subprocess.Popen(cmd, cwd=cfg._root, env=env, stdout=out, stderr=subprocess.STDOUT)
        out.close()
        job = {
            "pid": proc.pid,
            "command": cmd,
            "log": str(log_path),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "rebuild": bool(args.rebuild),
        }
        job_file.write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        ui(f"索引任务已在后台启动: PID {proc.pid}")
        ui(f"日志: {log_path}")
        ui("查看状态: autor index --status")
        return

    action = "重建索引" if args.rebuild else "构建索引"
    ui(f"{action}: {papers_dir} -> {db_path}")
    if args.rebuild and not getattr(args, "direct", False):
        count = build_index_atomic(
            papers_dir,
            db_path,
            rebuild=True,
            temp_dir=Path(args.tmp_dir) if getattr(args, "tmp_dir", None) else None,
        )
    else:
        count = build_index(papers_dir, db_path, rebuild=args.rebuild)
    ui(f"完成：已索引 {count} 篇论文。")
    ui("下一步：运行 `autor search <关键词>` 查看结果，或 `autor research <问题>` 生成可审计证据包。")


def cmd_search_author(args: argparse.Namespace, cfg) -> None:
    from autor.index import search_author

    query = " ".join(args.query)
    try:
        results = search_author(
            query,
            cfg.index_db,
            top_k=_resolve_top(args, cfg.search.top_k),
            year=args.year,
            journal=args.journal,
            paper_type=args.paper_type,
        )
    except FileNotFoundError as e:
        _log.error("%s", e)
        sys.exit(1)

    if not results:
        ui(f'未找到作者 "{query}" 的相关论文。')
        return

    ui(f'按作者检索到 {len(results)} 篇论文（"{query}"）:\n')
    for i, r in enumerate(results, start=1):
        _print_search_result(i, r)
    _print_search_next_steps()


def cmd_search(args: argparse.Namespace, cfg) -> None:
    import time

    from autor.index import search
    from autor.metrics import get_store

    query = " ".join(args.query)
    t0 = time.monotonic()
    try:
        results = search(
            query,
            cfg.index_db,
            top_k=_resolve_top(args, cfg.search.top_k),
            year=args.year,
            journal=args.journal,
            paper_type=args.paper_type,
        )
    except FileNotFoundError as e:
        _log.error("%s", e)
        sys.exit(1)

    elapsed = time.monotonic() - t0
    store = get_store()
    _record_search_metrics(store, "search", query, results, elapsed, args)

    if not results:
        ui(f'未找到与 "{query}" 相关的结果。')
        return

    ui(f'关键词检索到 {len(results)} 篇论文（"{query}"）:\n')
    for i, r in enumerate(results, start=1):
        _print_search_result(i, r)
    _print_search_next_steps()


def cmd_show(args: argparse.Namespace, cfg) -> None:
    from autor.loader import append_notes, load_l1, load_l2, load_l3, load_l4, load_notes
    from autor.metrics import get_store

    paper_d = _resolve_paper(args.paper_id, cfg)
    json_path = paper_d / "meta.json"
    md_path = paper_d / "paper.md"

    # Handle --append-notes (append, then continue to show content)
    if getattr(args, "append_notes", None):
        notes_text = str(args.append_notes).strip()
        if not notes_text:
            ui("警告：--append-notes 内容为空，已忽略。")
        else:
            try:
                append_notes(paper_d, notes_text)
            except (UnicodeDecodeError, OSError) as e:
                _log.error("追加笔记失败：%s", e)
                ui(f"追加笔记到 {paper_d.name}/notes.md 失败：{e}")
            else:
                ui(f"已追加笔记到 {paper_d.name}/notes.md")

    l1 = load_l1(json_path)
    _print_header(l1)

    # Show existing agent notes (T2 layer) if available
    try:
        notes = load_notes(paper_d)
    except (UnicodeDecodeError, OSError) as e:
        _log.warning("读取 notes.md 失败：%s", e)
        notes = None
    if notes:
        ui("\n--- Agent 笔记 (notes.md) ---\n")
        ui(notes)
        ui("\n--- 笔记结束 ---\n")

    store = get_store()

    def _record_read() -> None:
        if store:
            try:
                store.record(
                    category="read",
                    name=paper_d.name,  # use dir_name so insights can find the paper
                    detail={
                        "layer": args.layer,
                        "title": l1.get("title", ""),
                        "doi": l1.get("doi", ""),
                    },
                )
            except Exception as _e:
                _log.debug("metrics record failed: %s", _e)

    if args.layer == 1:
        _record_read()
        return

    if args.layer == 2:
        abstract = load_l2(json_path)
        ui("\n--- 摘要 ---\n")
        ui(abstract)
        _record_read()
        return

    if args.layer == 3:
        conclusion = load_l3(json_path)
        if conclusion is None:
            _log.error("尚未生成 L3 结论层。请先运行：autor enrich-l3 %s", args.paper_id)
            sys.exit(1)
        ui("\n--- L3 结论层 ---\n")
        ui(conclusion)
        _record_read()
        return

    if args.layer == 4:
        if not md_path.exists():
            _log.error("未找到 paper.md：%s", md_path)
            sys.exit(1)
        ui("\n--- 全文 ---\n")
        ui(load_l4(md_path))
        _record_read()
        return


def cmd_research(args: argparse.Namespace, cfg) -> None:
    from autor.index import research_bundle

    query = " ".join(args.query)
    run_dir = Path(args.run_dir) if args.run_dir else cfg._root / "workspace" / "research-runs" / _safe_run_name(query)
    try:
        result = research_bundle(
            query,
            cfg.index_db,
            run_dir=run_dir,
            top_k=_resolve_top(args, cfg.search.top_k),
            cfg=cfg,
            year=args.year,
            journal=args.journal,
            paper_type=args.paper_type,
            neighbors=args.neighbors,
            max_chars=args.max_chars,
            per_node_max_chars=args.per_node_max_chars,
        )
    except FileNotFoundError as e:
        _log.error("%s", e)
        sys.exit(1)

    paths = result.get("paths", {})
    verify = result.get("verify", {})
    if paths:
        ui(f"证据包已生成: {paths.get('round_bundle_md')}")
        ui(f"trace: {paths.get('trace')}")
        ui(f"verify: {paths.get('verify')}")
    ui(f"验证: ok={verify.get('ok')} evidence={verify.get('evidence_count')} budget_exhausted={verify.get('budget_exhausted')}")


def _safe_run_name(query: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9\u3400-\u9fff]+", "-", query.strip()).strip("-")
    return (stem[:48] or "query").lower()


def cmd_audit(args: argparse.Namespace, cfg) -> None:
    from autor.audit import audit_papers, format_report

    papers_dir = cfg.papers_dir
    if not papers_dir.exists():
        _log.error("论文目录不存在: %s", papers_dir)
        sys.exit(1)

    ui(f"正在审计论文库: {papers_dir}\n")
    issues = audit_papers(papers_dir)

    if args.severity:
        issues = [i for i in issues if i.severity == args.severity]

    ui(format_report(issues))


def cmd_repair(args: argparse.Namespace, cfg) -> None:
    import json

    from autor.ingest.metadata import (
        PaperMetadata,
        _extract_lastname,
        enrich_metadata,
        generate_new_stem,
        rename_files,
        write_metadata_json,
    )

    papers_dir = cfg.papers_dir
    paper_id = args.paper_id

    paper_d = papers_dir / paper_id
    md_path = paper_d / "paper.md"
    json_path = paper_d / "meta.json"

    if not md_path.exists():
        _log.error("文件不存在: %s", md_path)
        sys.exit(1)

    # Preserve existing UUID
    existing_uuid = ""
    if json_path.exists():
        try:
            existing_data = json.loads(json_path.read_text(encoding="utf-8"))
            existing_uuid = existing_data.get("id", "")
        except (json.JSONDecodeError, OSError) as e:
            _log.debug("failed to read existing meta.json: %s", e)

    # Build PaperMetadata from CLI args (skip md parsing)
    meta = PaperMetadata()
    meta.id = existing_uuid
    meta.title = args.title
    meta.doi = args.doi or ""
    meta.year = args.year
    meta.source_file = md_path.name
    if args.author:
        meta.authors = [args.author]
        meta.first_author = args.author
        meta.first_author_lastname = _extract_lastname(args.author)

    ui(f"修复论文: {paper_id}")
    ui(f"  标题: {meta.title}")
    ui(f"  作者: {meta.first_author or '?'} | 年份: {meta.year or '?'} | DOI: {meta.doi or '无'}")

    # API enrichment
    if not args.no_api:
        _log.debug("querying APIs")
        cli_author = meta.first_author
        cli_lastname = meta.first_author_lastname
        cli_year = meta.year

        meta = enrich_metadata(meta)

        if cli_author and not meta.authors:
            meta.authors = [cli_author]
            meta.first_author = cli_author
            meta.first_author_lastname = cli_lastname
        if cli_year and not meta.year:
            meta.year = cli_year
    else:
        meta.extraction_method = "manual_fix"
        _log.debug("skipping API query (--no-api)")

    ui(f"  结果: {meta.first_author_lastname} ({meta.year}) {meta.title[:60]}")
    if meta.doi:
        ui(f"  DOI: {meta.doi}")
    ui(f"  方法: {meta.extraction_method}")

    if args.dry_run:
        ui("  [dry-run] 未写入任何文件")
        return

    # Write new JSON
    write_metadata_json(meta, json_path)
    ui(f"  已写入: {json_path.name}")

    new_stem = generate_new_stem(meta)
    rename_files(md_path, json_path, new_stem, dry_run=False)

    _log.debug("done. consider running pipeline reindex")


def cmd_enrich_toc(args: argparse.Namespace, cfg) -> None:
    from autor.loader import enrich_toc
    from autor.papers import iter_paper_dirs

    papers_dir = cfg.papers_dir

    if args.all:
        targets = sorted(d / "meta.json" for d in iter_paper_dirs(papers_dir))
    elif args.paper_id:
        targets = [papers_dir / args.paper_id / "meta.json"]
    else:
        _log.error("请指定 <paper-id> 或 --all")
        sys.exit(1)

    ok = fail = skip = 0
    for json_path in targets:
        md_path = json_path.parent / "paper.md"
        if not md_path.exists():
            _log.error("已跳过（缺少 paper.md）: %s", json_path.parent.name)
            skip += 1
            continue

        ui(f"\n{json_path.parent.name}")
        success = enrich_toc(
            json_path,
            md_path,
            cfg,
            force=args.force,
            inspect=args.inspect,
        )
        if success:
            ok += 1
        else:
            fail += 1

    if args.all or len(targets) > 1:
        ui(f"\n完成: {ok} 成功 | {fail} 失败 | {skip} 跳过")


def cmd_pipeline(args: argparse.Namespace, cfg) -> None:
    from autor import workspace as workspace_mod
    from autor.ingest.pipeline import PRESETS, STEPS, run_pipeline

    if args.list_steps:
        ui("可用步骤：")
        for name, sdef in STEPS.items():
            ui(f"  {name:<10} [{sdef.scope:<7}]  {sdef.desc}")
        ui("\n可用预设：")
        for name, steps in PRESETS.items():
            ui(f"  {name:<10} = {', '.join(steps)}")
        return

    # Resolve step list
    if args.preset:
        if args.preset not in PRESETS:
            _log.error("未知预设 '%s'。可用预设: %s", args.preset, ", ".join(PRESETS))
            sys.exit(1)
        step_names = PRESETS[args.preset]
    elif args.steps:
        step_names = [s.strip() for s in args.steps.split(",") if s.strip()]
    else:
        _log.error("请指定一个预设名称或使用 --steps")
        sys.exit(1)

    if args.workspace and not workspace_mod.validate_workspace_name(args.workspace):
        ui(f"非法工作区名称: {args.workspace}")
        return

    opts = {
        "dry_run": args.dry_run,
        "no_api": args.no_api,
        "force": args.force,
        "inspect": args.inspect,
        "max_retries": args.max_retries,
        "rebuild": args.rebuild,
    }
    workspace_filter = getattr(args, "workspace_filter", None)
    if workspace_filter:
        opts["workspace_filter"] = workspace_filter
    if args.inbox:
        opts["inbox_dir"] = Path(args.inbox).resolve()
    if args.papers:
        opts["papers_dir"] = Path(args.papers).resolve()

    run_pipeline(step_names, cfg, opts, workspace=args.workspace)


def cmd_enrich_l3(args: argparse.Namespace, cfg) -> None:
    from autor.loader import enrich_l3
    from autor.papers import iter_paper_dirs, read_meta

    papers_dir = cfg.papers_dir

    if args.all:
        targets = sorted(d / "meta.json" for d in iter_paper_dirs(papers_dir))
    elif getattr(args, "workspace", None):
        from autor import workspace as workspace_mod

        if not workspace_mod.validate_workspace_name(args.workspace):
            ui(f"非法工作区名称: {args.workspace}")
            return
        ws_dir = cfg._root / "workspace" / args.workspace
        dir_names = workspace_mod.read_dir_names(ws_dir, cfg.index_db)
        targets = sorted(papers_dir / name / "meta.json" for name in dir_names)
        if getattr(args, "only_missing", False):
            filtered = []
            for jp in targets:
                try:
                    meta = read_meta(jp.parent)
                except (ValueError, FileNotFoundError):
                    continue
                if not meta.get("l3"):
                    filtered.append(jp)
            targets = filtered
    elif args.paper_id:
        targets = [papers_dir / args.paper_id / "meta.json"]
    else:
        _log.error("请指定 <paper-id>、--workspace 或 --all")
        sys.exit(1)

    ok = fail = skip = 0
    for json_path in targets:
        md_path = json_path.parent / "paper.md"
        if not md_path.exists():
            _log.error("已跳过（缺少 paper.md）: %s", json_path.parent.name)
            skip += 1
            continue

        ui(f"\n{json_path.parent.name}")
        success = enrich_l3(
            json_path,
            md_path,
            cfg,
            force=args.force,
            max_retries=args.max_retries,
            inspect=args.inspect,
        )
        if success:
            ok += 1
        else:
            fail += 1
            meta = read_meta(json_path.parent)
            status = meta.get("l3_last_attempt_status") or "failed"
            stage = meta.get("l3_last_attempt_stage") or "unknown"
            reason = meta.get("l3_last_attempt_reason") or "未知原因"
            ui(f"  失败 [{stage}/{status}]: {reason}")

    if args.all or getattr(args, "workspace", None) or len(targets) > 1:
        ui(f"\n完成: {ok} 成功 | {fail} 失败 | {skip} 跳过")


def cmd_top_cited(args: argparse.Namespace, cfg) -> None:
    from autor.index import top_cited

    try:
        results = top_cited(
            cfg.index_db,
            top_k=_resolve_top(args, cfg.search.top_k),
            year=args.year,
            journal=args.journal,
            paper_type=args.paper_type,
        )
    except FileNotFoundError as e:
        _log.error("%s", e)
        sys.exit(1)

    if not results:
        ui("索引中没有引用数据。请先运行 autor refetch --all。")
        return

    ui(f"按引用量排序的前 {len(results)} 篇论文：\n")
    for i, r in enumerate(results, start=1):
        _print_search_result(i, r)
    _print_search_next_steps()


def cmd_refs(args: argparse.Namespace, cfg) -> None:
    from autor.index import get_references
    from autor.papers import read_meta

    paper_d = _resolve_paper(args.paper_id, cfg)
    meta = read_meta(paper_d)
    paper_uuid = meta.get("id", "")

    pids = _resolve_ws_paper_ids(args, cfg)
    refs = get_references(paper_uuid, cfg.index_db, paper_ids=pids)
    if not refs:
        ui("该论文没有参考文献数据。请先运行 refetch 拉取 references。")
        return

    in_lib = [r for r in refs if r.get("target_id")]
    out_lib = [r for r in refs if not r.get("target_id")]

    scope = f"工作区 {args.ws}" if getattr(args, "ws", None) else "库内"
    ui(f"参考文献共 {len(refs)} 篇（{scope} {len(in_lib)} 篇，库外 {len(out_lib)} 篇）\n")

    if in_lib:
        ui("── 库内 ──")
        for i, r in enumerate(in_lib, 1):
            display = r.get("dir_name") or r["target_id"]
            year = r.get("year") or "?"
            author = r.get("first_author") or "?"
            ui(f"[{i}] {display}")
            ui(f"     {author} | {year} | {r.get('title', '?')}")
            ui(f"     DOI: {r['target_doi']}")
            ui()

    if out_lib:
        ui("── 库外 ──")
        for i, r in enumerate(out_lib, 1):
            ui(f"[{i}] DOI: {r['target_doi']}")
        ui()


def cmd_citing(args: argparse.Namespace, cfg) -> None:
    from autor.index import get_citing_papers
    from autor.papers import read_meta

    paper_d = _resolve_paper(args.paper_id, cfg)
    meta = read_meta(paper_d)
    paper_uuid = meta.get("id", "")

    pids = _resolve_ws_paper_ids(args, cfg)
    results = get_citing_papers(paper_uuid, cfg.index_db, paper_ids=pids)
    if not results:
        scope = f"工作区 {args.ws} 中" if getattr(args, "ws", None) else "本地"
        ui(f"没有找到引用该论文的{scope}论文。")
        return

    scope = f"工作区 {args.ws}" if getattr(args, "ws", None) else "本地"
    ui(f"共 {len(results)} 篇{scope}论文引用了此论文：\n")
    for i, r in enumerate(results, 1):
        display = r.get("dir_name") or r["source_id"]
        year = r.get("year") or "?"
        author = r.get("first_author") or "?"
        ui(f"[{i}] {display}")
        ui(f"     {author} | {year} | {r.get('title', '?')}")
        ui()


def cmd_shared_refs(args: argparse.Namespace, cfg) -> None:
    from autor.index import get_shared_references
    from autor.papers import read_meta

    paper_uuids = []
    for pid in args.paper_ids:
        paper_d = _resolve_paper(pid, cfg)
        meta = read_meta(paper_d)
        paper_uuids.append(meta.get("id", ""))

    min_shared = args.min if args.min is not None else 2
    pids = _resolve_ws_paper_ids(args, cfg)
    results = get_shared_references(paper_uuids, cfg.index_db, min_shared=min_shared, paper_ids=pids)
    if not results:
        ui(f"没有找到被 ≥{min_shared} 篇论文共同引用的参考文献。")
        return

    ui(f"共同参考文献（被 ≥{min_shared} 篇共引）：共 {len(results)} 篇\n")
    for i, r in enumerate(results, 1):
        count = r["shared_count"]
        if r.get("target_id"):
            display = r.get("dir_name") or r["target_id"]
            year = r.get("year") or "?"
            ui(f"[{i}] [{count}x] {display}")
            ui(f"     {r.get('title', '?')} | {year}")
            ui(f"     DOI: {r['target_doi']}")
        else:
            ui(f"[{i}] [{count}x] DOI: {r['target_doi']}")
        ui()


def cmd_refetch(args: argparse.Namespace, cfg) -> None:
    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from autor.ingest.metadata import refetch_metadata
    from autor.papers import iter_paper_dirs

    papers_dir = cfg.papers_dir

    if getattr(args, "workspace", None):
        from autor import workspace as workspace_mod

        if not workspace_mod.validate_workspace_name(args.workspace):
            _log.error("非法工作区名称: %s", args.workspace)
            sys.exit(1)
        ws_dir = cfg._root / "workspace" / args.workspace
        if not ws_dir.exists():
            _log.error("工作区不存在: %s", args.workspace)
            sys.exit(1)
        targets = []
        for entry in workspace_mod.read_entries(ws_dir):
            dir_name = entry.get("dir_name", "")
            jp = papers_dir / dir_name / "meta.json"
            if jp.exists():
                targets.append(jp)
            else:
                try:
                    record = workspace_mod.show(ws_dir, cfg.index_db)
                except Exception:
                    record = []
                refreshed = next((r for r in record if r.get("id") == entry.get("id")), {})
                if refreshed.get("dir_name"):
                    targets.append(papers_dir / refreshed["dir_name"] / "meta.json")
        targets = sorted(set(targets))
    elif args.all:
        targets = sorted(d / "meta.json" for d in iter_paper_dirs(papers_dir))
    elif args.paper_id:
        try:
            targets = [_resolve_paper(args.paper_id, cfg) / "meta.json"]
        except SystemExit:
            targets = [papers_dir / args.paper_id / "meta.json"]
    else:
        _log.error("请指定 <paper-id>、--workspace 或 --all")
        sys.exit(1)

    # Filter: only papers missing citations or bibliographic details (unless --force)
    if (args.all or getattr(args, "workspace", None)) and not args.force:
        filtered = []
        for jp in targets:
            data = json.loads(jp.read_text(encoding="utf-8"))
            if not data.get("doi"):
                continue
            missing_cite = not data.get("citation_count")
            missing_bib = not all(data.get(k) for k in ("volume", "publisher"))
            missing_refs = not data.get("references")
            if missing_cite or missing_bib or missing_refs:
                filtered.append(jp)
        scope = f"工作区 {args.workspace}" if getattr(args, "workspace", None) else "全库"
        ui(f"{scope}共 {len(targets)} 篇，{len(filtered)} 篇需要补全")
        targets = filtered

    if not targets:
        ui("无需更新")
        return

    # Filter out non-existent paths
    valid = []
    fail = 0
    for jp in targets:
        if jp.exists():
            valid.append(jp)
        else:
            _log.error("未找到论文: %s", jp.parent.name)
            fail += 1
    targets = valid

    ok = skip = 0
    total = len(targets)
    workers = min(getattr(args, "jobs", 5) or 5, total)
    ui(f"并发 refetch（{workers} workers，共 {total} 篇）...")

    def _do_refetch(jp: Path) -> tuple[Path, bool | None]:
        try:
            return jp, refetch_metadata(jp)
        except Exception as e:
            _log.error("refetch 失败 %s: %s", jp.parent.name, e)
            return jp, None

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_do_refetch, jp): jp for jp in targets}
        for fut in as_completed(futures):
            jp, changed = fut.result()
            done += 1
            name = jp.parent.name
            if changed is None:
                fail += 1
                ui(f"[{done}/{total}] ✗ {name}")
            elif changed:
                ok += 1
                ui(f"[{done}/{total}] ✓ {name}")
            else:
                skip += 1
                ui(f"[{done}/{total}] - {name}")

    ui(f"\n完成: {ok} 更新 | {skip} 无变化 | {fail} 失败")


def cmd_backfill_abstract(args: argparse.Namespace, cfg) -> None:
    from autor.ingest.metadata import backfill_abstracts

    papers_dir = cfg.papers_dir
    if not papers_dir.exists():
        _log.error("论文目录不存在: %s", papers_dir)
        sys.exit(1)

    action = "预览补全" if args.dry_run else "补全摘要"
    doi_fetch = getattr(args, "doi_fetch", False)
    source = "DOI 官方来源" if doi_fetch else "本地 .md + LLM 回退"
    ui(f"{action}摘要（{source}）...\n")
    stats = backfill_abstracts(papers_dir, dry_run=args.dry_run, doi_fetch=doi_fetch, cfg=cfg)
    parts = [f"{stats['filled']} 已补全", f"{stats['skipped']} 跳过", f"{stats['failed']} 失败"]
    if stats.get("updated"):
        parts.insert(1, f"{stats['updated']} 已更新为官方摘要")
    ui(f"\n完成: {' | '.join(parts)}")
    if stats["filled"] and not args.dry_run:
        _log.debug("consider rebuilding evidence index: autor index --rebuild")


def cmd_explore(args: argparse.Namespace, cfg) -> None:
    action = args.explore_action

    if action == "fetch":
        if args.limit is not None and args.limit <= 0:
            ui(f"--limit 必须为正整数，当前为: {args.limit}")
            return
        # Determine name: explicit --name, or derive from filters
        name = args.name
        if not name:
            if args.issn:
                name = args.issn.replace("-", "")
            elif args.concept:
                name = f"concept-{args.concept}"
            elif args.author:
                name = f"author-{args.author}"
            elif args.keyword:
                name = args.keyword.replace(" ", "-")[:30]
            else:
                ui("请提供 --name 或至少一个过滤条件")
                return
        from autor.explore import fetch_explore

        total = fetch_explore(
            name,
            issn=getattr(args, "issn", None),
            concept=getattr(args, "concept", None),
            topic=getattr(args, "topic_id", None),
            author=getattr(args, "author", None),
            institution=getattr(args, "institution", None),
            keyword=getattr(args, "keyword", None),
            source_type=getattr(args, "source_type", None),
            year_range=getattr(args, "year_range", None),
            min_citations=getattr(args, "min_citations", None),
            oa_type=getattr(args, "oa_type", None),
            incremental=getattr(args, "incremental", False),
            limit=getattr(args, "limit", None),
            cfg=cfg,
        )
        ui(f"\n已抓取 {total} 篇论文")

    elif action == "search":
        query = " ".join(args.query)
        top_k = _resolve_top(args, 10)
        from autor.explore import explore_search

        results = explore_search(args.name, query, top_k=top_k, cfg=cfg)
        if not results:
            ui("未找到结果。")
            return
        for i, r in enumerate(results, 1):
            authors = r.get("authors", [])
            first = authors[0] if authors else ""
            cited = r.get("cited_by_count", 0)
            cite_str = f"  [被引: {cited}]" if cited else ""
            ui(f"[{i}] [{r.get('year', '?')}] {r.get('title', '')}")
            ui(f"     {first} | {r.get('doi', '')}  (分数: {r['score']:.3f}){cite_str}")
            ui()

    elif action == "list":
        import json as _json

        explore_root = cfg._root / "data" / "explore"
        if not explore_root.exists():
            ui("暂无 explore 库，请先运行 autor explore fetch --issn <ISSN> 创建。")
            return
        for d in sorted(explore_root.iterdir()):
            if not d.is_dir():
                continue
            meta_file = d / "meta.json"
            if meta_file.exists():
                try:
                    meta = _json.loads(meta_file.read_text("utf-8"))
                except (OSError, _json.JSONDecodeError) as e:
                    ui(f"  {d.name}: meta.json 读取失败，已跳过（{e}）")
                    continue
                query = meta.get("query", {})
                if query:
                    qinfo = ", ".join(f"{k}={v}" for k, v in query.items())
                else:
                    qinfo = "?"
                ui(f"  {d.name}: {meta.get('count', '?')} 篇 ({qinfo}，抓取时间 {meta.get('fetched_at', '?')})")
        return

    elif action == "info":
        import json as _json

        if not args.name:
            # List all explore libraries
            explore_root = cfg._root / "data" / "explore"
            if not explore_root.exists():
                ui("暂无 explore 库，请先运行 autor explore fetch --issn <ISSN> 创建。")
                return
            for d in sorted(explore_root.iterdir()):
                if not d.is_dir():
                    continue
                meta_file = d / "meta.json"
                if meta_file.exists():
                    try:
                        meta = _json.loads(meta_file.read_text("utf-8"))
                    except (OSError, _json.JSONDecodeError) as e:
                        ui(f"  {d.name}: meta.json 读取失败，已跳过（{e}）")
                        continue
                    query = meta.get("query", {})
                    if query:
                        qinfo = ", ".join(f"{k}={v}" for k, v in query.items())
                    else:
                        qinfo = "?"
                    ui(f"  {d.name}: {meta.get('count', '?')} 篇 ({qinfo}，抓取时间 {meta.get('fetched_at', '?')})")
            return
        from autor.explore import count_papers

        meta_file = cfg._root / "data" / "explore" / args.name / "meta.json"
        if meta_file.exists():
            try:
                meta = _json.loads(meta_file.read_text("utf-8"))
            except (OSError, _json.JSONDecodeError) as e:
                ui(f"读取 {meta_file} 失败：{e}")
                return
            ui(f"Explore 库: {args.name}")
            for k, v in meta.items():
                ui(f"  {k}: {v}")
        else:
            n = count_papers(args.name, cfg=cfg)
            ui(f"Explore 库 {args.name}: {n} 篇论文")

    else:
        _log.error("未知操作: %s", action)
        sys.exit(1)


def cmd_rename(args: argparse.Namespace, cfg) -> None:
    from autor.ingest.metadata import rename_paper
    from autor.papers import iter_paper_dirs

    papers_dir = cfg.papers_dir

    if args.all:
        targets = sorted(d / "meta.json" for d in iter_paper_dirs(papers_dir))
    elif args.paper_id:
        targets = [papers_dir / args.paper_id / "meta.json"]
    else:
        _log.error("请指定 <paper-id> 或 --all")
        sys.exit(1)

    renamed = skip = fail = 0
    for json_path in targets:
        if not json_path.exists():
            _log.error("未找到论文: %s", json_path.parent.name)
            fail += 1
            continue

        new_path = rename_paper(json_path, dry_run=args.dry_run)
        if new_path:
            action = "预览" if args.dry_run else "重命名"
            ui(f"{action}: {json_path.parent.name} -> {new_path.parent.name}")
            renamed += 1
        else:
            skip += 1

    ui(f"\n完成: {renamed} 已重命名 | {skip} 未变化 | {fail} 失败")
    if renamed and not args.dry_run:
        _log.debug("consider rebuilding index: autor index --rebuild")


# ============================================================================
#  export
# ============================================================================


def cmd_export(args: argparse.Namespace, cfg) -> None:
    action = args.export_action
    if action == "bibtex":
        _cmd_export_bibtex(args, cfg)
    elif action == "ris":
        _cmd_export_ris(args, cfg)
    elif action == "markdown":
        _cmd_export_markdown(args, cfg)
    elif action == "docx":
        _cmd_export_docx(args, cfg)
    else:
        _log.error("未知导出操作: %s", action)
        sys.exit(1)


def _cmd_export_ris(args: argparse.Namespace, cfg) -> None:
    from autor.export import export_ris

    paper_ids = args.paper_ids if args.paper_ids else None
    if not paper_ids and not args.all:
        _log.error("请指定论文 ID 或 --all")
        sys.exit(1)

    ris = export_ris(
        cfg.papers_dir,
        paper_ids=paper_ids,
        year=args.year,
        journal=args.journal,
    )

    if not ris:
        ui("未找到匹配的论文")
        return

    if args.output:
        out = Path(args.output)
        out.write_text(ris, encoding="utf-8")
        count = ris.count("TY  -")
        ui(f"已导出到 {out}（{count} 篇）")
    else:
        print(ris)


def _cmd_export_markdown(args: argparse.Namespace, cfg) -> None:
    from autor.export import export_markdown_refs

    paper_ids = args.paper_ids if args.paper_ids else None
    if not paper_ids and not args.all:
        _log.error("请指定论文 ID 或 --all")
        sys.exit(1)

    style = getattr(args, "style", "apa") or "apa"

    try:
        md = export_markdown_refs(
            cfg.papers_dir,
            cfg=cfg,
            paper_ids=paper_ids,
            year=args.year,
            journal=args.journal,
            numbered=not args.bullet,
            style=style,
        )
    except (FileNotFoundError, ValueError, AttributeError, ImportError) as e:
        _log.error("%s", e)
        sys.exit(1)

    if not md:
        ui("未找到匹配的论文")
        return

    if args.output:
        out = Path(args.output)
        out.write_text(md, encoding="utf-8")
        count = md.count("\n")
        ui(f"已导出到 {out}（{count} 条引用，{style} 格式）")
    else:
        print(md)


def cmd_document(args: argparse.Namespace, cfg) -> None:
    action = getattr(args, "doc_action", None)
    if action == "inspect":
        _cmd_document_inspect(args, cfg)
    else:
        _log.error("请指定 document 子命令: inspect")
        sys.exit(1)


def cmd_plot(args: argparse.Namespace, cfg) -> None:
    from autor import workspace as workspace_mod
    from autor.plot import PlotError, generate_plot

    if args.workspace and not workspace_mod.validate_workspace_name(args.workspace):
        _log.error("非法工作区名称: %s", args.workspace)
        sys.exit(1)

    prompt = " ".join(args.prompt or []).strip()
    if args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if not prompt_path.exists():
            _log.error("prompt 文件不存在: %s", prompt_path)
            sys.exit(1)
        try:
            prompt = prompt_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            _log.error("读取 prompt 文件失败: %s", e)
            sys.exit(1)

    if not prompt:
        _log.error("请提供 prompt 文本或 --prompt-file")
        sys.exit(1)

    try:
        summary = generate_plot(
            prompt,
            cfg=cfg,
            workspace=args.workspace,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            name=args.name,
            urls=args.ref_url,
            host=args.host,
            api_key=args.api_key,
            model=args.model,
            aspect_ratio=args.aspect_ratio,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
        )
    except (OSError, PlotError, requests.RequestException) as e:
        _log.error("绘图失败: %s", e)
        sys.exit(1)

    files = summary.get("files") or []
    ui(f"已生成 {len(files)} 张图片")
    for file_path in files:
        ui(f"  - {file_path}")
    ui(f"任务 ID: {summary.get('id', '')}")
    ui(f"元数据: {summary.get('meta_file', '')}")


def _cmd_document_inspect(args: argparse.Namespace, cfg) -> None:
    from autor.document import inspect

    file_path = Path(args.file)
    if not file_path.exists():
        _log.error("文件不存在: %s", file_path)
        sys.exit(1)
    fmt = getattr(args, "format", None)
    try:
        result = inspect(file_path, fmt=fmt)
    except (ValueError, ImportError) as e:
        _log.error("%s", e)
        sys.exit(1)
    print(result)


def cmd_style(args: argparse.Namespace, cfg) -> None:
    """Dispatcher for `autor style` subcommands."""
    sub = getattr(args, "style_sub", None)
    if sub == "list":
        _cmd_style_list(args, cfg)
    elif sub == "show":
        _cmd_style_show(args, cfg)
    else:
        _log.error("请指定 style 子命令: list / show")
        sys.exit(1)


def _cmd_style_list(args: argparse.Namespace, cfg) -> None:
    from autor.citation_styles import list_styles

    styles = list_styles(cfg)
    ui(f"可用引用格式（共 {len(styles)} 种）：")
    for s in styles:
        tag = f"[{s['source']}]"
        desc = f" — {s['description']}" if s.get("description") else ""
        print(f"  {s['name']:<28} {tag:<10}{desc}")
    print()
    ui("用法：autor export markdown --all --style <name>")


def _cmd_style_show(args: argparse.Namespace, cfg) -> None:
    from autor.citation_styles import show_style

    try:
        code = show_style(args.name, cfg)
        print(code)
    except (FileNotFoundError, ValueError) as e:
        _log.error("%s", e)
        sys.exit(1)


def _cmd_export_docx(args: argparse.Namespace, cfg) -> None:
    from autor.export import export_docx

    # Determine input content
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            _log.error("输入文件不存在: %s", args.input)
            sys.exit(1)
        content = input_path.read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        _log.error("请通过 --input 指定 Markdown 文件，或通过 stdin 传入内容")
        sys.exit(1)

    output = Path(args.output) if args.output else cfg._root / "workspace" / "output.docx"

    try:
        export_docx(content, output, title=args.title or None)
        ui(f"已导出到 {output}")
    except ImportError as e:
        _log.error("%s", e)
        sys.exit(1)


def _cmd_export_bibtex(args: argparse.Namespace, cfg) -> None:
    from autor.export import export_bibtex

    paper_ids = args.paper_ids if args.paper_ids else None
    if args.workspace:
        from autor import workspace as workspace_mod

        if not workspace_mod.validate_workspace_name(args.workspace):
            _log.error("非法工作区名称: %s", args.workspace)
            sys.exit(1)
        ws_dir = cfg._root / "workspace" / args.workspace
        paper_ids = list(workspace_mod.read_dir_names(ws_dir, cfg.index_db))
        if not paper_ids:
            ui("工作区为空")
            return
    if not paper_ids and not args.all:
        _log.error("请指定论文 ID 或 --all")
        sys.exit(1)

    bib = export_bibtex(
        cfg.papers_dir,
        paper_ids=paper_ids,
        year=args.year,
        journal=args.journal,
    )

    if not bib:
        ui("未找到匹配的论文")
        return

    if args.output:
        out = Path(args.output)
        out.write_text(bib, encoding="utf-8")
        ui(f"已导出到 {out}（{bib.count('@')} 篇）")
    else:
        print(bib)


# ============================================================================
#  workspace
# ============================================================================


def cmd_identify(args: argparse.Namespace, cfg) -> None:
    """Check canonical PMIDs/DOIs against the local library and optional workspace."""
    import json
    import re

    from autor import workspace as workspace_mod
    from autor.index import lookup_paper

    identifiers: list[str] = []
    identifiers.extend(args.pmids or [])
    identifiers.extend(args.dois or [])

    for file_arg in [args.pmid_list, args.seed_file]:
        if not file_arg:
            continue
        text = Path(file_arg).read_text(encoding="utf-8")
        identifiers.extend(re.findall(r"\b\d{5,9}\b", text))
        identifiers.extend(re.findall(r"10\.\d{4,9}/[^\s,;\"'<>]+", text, flags=re.IGNORECASE))

    # Preserve order while removing duplicates.
    identifiers = list(dict.fromkeys(i.strip() for i in identifiers if i and i.strip()))
    if not identifiers:
        ui("未提供 PMID/DOI；请使用 --pmid、--doi、--pmid-list 或 --seed-file")
        return

    workspace_ids: set[str] | None = None
    if args.workspace:
        if not workspace_mod.validate_workspace_name(args.workspace):
            ui(f"非法工作区名称: {args.workspace}")
            return
        workspace_ids = workspace_mod.read_paper_ids(cfg._root / "workspace" / args.workspace)

    records: list[dict] = []
    missing: list[str] = []
    for ident in identifiers:
        record = lookup_paper(cfg.index_db, ident)
        if not record:
            missing.append(ident)
            continue
        payload = dict(record)
        payload["query"] = ident
        if workspace_ids is not None:
            payload["in_workspace"] = record["id"] in workspace_ids
        records.append(payload)

    result = {
        "count": len(identifiers),
        "found_count": len(records),
        "missing_count": len(missing),
        "workspace": args.workspace,
        "records": records,
        "missing": missing,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_ws(args: argparse.Namespace, cfg) -> None:
    from autor import workspace

    ws_root = cfg._root / "workspace"
    action = args.ws_action

    # Validate workspace-name style arguments in CLI layer to prevent path traversal.
    names_to_check: list[str] = []
    if action in {
        "init",
        "add",
        "remove",
        "show",
        "search",
        "export",
        "export-meta",
        "export-evidence",
        "status",
        "screen",
        "plan-package",
        "citation-coverage",
        "citation-network",
        "figure-status",
        "dedup",
    }:
        names_to_check.append(args.name)
    elif action == "rename":
        names_to_check.extend([args.old_name, args.new_name])

    for name in names_to_check:
        if not workspace.validate_workspace_name(name):
            ui(f"非法工作区名称: {name}")
            return

    if action == "init":
        ws_dir = ws_root / args.name
        workspace.create(ws_dir)
        ui(f"工作区已创建: {ws_dir}")

    elif action == "add":
        ws_dir = ws_root / args.name
        if not (ws_dir / "papers.json").exists():
            workspace.create(ws_dir)

        # Resolve paper_refs from batch flags or positional args
        paper_refs = args.paper_refs or []
        if args.add_all:
            import sqlite3

            index_db_path = Path(cfg.index_db)
            if not index_db_path.exists():
                ui("索引数据库不存在，可能尚未初始化。")
                ui("请先运行: autor index")
                return

            try:
                with sqlite3.connect(cfg.index_db) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT id, dir_name FROM papers_registry").fetchall()
            except sqlite3.OperationalError as e:
                _log.debug("索引数据库查询失败: %s", e)
                ui("索引数据库结构不完整或尚未初始化。")
                ui("请先运行: autor index")
                return

            resolved = [{"id": r["id"], "dir_name": r["dir_name"]} for r in rows]
            if not resolved:
                ui("主库中没有论文")
                return
            if args.scope_filter:
                resolved, rejected = workspace.filter_resolved_by_scope(
                    resolved,
                    cfg.papers_dir,
                    args.scope_filter,
                    cfg=cfg,
                )
                ui(f"范围过滤: 保留 {len(resolved)} 篇，排除 {len(rejected)} 篇")
                for e in rejected:
                    ui(f"  ! {e['dir_name']} [{e.get('scope_decision')}: {e.get('scope_reason')}]")
            added = workspace.add(ws_dir, [], cfg.index_db, resolved=resolved)
            ui(f"已添加 {len(added)} 篇论文到 {args.name}")
            for e in added:
                ui(f"  + {e['dir_name']}")
            return
        elif args.add_search is not None:
            from autor.index import search

            results = search(
                args.add_search,
                cfg.index_db,
                top_k=_resolve_top(args, cfg.search.top_k),
                cfg=cfg,
                year=getattr(args, "year", None),
                journal=getattr(args, "journal", None),
                paper_type=getattr(args, "paper_type", None),
            )
            if not results:
                ui(f'未找到 "{args.add_search}" 的结果')
                return
            paper_refs = [r["paper_id"] for r in results]
            ui(f'搜索 "{args.add_search}": 找到 {len(paper_refs)} 篇论文')

        if not paper_refs:
            ui("未指定论文引用")
            return

        if args.scope_filter:
            from autor.index import lookup_paper

            resolved = []
            for ref in paper_refs:
                record = lookup_paper(cfg.index_db, ref)
                if not record:
                    ui(f"无法解析论文引用: {ref}")
                    continue
                resolved.append({"id": record["id"], "dir_name": record["dir_name"]})
            resolved, rejected = workspace.filter_resolved_by_scope(
                resolved,
                cfg.papers_dir,
                args.scope_filter,
                cfg=cfg,
            )
            ui(f"范围过滤: 保留 {len(resolved)} 篇，排除 {len(rejected)} 篇")
            for e in rejected:
                ui(f"  ! {e['dir_name']} [{e.get('scope_decision')}: {e.get('scope_reason')}]")
            added = workspace.add(ws_dir, [], cfg.index_db, resolved=resolved)
        else:
            added = workspace.add(ws_dir, paper_refs, cfg.index_db)
        ui(f"已添加 {len(added)} 篇论文到 {args.name}")
        for e in added:
            ui(f"  + {e['dir_name']}")

    elif action == "remove":
        ws_dir = ws_root / args.name
        removed = workspace.remove(ws_dir, args.paper_refs, cfg.index_db)
        ui(f"已移除 {len(removed)} 篇论文")
        for e in removed:
            ui(f"  - {e['dir_name']}")

    elif action == "list":
        names = workspace.list_workspaces(ws_root)
        if not names:
            ui("没有工作区")
            return
        for name in names:
            ws_dir = ws_root / name
            ids = workspace.read_paper_ids(ws_dir)
            ui(f"  {name}（{len(ids)} 篇论文）")

    elif action == "dedup":
        ws_dir = ws_root / args.name
        result = workspace.dedup(ws_dir, cfg.index_db)
        ui(f"工作区清理完成: 保留 {result['kept_count']} 篇，移除 {result['removed_count']} 条")
        for e in result["removed"]:
            ui(f"  - {e.get('dir_name', e.get('id'))} [{e.get('dedup_reason')}]")

    elif action == "show":
        ws_dir = ws_root / args.name
        papers = workspace.show(ws_dir, cfg.index_db)
        ui(f"工作区 {args.name}: {len(papers)} 篇论文")
        for i, p in enumerate(papers, 1):
            ui(f"  {i:3d}. {p['dir_name']}")

    elif action == "status":
        ws_dir = ws_root / args.name
        payload = workspace.status(ws_dir, cfg.papers_dir, cfg.index_db, include_papers=args.papers)
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    elif action == "export-meta":
        ws_dir = ws_root / args.name
        rows = workspace.export_metadata(ws_dir, cfg.papers_dir, cfg.index_db)
        if not rows:
            ui("工作区为空，或未找到可导出的元信息")
            return
        try:
            payload = workspace.dump_metadata(rows, fmt=args.format)
        except ValueError as e:
            _log.error("%s", e)
            sys.exit(1)

        if args.output:
            out = Path(args.output)
            out.write_text(payload, encoding="utf-8")
            ui(f"已导出到 {out}（{len(rows)} 篇，{args.format}）")
        else:
            print(payload, end="")

    elif action == "export-evidence":
        ws_dir = ws_root / args.name
        rows = workspace.export_evidence(ws_dir, cfg.papers_dir, cfg.index_db)
        payload = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            out = Path(args.output)
            out.write_text(payload, encoding="utf-8")
            ui(f"已导出到 {out}（{len(rows)} 篇，evidence json）")
        else:
            print(payload, end="")

    elif action == "screen":
        ws_dir = ws_root / args.name
        criteria = args.criteria or ""
        if args.criteria_file:
            criteria = Path(args.criteria_file).read_text(encoding="utf-8")
        if not criteria.strip():
            ui("请提供 --criteria 或 --criteria-file")
            return
        result = workspace.screen(
            ws_dir,
            cfg.papers_dir,
            cfg.index_db,
            criteria=criteria,
            target_count=args.target,
            apply=args.apply,
        )
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            out = Path(args.output)
            out.write_text(payload, encoding="utf-8")
            ui(f"筛选结果已写入: {out}")
        else:
            print(payload, end="")

    elif action == "plan-package":
        ws_dir = ws_root / args.name
        criteria = args.criteria or ""
        if args.criteria_file:
            criteria = Path(args.criteria_file).read_text(encoding="utf-8")
        result = workspace.generate_planning_package(
            ws_dir,
            cfg.papers_dir,
            cfg.index_db,
            title=args.title,
            criteria=criteria,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif action == "citation-coverage":
        ws_dir = ws_root / args.name
        manuscript = Path(args.manuscript) if args.manuscript else None
        result = workspace.citation_coverage(ws_dir, manuscript, require=args.require)
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            out = Path(args.output)
            out.write_text(payload, encoding="utf-8")
            ui(f"引用覆盖检查已写入: {out}")
        else:
            print(payload, end="")
        if args.fail_if_missing and (result["missing_required_count"] or result["unknown_citekeys"]):
            raise SystemExit(2)

    elif action == "citation-network":
        ws_dir = ws_root / args.name
        result = workspace.citation_network(ws_dir, cfg.index_db, min_shared=args.min_shared)
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            out = Path(args.output)
        else:
            out = ws_dir / "sidecars" / "citation-network.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        ui(f"引用网络已写入: {out}")
        ui(
            "状态: {status} | 参考边 {edges} | 库内边 {internal} | 共引节点 {shared}".format(
                status=result["status"],
                edges=result["summary"]["reference_edge_count"],
                internal=result["summary"]["internal_edge_count"],
                shared=result["summary"]["shared_reference_count"],
            )
        )
        if args.print_json:
            print(payload, end="")

    elif action == "figure-status":
        ws_dir = ws_root / args.name
        result = workspace.figure_status(ws_dir)
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            out = Path(args.output)
            out.write_text(payload, encoding="utf-8")
            ui(f"图片检查已写入: {out}")
        else:
            print(payload, end="")
        if args.fail_if_missing and result["missing_count"]:
            raise SystemExit(2)

    elif action == "search":
        ws_dir = ws_root / args.name
        pids = workspace.read_paper_ids(ws_dir)
        if not pids:
            ui("工作区为空")
            return
        query = " ".join(args.query)
        top_k = _resolve_top(args, cfg.search.top_k)

        from autor.index import search as kw_search

        results = kw_search(
            query,
            cfg.index_db,
            top_k=top_k,
            cfg=cfg,
            year=args.year,
            journal=args.journal,
            paper_type=args.paper_type,
            paper_ids=pids,
        )

        if not results:
            ui(f'工作区 {args.name} 中未找到 "{query}" 的结果')
            return
        ui(f"工作区 {args.name} 中找到 {len(results)} 篇:\n")
        for i, r in enumerate(results, 1):
            match = r.get("match")
            extra = _format_match_tag(match) if match else ""
            _print_search_result(i, r, extra=extra)
        _print_search_next_steps(include_ws_add=False)

    elif action == "export":
        ws_dir = ws_root / args.name
        dir_names = workspace.read_dir_names(ws_dir, cfg.index_db)
        if not dir_names:
            ui("工作区为空")
            return
        from autor.export import export_bibtex

        bib = export_bibtex(
            cfg.papers_dir,
            paper_ids=list(dir_names),
            year=args.year,
            journal=args.journal,
            paper_type=args.paper_type,
        )
        if not bib:
            ui("未找到匹配的论文")
            return
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(bib, encoding="utf-8")
            ui(f"已导出到 {out}（{bib.count('@')} 篇）")
        else:
            print(bib)

    elif action == "rename":
        try:
            workspace.rename(ws_root, args.old_name, args.new_name)
        except (ValueError, FileNotFoundError, FileExistsError) as e:
            ui(str(e))
            return
        ui(f"工作区已重命名: {args.old_name} → {args.new_name}")


# ============================================================================
#  fsearch (federated search)
# ============================================================================


def _search_arxiv(query: str, top_k: int) -> list[dict]:
    """Call arXiv Atom API, return simplified paper dicts."""
    from autor.sources.arxiv import search_arxiv

    return search_arxiv(query, top_k)


def _query_dois_for_set(cfg, doi_set: list[str]) -> set[str]:
    """Return the subset of doi_set that exists in the main library (case-insensitive).

    Only queries the specific DOIs requested, so this is O(len(doi_set)) regardless
    of library size. Returns an empty set if the index DB is missing or on any error.
    """
    import sqlite3

    if not doi_set or not Path(cfg.index_db).exists():
        return set()
    try:
        normalized = [d.lower() for d in doi_set]
        placeholders = ",".join("?" * len(normalized))
        with sqlite3.connect(str(cfg.index_db)) as conn:
            rows = conn.execute(
                f"SELECT doi FROM papers_registry WHERE LOWER(doi) IN ({placeholders})",
                normalized,
            ).fetchall()
        return {r[0].lower() for r in rows}
    except Exception:
        return set()


def cmd_fsearch(args: argparse.Namespace, cfg) -> None:
    query = " ".join(args.query)
    top_k = _resolve_top(args, 10)
    scope_str = args.scope or "main"
    scopes = [s.strip() for s in scope_str.split(",") if s.strip()] or ["main"]

    ui(f'联邦搜索: "{query}"  scope={scope_str}\n')

    for scope in scopes:
        if scope == "main":
            ui("── [主库] ──")
            if not cfg.index_db.exists():
                ui("  主库索引不存在，请先运行 autor index")
                results = []
            else:
                from autor.index import search

                try:
                    results = search(query, cfg.index_db, top_k=top_k, cfg=cfg)
                except Exception as e:
                    ui(f"  主库搜索失败：{e}")
                    results = []
            if not results:
                ui("  无结果")
            else:
                for i, r in enumerate(results, 1):
                    score = r.get("score", 0.0)
                    _print_search_result(i, r, extra=f"{_format_match_tag(r.get('match', '?'))} {score:.3f}")
            ui()

        elif scope.startswith("explore:"):
            explore_name = scope[len("explore:") :]
            from autor.explore import validate_explore_name

            if explore_name != "*" and not validate_explore_name(explore_name):
                ui(f"  无效的 explore 库名 '{explore_name}'：不能为空，且不能包含路径分隔符或 '..'")
                ui()
                continue
            if explore_name == "*":
                from autor.explore import list_explore_libs

                names = list_explore_libs(cfg)
                if not names:
                    ui("── [explore: *] ──")
                    ui("  暂无 explore 库，请先运行 autor explore fetch --name <名称>")
                    ui()
            else:
                names = [explore_name]

            for name in names:
                ui(f"── [explore: {name}] ──")
                from autor.explore import explore_db_path, explore_search

                db = explore_db_path(name, cfg)
                if not db.exists():
                    ui(f"  explore 库 {name} 不存在或未建索引（explore.db 缺失）")
                    ui()
                    continue
                try:
                    results = explore_search(name, query, top_k=top_k, cfg=cfg)
                except Exception as e:
                    ui(f"  搜索失败: {e}")
                    ui()
                    continue
                if not results:
                    ui("  无结果")
                else:
                    for i, r in enumerate(results, 1):
                        authors = r.get("authors", [])
                        first = authors[0] if authors else "?"
                        score = r.get("score", 0.0)
                        ui(f"  [{i}] [{r.get('year', '?')}] {r.get('title', '')}")
                        ui(f"       {first} | 分数: {score:.3f}")
                        ui()

        elif scope == "arxiv":
            ui("── [arXiv] ──")
            arxiv_results = _search_arxiv(query, top_k)
            if not arxiv_results:
                ui("  arXiv 不可用或无结果")
            else:
                # Only query the library for DOIs that actually appear in results
                arxiv_dois = [r["doi"].lower() for r in arxiv_results if r.get("doi")]
                in_lib_dois = _query_dois_for_set(cfg, arxiv_dois)
                for i, r in enumerate(arxiv_results, 1):
                    authors = r.get("authors", [])
                    first = (authors[0] if authors else "?") + (" et al." if len(authors) > 1 else "")
                    doi = r.get("doi", "")
                    in_lib = bool(doi and doi.lower() in in_lib_dois)
                    status = "  [已入库]" if in_lib else ""
                    ui(f"  [{i}] [{r.get('year', '?')}] {r.get('title', '')}{status}")
                    ui(f"       {first} | arxiv:{r.get('arxiv_id', '')}" + (f" | doi:{doi}" if doi else ""))
                    ui()

        else:
            ui(f"  未知 scope: {scope}，支持: main / explore:NAME / explore:* / arxiv")


# ============================================================================
#  insights
# ============================================================================


def cmd_insights(args: argparse.Namespace, cfg) -> None:
    import json as _json
    from collections import Counter
    from datetime import datetime, timedelta, timezone

    from autor.metrics import get_store

    store = get_store()
    if not store:
        ui("暂无足够数据（metrics 未初始化）")
        return

    days = args.days
    if days <= 0:
        ui("--days 必须为正整数")
        return
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since_iso = since_dt.isoformat()

    # Fetch search events
    search_events = store.query(category="search", since=since_iso, limit=10000)
    # Fetch read events
    read_events = store.query(category="read", since=since_iso, limit=10000)

    if not search_events and not read_events:
        ui(f"暂无足够数据（过去 {days} 天内无搜索或阅读记录）")
        return

    ui(f"=== 科研行为分析（过去 {days} 天）===\n")

    # 1. Top 10 search keywords
    _STOPWORDS = {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "by",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "have",
        "has",
        "do",
        "does",
        "this",
        "that",
        "it",
        "its",
        "from",
        "as",
        "via",
        "using",
        "based",
    }
    word_counts: Counter = Counter()
    for ev in search_events:
        detail_raw = ev.get("detail") or ""
        if detail_raw:
            try:
                detail = _json.loads(detail_raw)
                q = detail.get("query", "")
            except Exception:
                q = ""
        else:
            q = ""
        if q:
            for w in q.lower().split():
                w = w.strip("\"',.:;!?()[]{}")
                if w and w not in _STOPWORDS and len(w) > 1:
                    word_counts[w] += 1

    ui("【搜索热词前 10】")
    if word_counts:
        for word, cnt in word_counts.most_common(10):
            bar = "█" * min(cnt, 20)
            ui(f"  {word:<20s} {bar} ({cnt})")
    else:
        ui("  暂无搜索记录")
    ui()

    # 2. Top 10 most-read papers — aggregate by resolved title to dedup UUID vs dir_name variants
    # First pass: count by name and collect one detail payload per name (cheaply).
    papers_dir = cfg.papers_dir
    name_counts: Counter = Counter()
    name_to_detail_title: dict[str, str] = {}  # title from recorded detail (fast)

    for ev in read_events:
        name = ev.get("name", "")
        if not name:
            continue
        name_counts[name] += 1
        if name not in name_to_detail_title and ev.get("detail"):
            try:
                d = _json.loads(ev["detail"])
                t = d.get("title", "")
                if t:
                    name_to_detail_title[name] = t
            except Exception:
                pass

    # Build title map for ALL names using already-recorded detail.title (zero disk I/O).
    # This ensures the aggregation below correctly merges UUID/dir_name variants for any paper.
    pid_to_title: dict[str, str] = dict(name_to_detail_title)

    # Disk reads only for the top-10 names still missing a title (≤10 reads total).
    for name, _ in name_counts.most_common(10):
        if not pid_to_title.get(name):
            meta_path = papers_dir / name / "meta.json"
            if meta_path.exists():
                try:
                    meta = _json.loads(meta_path.read_text("utf-8"))
                    t = meta.get("title", "")
                    if t:
                        pid_to_title[name] = t
                except Exception:
                    pass

    title_read_counts: Counter = Counter()
    for name, cnt in name_counts.items():
        title_key = pid_to_title.get(name) or name
        title_read_counts[title_key] += cnt

    ui("【最常阅读论文前 10】")
    if title_read_counts:
        for rank, (title_key, cnt) in enumerate(title_read_counts.most_common(10), 1):
            label = title_key[:60]
            ui(f"  {rank:2d}. [{cnt}次] {label}")
    else:
        ui("  暂无阅读记录")
    ui()

    # 3. Weekly read-count trend (ASCII bar chart)
    ui("【阅读量趋势（按周）】")
    if read_events:
        week_counts: Counter = Counter()
        for ev in read_events:
            ts = ev.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    week_key = dt.strftime("%Y-W%W")
                    week_counts[week_key] += 1
                except Exception:
                    pass
        if week_counts:
            max_count = max(week_counts.values()) or 1
            for week in sorted(week_counts):
                cnt = week_counts[week]
                bar_len = round(cnt / max_count * 20)
                bar = "█" * bar_len
                ui(f"  {week}  {bar} {cnt}")
        else:
            ui("  暂无足够数据")
    else:
        ui("  暂无阅读记录")
    ui()

    # 4. Recommend adjacent papers not yet read (based on recent title/abstract terms)
    ui("【推荐：你可能还没读过的邻近论文】")
    recent_since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_reads = store.query(category="read", since=recent_since, limit=500)
    # Preserve recency order (store.query returns newest-first); deduplicate while keeping order.
    _seen: set[str] = set()
    recent_paper_ids = []
    for ev in recent_reads:
        n = ev.get("name")
        if n and n not in _seen:
            _seen.add(n)
            recent_paper_ids.append(n)

    if not recent_paper_ids:
        ui("  过去7天无阅读记录，无法推荐")
    else:
        # Use all-time read history so papers read outside the current window
        # are not mistakenly recommended as "not yet read".
        all_read_pids = store.query_distinct_names("read")
        try:
            from autor.index import search as evidence_search

            candidate_scores: dict[str, float] = {}
            for pid in recent_paper_ids[:5]:  # limit to avoid slow search
                paper_d = cfg.papers_dir / pid
                meta_path = paper_d / "meta.json"
                if not meta_path.exists():
                    continue
                try:
                    meta = _json.loads(meta_path.read_text("utf-8"))
                    title = meta.get("title", "")
                    abstract = meta.get("abstract", "")
                    query_text = f"{title}\n{abstract}".strip()
                    if not query_text:
                        continue
                except Exception:
                    continue
                try:
                    neighbors = evidence_search(query_text, cfg.index_db, top_k=10, cfg=cfg)
                except Exception:
                    continue
                for r in neighbors:
                    n_pid = r.get("dir_name") or r.get("paper_id", "")
                    if n_pid and n_pid not in all_read_pids:
                        score = r.get("score", 0.0)
                        if n_pid not in candidate_scores or candidate_scores[n_pid] < score:
                            candidate_scores[n_pid] = score
            if candidate_scores:
                sorted_candidates = sorted(candidate_scores.items(), key=lambda x: -x[1])[:5]
                for rank, (pid, score) in enumerate(sorted_candidates, 1):
                    title = ""
                    paper_d = cfg.papers_dir / pid
                    meta_path = paper_d / "meta.json"
                    if meta_path.exists():
                        try:
                            meta = _json.loads(meta_path.read_text("utf-8"))
                            title = meta.get("title", "")
                        except Exception:
                            pass
                    label = title[:60] if title else pid
                    ui(f"  {rank}. {label}  (分数: {score:.3f})")
            else:
                ui("  未找到合适的邻近论文")
        except ImportError:
            ui("  检索模块不可用")
    ui()

    # 5. Active workspaces — list workspaces with paper counts
    ui("【活跃工作区】")
    try:
        import json as _json2

        from autor.workspace import list_workspaces

        ws_root = cfg._root / "workspace"
        ws_names = list_workspaces(ws_root)
        if ws_names:
            for ws_name in ws_names:
                papers_json = ws_root / ws_name / "papers.json"
                try:
                    count = len(_json2.loads(papers_json.read_text("utf-8")))
                except Exception:
                    count = 0
                ui(f"  {ws_name:<30s} {count} 篇论文")
        else:
            ui("  暂无工作区")
    except Exception:
        ui("  工作区信息不可用")
    ui()


# ============================================================================
#  metrics
# ============================================================================


def cmd_metrics(args: argparse.Namespace, cfg) -> None:
    from autor.metrics import get_store

    store = get_store()
    if not store:
        _log.error("Metrics 数据库尚未初始化。")
        return

    if args.summary:
        s = store.summary()
        ui("LLM 调用统计（全部会话）：")
        ui(f"  调用次数:      {s['call_count']}")
        ui(f"  输入 tokens:   {s['total_tokens_in']:,}")
        ui(f"  输出 tokens:   {s['total_tokens_out']:,}")
        ui(f"  总 tokens:     {s['total_tokens_in'] + s['total_tokens_out']:,}")
        ui(f"  总耗时:        {s['total_duration_s']:.1f}s")
        return

    rows = store.query(
        category=args.category,
        since=args.since,
        limit=args.last,
    )
    if not rows:
        ui("没有记录。")
        return

    # Header
    if args.category == "llm":
        ui(f"{'time':<20s} {'purpose':<24s} {'prompt':>8s} {'compl':>8s} {'total':>8s} {'time':>7s} {'status':<5s}")
        ui("-" * 82)
        total_in = total_out = 0
        for r in reversed(rows):
            ts = r["timestamp"][:19].replace("T", " ")
            name = r["name"][:24]
            t_in = r["tokens_in"] or 0
            t_out = r["tokens_out"] or 0
            dur = r["duration_s"] or 0
            total_in += t_in
            total_out += t_out
            ui(f"{ts:<20s} {name:<24s} {t_in:>8,d} {t_out:>8,d} {t_in + t_out:>8,d} {dur:>6.1f}s {r['status']:<5s}")
        ui("-" * 82)
        ui(f"{'total':<20s} {'':<24s} {total_in:>8,d} {total_out:>8,d} {total_in + total_out:>8,d}")
    else:
        ui(f"{'time':<20s} {'name':<32s} {'time':>7s} {'status':<5s}")
        ui("-" * 66)
        for r in reversed(rows):
            ts = r["timestamp"][:19].replace("T", " ")
            name = r["name"][:32]
            dur = r["duration_s"] or 0
            ui(f"{ts:<20s} {name:<32s} {dur:>6.1f}s {r['status']:<5s}")


def cmd_setup(args: argparse.Namespace, cfg) -> None:
    from autor.setup import format_check_results, run_check, run_wizard

    action = getattr(args, "setup_action", None)
    if action == "check":
        lang = getattr(args, "lang", "zh")
        results = run_check(cfg, lang)
        ui(format_check_results(results))
    else:
        run_wizard(cfg)


def cmd_migrate_dirs(args: argparse.Namespace, cfg) -> None:
    from autor.migrate import migrate_to_dirs

    dry_run = not args.execute
    stats = migrate_to_dirs(cfg.papers_dir, dry_run=dry_run)
    mode = "dry-run" if dry_run else "executed"
    ui(f"\n迁移完成 ({mode}): {stats['migrated']} 迁移 | {stats['skipped']} 跳过 | {stats['failed']} 失败")
    if dry_run and stats["migrated"]:
        ui("添加 --execute 以实际执行迁移")
    if not dry_run and stats["migrated"]:
        ui("请运行 `autor pipeline reindex` 重建索引")


def cmd_import_endnote(args: argparse.Namespace, cfg) -> None:
    try:
        from autor.sources.endnote import parse_endnote_full
    except ImportError as e:
        _check_import_error(e)

    from autor.ingest.pipeline import import_external

    paths = [Path(f) for f in args.files]
    for p in paths:
        if not p.exists():
            ui(f"错误：文件不存在: {p}")
            sys.exit(1)

    records, pdf_paths = parse_endnote_full(paths)
    if not records:
        ui("未解析到任何记录")
        return

    n_pdfs = sum(1 for p in pdf_paths if p is not None)
    if n_pdfs:
        ui(f"解析到 {len(records)} 条记录，{n_pdfs} 个可匹配 PDF")
    else:
        ui(f"解析到 {len(records)} 条记录")

    stats = import_external(
        records,
        cfg,
        pdf_paths=pdf_paths,
        no_api=args.no_api,
        dry_run=args.dry_run,
    )

    # Batch convert PDFs → paper.md via MinerU + enrich (toc/l3/abstract)
    if not args.dry_run and not args.no_convert and stats["ingested"] > 0:
        _batch_convert_pdfs(cfg, enrich=True)


def _batch_convert_pdfs(cfg, *, enrich: bool = False) -> None:
    """Convert all unprocessed PDFs in papers_dir to paper.md via MinerU."""
    from autor.ingest.pipeline import batch_convert_pdfs

    batch_convert_pdfs(cfg, enrich=enrich)


def cmd_import_zotero(args: argparse.Namespace, cfg) -> None:
    import tempfile

    # Resolve credentials
    api_key = args.api_key or cfg.resolved_zotero_api_key()
    library_id = args.library_id or cfg.resolved_zotero_library_id()
    library_type = args.library_type or cfg.zotero.library_type

    # Local SQLite mode
    if args.local:
        db_path = Path(args.local)
        if not db_path.exists():
            ui(f"错误：Zotero 数据库不存在: {db_path}")
            sys.exit(1)

        from autor.sources.zotero import list_collections_local, parse_zotero_local

        if args.list_collections:
            collections = list_collections_local(db_path)
            if not collections:
                ui("没有找到 collections")
                return
            ui(f"{'Key':<12} {'Items':>5}  Name")
            ui("-" * 50)
            for c in collections:
                ui(f"{c['key']:<12} {c['numItems']:>5}  {c['name']}")
            return

        records, pdf_paths = parse_zotero_local(
            db_path,
            collection_key=args.collection,
            item_types=args.item_type,
        )
    else:
        # Web API mode
        if not api_key:
            ui("错误：需要 Zotero API key（--api-key 或 config.local.yaml zotero.api_key 或 ZOTERO_API_KEY 环境变量）")
            sys.exit(1)
        if not library_id:
            ui(
                "错误：需要 Zotero library ID（--library-id 或 config.local.yaml zotero.library_id 或 ZOTERO_LIBRARY_ID 环境变量）"
            )
            sys.exit(1)

        try:
            from autor.sources.zotero import fetch_zotero_api, list_collections_api
        except ImportError as e:
            _check_import_error(e)

        if args.list_collections:
            collections = list_collections_api(library_id, api_key, library_type=library_type)
            if not collections:
                ui("没有找到 collections")
                return
            ui(f"{'Key':<12} {'Items':>5}  Name")
            ui("-" * 50)
            for c in collections:
                ui(f"{c['key']:<12} {c['numItems']:>5}  {c['name']}")
            return

        download_pdfs = not args.no_pdf
        pdf_dir = Path(tempfile.mkdtemp(prefix="autor_zotero_")) if download_pdfs else None

        records, pdf_paths = fetch_zotero_api(
            library_id,
            api_key,
            library_type=library_type,
            collection_key=args.collection,
            item_types=args.item_type,
            download_pdfs=download_pdfs,
            pdf_dir=pdf_dir,
        )

    if not records:
        ui("未获取到任何记录")
        return

    n_pdfs = sum(1 for p in pdf_paths if p is not None)
    if n_pdfs:
        ui(f"获取到 {len(records)} 条记录，{n_pdfs} 个 PDF")
    else:
        ui(f"获取到 {len(records)} 条记录")

    from autor.ingest.pipeline import import_external

    stats = import_external(
        records,
        cfg,
        pdf_paths=pdf_paths,
        no_api=args.no_api,
        dry_run=args.dry_run,
    )

    # Batch convert PDFs → paper.md via MinerU + enrich (toc/l3/abstract)
    if not args.dry_run and not args.no_convert and stats["ingested"] > 0:
        _batch_convert_pdfs(cfg, enrich=True)

    # Import collections as workspaces
    if args.import_collections and not args.dry_run:
        _import_zotero_collections_as_workspaces(args, cfg, api_key, library_id, library_type)


def _import_zotero_collections_as_workspaces(args, cfg, api_key, library_id, library_type):
    """Create workspaces from Zotero collections after import."""

    from autor import workspace
    from autor.papers import iter_paper_dirs

    if args.local:
        from autor.sources.zotero import list_collections_local, parse_zotero_local

        collections = list_collections_local(Path(args.local))
    else:
        from autor.sources.zotero import list_collections_api

        collections = list_collections_api(library_id, api_key, library_type=library_type)

    # Build DOI → UUID map from existing papers
    from autor.papers import read_meta

    doi_to_uuid: dict[str, str] = {}
    for pdir in iter_paper_dirs(cfg.papers_dir):
        try:
            meta = read_meta(pdir)
        except (ValueError, FileNotFoundError):
            continue
        if meta.get("doi") and meta.get("id"):
            doi_to_uuid[meta["doi"].lower()] = meta["id"]

    ws_root = cfg._root / "workspace"
    for coll in collections:
        name = coll["name"].replace("/", "-").replace(" ", "_")
        ws_dir = ws_root / name

        # Get papers in this collection
        if args.local:
            coll_records, _ = parse_zotero_local(
                Path(args.local),
                collection_key=coll["key"],
            )
        else:
            from autor.sources.zotero import fetch_zotero_api

            coll_records, _ = fetch_zotero_api(
                library_id,
                api_key,
                library_type=library_type,
                collection_key=coll["key"],
                download_pdfs=False,
            )

        # Match to ingested papers by DOI
        uuids = []
        for r in coll_records:
            if r.doi and r.doi.lower() in doi_to_uuid:
                uuids.append(doi_to_uuid[r.doi.lower()])

        if not uuids:
            continue

        workspace.create(ws_dir)
        workspace.add(ws_dir, uuids, cfg.index_db)
        ui(f"工作区 {name}: {len(uuids)} 篇论文")


def cmd_attach_pdf(args: argparse.Namespace, cfg) -> None:
    import shutil

    paper_d = _resolve_paper(args.paper_id, cfg)
    pdf_path = Path(args.pdf_path)

    if not pdf_path.exists():
        ui(f"错误：PDF 文件不存在: {pdf_path}")
        sys.exit(1)

    existing_md = paper_d / "paper.md"
    dry_run = getattr(args, "dry_run", False)

    if dry_run:
        ui(f"[dry-run] 论文目录: {paper_d}")
        ui(f"[dry-run] PDF 来源: {pdf_path}")
        ui(f"[dry-run] 目标 paper.md: {paper_d / 'paper.md'}")
        if existing_md.exists():
            ui("[dry-run] 警告：已有 paper.md，实际运行时将被覆盖")
        ui("[dry-run] 将执行: MinerU 转换 → 摘要补全 → L3 结论提取 → 更新 FTS5 索引")
        ui("[dry-run] 如确认无误，去掉 --dry-run 参数再运行")
        return

    if existing_md.exists():
        ui(f"警告：{paper_d.name} 已有 paper.md，将被覆盖")

    # Copy PDF to paper directory
    dest_pdf = paper_d / pdf_path.name
    shutil.copy2(str(pdf_path), str(dest_pdf))
    ui(f"已复制 PDF: {dest_pdf.name}")

    # Convert PDF → markdown via MinerU
    from autor.ingest.mineru import ConvertOptions, check_server, convert_pdf, strip_markdown_images

    mineru_opts = ConvertOptions(
        api_url=cfg.ingest.mineru_endpoint,
        output_dir=paper_d,
        backend=cfg.ingest.mineru_backend_local,
        cloud_model_version=cfg.ingest.mineru_model_version_cloud,
        lang=cfg.ingest.mineru_lang,
        parse_method=cfg.ingest.mineru_parse_method,
        formula_enable=cfg.ingest.mineru_enable_formula,
        table_enable=cfg.ingest.mineru_enable_table,
    )

    if check_server(cfg.ingest.mineru_endpoint):
        result = convert_pdf(dest_pdf, mineru_opts)
    else:
        api_keys = cfg.resolved_mineru_api_keys()
        if not api_keys:
            ui("错误：MinerU 不可达且无云 API key")
            sys.exit(1)
        from autor.ingest.mineru import convert_pdf_cloud

        result = convert_pdf_cloud(
            dest_pdf,
            mineru_opts,
            api_key=api_keys[0],
            cloud_url=cfg.ingest.mineru_cloud_url,
        )

    if not result.success:
        ui(f"MinerU 转换失败: {result.error}")
        sys.exit(1)

    # Move/rename output to paper.md
    if result.md_path and result.md_path != existing_md:
        if existing_md.exists():
            existing_md.unlink()
        shutil.move(str(result.md_path), str(existing_md))
    if existing_md.exists():
        existing_md.write_text(strip_markdown_images(existing_md.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")

    # Clean up MinerU artifacts; images are not retained.
    for pattern in ["*_layout.json", "*_content_list.json", "*_origin.pdf"]:
        for f in paper_d.glob(pattern):
            f.unlink(missing_ok=True)
    for img_dir in list(paper_d.glob("*_images")) + list(paper_d.glob("*_mineru_images")) + [paper_d / "images"]:
        if img_dir.is_dir():
            shutil.rmtree(img_dir)

    # Clean up the copied PDF (we only need the markdown)
    if dest_pdf.exists() and dest_pdf.name != "paper.pdf":
        dest_pdf.unlink()

    ui(f"paper.md 已生成: {paper_d.name}/")

    # Backfill abstract if missing
    from autor.papers import read_meta, write_meta

    data = read_meta(paper_d)
    if not data.get("abstract"):
        from autor.ingest.metadata import extract_abstract_from_md

        abstract = extract_abstract_from_md(existing_md, cfg)
        if abstract:
            data["abstract"] = abstract
            write_meta(paper_d, data)
            ui(f"abstract 已补全 ({len(abstract)} chars)")

    # L3 generation and incremental node-level FTS5 update.
    from autor.ingest.pipeline import step_index, step_l3

    step_l3(paper_d / "meta.json", cfg, {"dry_run": False, "force": False, "inspect": False, "max_retries": 2})
    step_index(cfg.papers_dir, cfg, {"dry_run": False, "rebuild": False})


# ============================================================================
#  Output helpers
# ============================================================================


def _print_search_result(idx: int, r: dict, extra: str = "") -> None:
    authors = r.get("authors") or ""
    author_display = authors.split(",")[0].strip() + (" et al." if "," in authors else "")
    cite = r.get("citation_count") or ""
    cite_suffix = f"  [被引: {cite}]" if cite else ""
    extra_suffix = f"  ({extra})" if extra else ""
    # Prefer dir_name for display, fall back to paper_id (UUID)
    display_id = r.get("dir_name") or r["paper_id"]
    ui(f"[{idx}] {display_id}{extra_suffix}")
    ui(f"     {author_display} | {r.get('year', '?')} | {r.get('journal', '?')}{cite_suffix}")
    ui(f"     {r['title']}")
    ui()


def _print_search_next_steps(include_ws_add: bool = True) -> None:
    ui("下一步：可以运行 `autor show <paper-id> --layer 2/3/4` 查看摘要、结论或全文。")
    if include_ws_add:
        ui("也可以运行 `autor ws add <工作区名> <paper-id>` 把感兴趣的论文加入工作区。")


def _format_match_tag(match: str) -> str:
    mapping = {
        "both": "可审计",
        "fts": "可审计",
        "vec": "已废弃",
    }
    return mapping.get(match, match)


def _format_citations(cc: dict) -> str:
    if not cc:
        return ""
    parts = []
    for src in ("semantic_scholar", "openalex", "crossref"):
        if src in cc:
            label = {"semantic_scholar": "S2", "openalex": "OA", "crossref": "CR"}[src]
            parts.append(f"{label}:{cc[src]}")
    return " | ".join(parts)


def _resolve_paper(paper_id: str, cfg) -> Path:
    """Resolve a paper identifier (dir_name, UUID, or DOI) to its directory.

    Resolution order:
    1. Direct dir_name match on filesystem
    2. Registry lookup (UUID / DOI) → dir_name
    3. Filesystem scan — read each meta.json["id"] to find UUID match

    Returns the paper directory Path, or exits with error.
    """
    from autor.papers import iter_paper_dirs

    papers_dir = cfg.papers_dir
    # 1. Direct dir_name
    paper_d = papers_dir / paper_id
    if (paper_d / "meta.json").exists():
        return paper_d
    # 2. Registry lookup (fast, but may be stale)
    from autor.index import lookup_paper

    reg = lookup_paper(cfg.index_db, paper_id)
    if reg:
        paper_d = papers_dir / reg["dir_name"]
        if (paper_d / "meta.json").exists():
            return paper_d
    # 3. Filesystem scan fallback (handles stale registry / pre-index state)
    from autor.papers import read_meta as _read_meta

    for pdir in iter_paper_dirs(papers_dir):
        try:
            data = _read_meta(pdir)
        except (ValueError, FileNotFoundError) as e:
            _log.debug("failed to read meta.json in %s: %s", pdir.name, e)
            continue
        if data.get("id") == paper_id or data.get("doi") == paper_id:
            return pdir
    _log.error("未找到论文: %s", paper_id)
    sys.exit(1)


def _print_header(l1: dict) -> None:
    authors = l1.get("authors") or []
    author_str = ", ".join(authors[:3])
    if len(authors) > 3:
        author_str += f" et al. ({len(authors)} total)"
    ui(f"论文ID   : {l1['paper_id']}")
    ui(f"标题     : {l1['title']}")
    ui(f"作者     : {author_str}")
    ui(f"年份     : {l1.get('year') or '?'}  |  期刊: {l1.get('journal') or '?'}")
    if l1.get("doi"):
        ui(f"DOI      : {l1['doi']}")
    ids = l1.get("ids") or {}
    if ids.get("patent_publication_number"):
        ui(f"公开号   : {ids['patent_publication_number']}")
    if l1.get("paper_type"):
        ui(f"类型     : {l1['paper_type']}")
    cite_str = _format_citations(l1.get("citation_count") or {})
    if cite_str:
        ui(f"引用     : {cite_str}")
    if ids.get("semantic_scholar_url"):
        ui(f"S2       : {ids['semantic_scholar_url']}")
    if ids.get("openalex_url"):
        ui(f"OpenAlex : {ids['openalex_url']}")


def cmd_citation_check(args: argparse.Namespace, cfg) -> None:
    from autor.citation_check import check_citations, extract_citations

    # Read input text
    if args.file:
        p = Path(args.file)
        if not p.exists():
            _log.error("文件不存在：%s", p)
            sys.exit(1)
        text = p.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    if not text.strip():
        ui("输入文本为空。")
        return

    citations = extract_citations(text)
    if not citations:
        ui("未在文本中发现引用。")
        return

    ui(f"提取到 {len(citations)} 条引用，正在验证…\n")

    try:
        paper_ids = _resolve_ws_paper_ids(args, cfg)
    except ValueError as e:
        ui(str(e))
        return

    results = check_citations(
        citations,
        cfg.index_db,
        paper_ids=paper_ids,
    )

    # Count by status (internal codes)
    counts = {"VERIFIED": 0, "NOT_IN_LIBRARY": 0, "AMBIGUOUS": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    status_labels = {
        "VERIFIED": "已验证",
        "NOT_IN_LIBRARY": "库中未找到",
        "AMBIGUOUS": "候选不唯一",
    }

    for r in results:
        status_icon = {"VERIFIED": "✓", "NOT_IN_LIBRARY": "✗", "AMBIGUOUS": "?"}.get(r["status"], " ")
        status_text = status_labels.get(r["status"], r["status"])
        ui(f"  [{status_icon}] {status_text:8s}  {r['raw']}  ({r['author']}, {r['year']})")
        if r["matches"]:
            for m in r["matches"][:3]:
                display_id = m.get("dir_name") or m.get("paper_id", "?")
                ui(f"       → {display_id}")
                ui(f"         {m.get('title', '?')}")

    ui()
    ui(
        f"验证结果：已验证 {counts['VERIFIED']} / "
        f"候选不唯一 {counts['AMBIGUOUS']} / "
        f"库中未找到 {counts['NOT_IN_LIBRARY']}"
    )


# ============================================================================
#  Entry point
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="autor",
        description="本地学术文献检索工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- index ---
    p_index = sub.add_parser("index", help="构建节点级 FTS5 证据索引")
    p_index.set_defaults(func=cmd_index)
    p_index.add_argument("--rebuild", action="store_true", help="清空后重建")
    p_index.add_argument("--status", action="store_true", help="查看索引健康状态，不执行构建")
    p_index.add_argument("--background", action="store_true", help="后台执行索引构建")
    p_index.add_argument("--direct", action="store_true", help="重建时直接写目标 index.db，不使用临时库")
    p_index.add_argument("--tmp-dir", type=str, default=None, help="重建时使用的临时目录")

    # --- search ---
    p_search = sub.add_parser("search", help="关键词检索")
    p_search.set_defaults(func=cmd_search)
    p_search.add_argument("query", nargs="+", help="检索词")
    p_search.add_argument("--top", type=int, default=None, help="最多返回 N 条（默认读 config search.top_k）")
    _add_filter_args(p_search)

    # --- search-author ---
    p_sa = sub.add_parser("search-author", help="按作者名搜索")
    p_sa.set_defaults(func=cmd_search_author)
    p_sa.add_argument("query", nargs="+", help="作者名（模糊匹配）")
    p_sa.add_argument("--top", type=int, default=None, help="最多返回 N 条（默认读 config search.top_k）")
    _add_filter_args(p_sa)

    # --- show ---
    p_show = sub.add_parser("show", help="查看论文内容")
    p_show.set_defaults(func=cmd_show)
    p_show.add_argument("paper_id", help="论文目录名（search 结果中显示）")
    p_show.add_argument(
        "--layer",
        type=int,
        default=2,
        choices=[1, 2, 3, 4],
        help="加载层级：1=元数据, 2=摘要, 3=L3 结论层, 4=全文（默认 2）",
    )
    p_show.add_argument(
        "--append-notes",
        type=str,
        default=None,
        metavar="TEXT",
        help="向论文笔记 notes.md 追加内容（T2 层，跨会话复用）",
    )

    # --- research bundle ---
    p_research = sub.add_parser("research", help="生成可审计证据包")
    p_research.set_defaults(func=cmd_research)
    p_research.add_argument("query", nargs="+", help="研究问题或检索目标")
    p_research.add_argument("--top", type=int, default=None, help="种子证据节点数量")
    p_research.add_argument("--run-dir", default=None, help="证据包输出目录（默认 workspace/research-runs/<query>）")
    p_research.add_argument("--neighbors", type=int, default=1, help="每个命中节点展开前后相邻节点数")
    p_research.add_argument("--max-chars", type=int, default=40000, help="证据包总字符预算")
    p_research.add_argument("--per-node-max-chars", type=int, default=6000, help="单个证据节点字符预算")
    _add_filter_args(p_research)

    # --- enrich-toc ---
    p_toc = sub.add_parser("enrich-toc", help="LLM 过滤标题噪声，提取论文 TOC 写入 JSON")
    p_toc.set_defaults(func=cmd_enrich_toc)
    p_toc.add_argument("paper_id", nargs="?", help="论文 ID（省略则需 --all）")
    p_toc.add_argument("--all", action="store_true", help="处理 papers_dir 中所有论文")
    p_toc.add_argument("--force", action="store_true", help="强制重新提取")
    p_toc.add_argument("--inspect", action="store_true", help="展示过滤过程")

    # --- pipeline ---
    p_pipe = sub.add_parser("pipeline", help="组合步骤流水线（可任意组装）")
    p_pipe.set_defaults(func=cmd_pipeline)
    p_pipe.add_argument(
        "preset",
        nargs="?",
        help="预设名称：full | ingest | enrich | reindex",
    )
    p_pipe.add_argument("--steps", help="自定义步骤序列（逗号分隔），如 toc,l3,index")
    p_pipe.add_argument("--list", dest="list_steps", action="store_true", help="列出所有步骤和预设")
    p_pipe.add_argument("--dry-run", action="store_true", help="预览，不写文件")
    p_pipe.add_argument("--no-api", action="store_true", help="离线模式，跳过外部 API")
    p_pipe.add_argument("--force", action="store_true", help="强制重新处理（toc/l3）")
    p_pipe.add_argument("--inspect", action="store_true", help="展示处理详情")
    p_pipe.add_argument("--max-retries", type=int, default=2, help="l3 最大重试次数（默认 2）")
    p_pipe.add_argument("--rebuild", action="store_true", help="重建索引（index 步骤）")
    p_pipe.add_argument("--inbox", help="inbox 目录（默认 data/inbox）")
    p_pipe.add_argument("--papers", help="papers 目录（默认配置值）")
    p_pipe.add_argument(
        "-w",
        "--workspace",
        help="将成功入库的论文自动添加到指定工作区（如果工作区不存在则自动创建）",
    )
    p_pipe.add_argument(
        "--workspace-filter",
        help="添加到工作区前用标题+摘要检查主题范围（优先 LLM，失败时启用保守启发式）",
    )

    # --- identify ---
    p_ident = sub.add_parser("identify", help="检查 PMID/DOI 种子文献在本地库和工作区中的覆盖情况")
    p_ident.set_defaults(func=cmd_identify)
    p_ident.add_argument("--pmid", dest="pmids", action="append", help="待检查 PMID（可重复）")
    p_ident.add_argument("--doi", dest="dois", action="append", help="待检查 DOI（可重复）")
    p_ident.add_argument("--pmid-list", help="包含 PMID 的文本文件")
    p_ident.add_argument("--seed-file", help="包含 PMID/DOI 种子文献的文本文件")
    p_ident.add_argument("--workspace", "-w", help="同时检查是否已在指定工作区中")

    # --- refetch ---
    p_refetch = sub.add_parser("refetch", help="重新查询 API 补全引用量等字段")
    p_refetch.set_defaults(func=cmd_refetch)
    p_refetch.add_argument("paper_id", nargs="?", help="论文 ID（省略则需 --all）")
    p_refetch.add_argument("--all", action="store_true", help="补查所有缺失引用量的论文")
    p_refetch.add_argument("--workspace", "-w", help="只补查指定工作区中的论文")
    p_refetch.add_argument("--force", action="store_true", help="强制重新查询（包括已有引用量的论文）")
    p_refetch.add_argument("--jobs", "-j", type=int, default=5, help="并发数（默认 5）")

    # --- top-cited ---
    p_tc = sub.add_parser("top-cited", help="按引用量排序查看论文")
    p_tc.set_defaults(func=cmd_top_cited)
    p_tc.add_argument("--top", type=int, default=None, help="最多返回 N 条（默认读 config search.top_k）")
    _add_filter_args(p_tc)

    # --- refs ---
    p_refs = sub.add_parser("refs", help="查看论文的参考文献列表")
    p_refs.set_defaults(func=cmd_refs)
    p_refs.add_argument("paper_id", help="论文 ID（目录名 / UUID / DOI）")
    p_refs.add_argument("--ws", type=str, default=None, help="限定工作区范围")

    # --- citing ---
    p_citing = sub.add_parser("citing", help="查看哪些本地论文引用了此论文")
    p_citing.set_defaults(func=cmd_citing)
    p_citing.add_argument("paper_id", help="论文 ID（目录名 / UUID / DOI）")
    p_citing.add_argument("--ws", type=str, default=None, help="限定工作区范围")

    # --- shared-refs ---
    p_sr = sub.add_parser("shared-refs", help="共同参考文献分析")
    p_sr.set_defaults(func=cmd_shared_refs)
    p_sr.add_argument("paper_ids", nargs="+", help="论文 ID（至少 2 个）")
    p_sr.add_argument("--min", type=int, default=None, help="最少共引次数（默认 2）")
    p_sr.add_argument("--ws", type=str, default=None, help="限定工作区范围")

    # --- backfill-abstract ---
    p_bf = sub.add_parser("backfill-abstract", help="补全缺失的 abstract（支持 DOI 官方抓取）")
    p_bf.set_defaults(func=cmd_backfill_abstract)
    p_bf.add_argument("--dry-run", action="store_true", help="预览，不写文件")
    p_bf.add_argument("--doi-fetch", action="store_true", help="从出版商网页抓取官方 abstract（覆盖现有）")

    # --- rename ---
    p_rename = sub.add_parser("rename", help="根据 JSON 元数据重命名论文文件")
    p_rename.set_defaults(func=cmd_rename)
    p_rename.add_argument("paper_id", nargs="?", help="论文 ID（省略则需 --all）")
    p_rename.add_argument("--all", action="store_true", help="重命名所有文件名不正确的论文")
    p_rename.add_argument("--dry-run", action="store_true", help="预览，不实际重命名")

    # --- audit ---
    p_audit = sub.add_parser("audit", help="审计已入库论文的数据质量")
    p_audit.set_defaults(func=cmd_audit)
    p_audit.add_argument("--severity", choices=["error", "warning", "info"], help="只显示指定严重级别的问题")

    # --- repair ---
    p_repair = sub.add_parser("repair", help="修复论文元数据（手动指定 title/DOI，跳过 MD 解析）")
    p_repair.set_defaults(func=cmd_repair)
    p_repair.add_argument("paper_id", help="论文 ID（文件名 stem）")
    p_repair.add_argument("--title", required=True, help="正确的论文标题")
    p_repair.add_argument("--doi", default="", help="已知 DOI（加速 API 查询）")
    p_repair.add_argument("--author", default="", help="一作全名")
    p_repair.add_argument("--year", type=int, default=None, help="发表年份")
    p_repair.add_argument("--no-api", action="store_true", help="跳过 API 查询，仅用提供的信息")
    p_repair.add_argument("--dry-run", action="store_true", help="预览，不实际修改")

    # --- explore ---
    p_explore = sub.add_parser("explore", help="文献探索（OpenAlex 拉取 + FTS5 检索）")
    p_explore.set_defaults(func=cmd_explore)
    p_explore_sub = p_explore.add_subparsers(dest="explore_action", required=True)

    p_ef = p_explore_sub.add_parser("fetch", help="从 OpenAlex 拉取论文（多维度 filter）")
    p_ef.add_argument("--issn", default=None, help="期刊 ISSN（如 0022-1120）")
    p_ef.add_argument("--concept", default=None, help="OpenAlex concept ID（如 C62520636）")
    p_ef.add_argument("--topic-id", default=None, help="OpenAlex topic ID")
    p_ef.add_argument("--author", default=None, help="OpenAlex author ID")
    p_ef.add_argument("--institution", default=None, help="OpenAlex institution ID")
    p_ef.add_argument("--keyword", default=None, help="标题/摘要关键词搜索")
    p_ef.add_argument("--source-type", default=None, help="来源类型（journal/conference/repository）")
    p_ef.add_argument("--oa-type", default=None, help="论文类型（article/review 等）")
    p_ef.add_argument("--min-citations", type=int, default=None, help="最小引用量")
    p_ef.add_argument("--name", help="探索库名称（默认从 filter 推导）")
    p_ef.add_argument("--year-range", help="年份过滤（如 2020-2025）")
    p_ef.add_argument("--incremental", action="store_true", help="增量更新（追加新论文）")
    p_ef.add_argument("--limit", type=int, default=None, help="最多拉取的论文数量上限（不设则无限）")

    p_es = p_explore_sub.add_parser("search", help="探索库 FTS5 检索")
    p_es.add_argument("--name", required=True, help="探索库名称")
    p_es.add_argument("query", nargs="+", help="查询文本")
    p_es.add_argument("--top", type=int, default=None, help="返回条数")

    p_el = p_explore_sub.add_parser("list", help="列出所有探索库")

    p_ei = p_explore_sub.add_parser("info", help="查看探索库信息")
    p_ei.add_argument("--name", default=None, help="探索库名称（省略列出全部）")

    # --- export ---
    p_export = sub.add_parser("export", help="导出论文或文档（BibTeX / RIS / Markdown / DOCX）")
    p_export.set_defaults(func=cmd_export)
    p_export_sub = p_export.add_subparsers(dest="export_action", required=True)

    p_eb = p_export_sub.add_parser("bibtex", help="导出 BibTeX 格式（LaTeX 引用）")
    p_eb.add_argument("paper_ids", nargs="*", help="论文目录名（可多个）")
    p_eb.add_argument("--all", action="store_true", help="导出全部论文")
    p_eb.add_argument("--workspace", "-w", help="导出指定工作区的全部论文")
    p_eb.add_argument("--year", type=str, default=None, help="年份过滤：2023 / 2020-2024")
    p_eb.add_argument("--journal", type=str, default=None, help="期刊名过滤（模糊匹配）")
    p_eb.add_argument("-o", "--output", type=str, default=None, help="输出文件路径（省略则输出到屏幕）")

    p_er = p_export_sub.add_parser("ris", help="导出 RIS 格式（Zotero / Endnote / Mendeley 导入）")
    p_er.add_argument("paper_ids", nargs="*", help="论文目录名（可多个）")
    p_er.add_argument("--all", action="store_true", help="导出全部论文")
    p_er.add_argument("--year", type=str, default=None, help="年份过滤：2023 / 2020-2024")
    p_er.add_argument("--journal", type=str, default=None, help="期刊名过滤（模糊匹配）")
    p_er.add_argument("-o", "--output", type=str, default=None, help="输出文件路径（省略则输出到屏幕）")

    p_em = p_export_sub.add_parser("markdown", help="导出 Markdown 文献列表（可直接粘贴到文档）")
    p_em.add_argument("paper_ids", nargs="*", help="论文目录名（可多个）")
    p_em.add_argument("--all", action="store_true", help="导出全部论文")
    p_em.add_argument("--year", type=str, default=None, help="年份过滤：2023 / 2020-2024")
    p_em.add_argument("--journal", type=str, default=None, help="期刊名过滤（模糊匹配）")
    p_em.add_argument("--bullet", action="store_true", help="使用无序列表（默认有序）")
    p_em.add_argument(
        "--style",
        type=str,
        default="apa",
        help="引用格式：apa（默认）/ vancouver / chicago-author-date / mla / <自定义>",
    )
    p_em.add_argument("-o", "--output", type=str, default=None, help="输出文件路径（省略则输出到屏幕）")

    p_ed = p_export_sub.add_parser("docx", help="将 Markdown 文本导出为 Word DOCX 文件")
    p_ed.add_argument("--input", "-i", type=str, default=None, help="输入 Markdown 文件路径（省略则从 stdin 读取）")
    p_ed.add_argument(
        "--output", "-o", type=str, default=None, help="输出 .docx 文件路径（默认 workspace/output.docx）"
    )
    p_ed.add_argument("--title", type=str, default=None, help="文档标题（可选，插入为一级标题）")

    # --- ws (workspace) ---
    p_ws = sub.add_parser("ws", aliases=["workspace"], help="工作区论文子集管理")
    p_ws.set_defaults(func=cmd_ws)
    p_ws_sub = p_ws.add_subparsers(dest="ws_action", required=True)

    p_ws_init = p_ws_sub.add_parser("init", help="初始化工作区")
    p_ws_init.add_argument("name", help="工作区名称（workspace/ 下的子目录名）")

    p_ws_add = p_ws_sub.add_parser("add", help="添加论文到工作区")
    p_ws_add.add_argument("name", help="工作区名称")
    p_ws_add.add_argument("paper_refs", nargs="*", help="论文引用（UUID / 目录名 / DOI）")
    p_ws_add_batch = p_ws_add.add_mutually_exclusive_group()
    p_ws_add_batch.add_argument("--search", dest="add_search", type=str, default=None, help="按搜索结果批量添加")
    p_ws_add_batch.add_argument("--all", dest="add_all", action="store_true", default=False, help="添加全库论文")
    p_ws_add.add_argument("--top", type=int, default=None, help="限制 --search 返回条数")
    p_ws_add.add_argument("--filter", dest="scope_filter", help="添加前按主题范围过滤（优先 LLM，失败时启发式）")
    _add_filter_args(p_ws_add)

    p_ws_rm = p_ws_sub.add_parser("remove", help="从工作区移除论文")
    p_ws_rm.add_argument("name", help="工作区名称")
    p_ws_rm.add_argument("paper_refs", nargs="+", help="论文引用（UUID / 目录名 / DOI）")

    p_ws_list = p_ws_sub.add_parser("list", help="列出所有工作区")

    p_ws_dedup = p_ws_sub.add_parser("dedup", help="清理工作区中的 DUP 条目和重复 UUID")
    p_ws_dedup.add_argument("name", help="工作区名称")

    p_ws_show = p_ws_sub.add_parser("show", help="查看工作区中的论文")
    p_ws_show.add_argument("name", help="工作区名称")

    p_ws_search = p_ws_sub.add_parser("search", help="在工作区内搜索")
    p_ws_search.add_argument("name", help="工作区名称")
    p_ws_search.add_argument("query", nargs="+", help="查询文本")
    p_ws_search.add_argument("--top", type=int, default=None, help="返回条数")
    _add_filter_args(p_ws_search)

    p_ws_rename = p_ws_sub.add_parser("rename", help="重命名工作区")
    p_ws_rename.add_argument("old_name", help="当前工作区名称")
    p_ws_rename.add_argument("new_name", help="新工作区名称")

    p_ws_export = p_ws_sub.add_parser("export", help="导出工作区论文 BibTeX")
    p_ws_export.add_argument("name", help="工作区名称")
    p_ws_export.add_argument("-o", "--output", type=str, default=None, help="输出文件路径")
    _add_filter_args(p_ws_export)

    p_ws_export_meta = p_ws_sub.add_parser("export-meta", help="导出工作区论文 PMID/DOI 等元信息")
    p_ws_export_meta.add_argument("name", help="工作区名称")
    p_ws_export_meta.add_argument("-o", "--output", type=str, default=None, help="输出文件路径")
    p_ws_export_meta.add_argument(
        "--format",
        choices=["json", "jsonl", "csv"],
        default="json",
        help="导出格式（默认 json）",
    )

    p_ws_status = p_ws_sub.add_parser("status", help="查看工作区完整性状态")
    p_ws_status.add_argument("name", help="工作区名称")
    p_ws_status.add_argument("--papers", action="store_true", help="包含逐篇论文状态")

    p_ws_export_evidence = p_ws_sub.add_parser("export-evidence", help="导出工作区证据清单 JSON")
    p_ws_export_evidence.add_argument("name", help="工作区名称")
    p_ws_export_evidence.add_argument("-o", "--output", type=str, default=None, help="输出文件路径")

    p_ws_screen = p_ws_sub.add_parser("screen", help="按范围标准筛选工作区论文")
    p_ws_screen.add_argument("name", help="工作区名称")
    p_ws_screen.add_argument("--criteria", type=str, default=None, help="筛选标准文本")
    p_ws_screen.add_argument("--criteria-file", type=str, default=None, help="筛选标准文件")
    p_ws_screen.add_argument("--target", type=int, default=None, help="目标保留篇数")
    p_ws_screen.add_argument("--apply", action="store_true", help="将筛选结果实际应用到工作区")
    p_ws_screen.add_argument("-o", "--output", type=str, default=None, help="输出筛选报告路径")

    p_ws_plan = p_ws_sub.add_parser("plan-package", help="生成 review 规划包骨架")
    p_ws_plan.add_argument("name", help="工作区名称")
    p_ws_plan.add_argument("--title", type=str, default=None, help="综述标题")
    p_ws_plan.add_argument("--criteria", type=str, default="", help="筛选标准文本")
    p_ws_plan.add_argument("--criteria-file", type=str, default=None, help="筛选标准文件")

    p_ws_cov = p_ws_sub.add_parser("citation-coverage", help="检查稿件引用覆盖 reference-map 的程度")
    p_ws_cov.add_argument("name", help="工作区名称")
    p_ws_cov.add_argument("--manuscript", type=str, default=None, help="稿件 Markdown 路径（默认 final.md）")
    p_ws_cov.add_argument(
        "--require",
        choices=["retained", "citable", "must_cite"],
        default="retained",
        help="要求进入正文的引用范围（默认 retained）",
    )
    p_ws_cov.add_argument("--fail-if-missing", action="store_true", help="缺失必需引用或出现未知 citekey 时返回非零状态")
    p_ws_cov.add_argument("-o", "--output", type=str, default=None, help="输出检查报告路径")

    p_ws_net = p_ws_sub.add_parser("citation-network", help="导出工作区引用网络 sidecar")
    p_ws_net.add_argument("name", help="工作区名称")
    p_ws_net.add_argument("--min-shared", type=int, default=2, help="共同参考文献最小共引次数（默认 2）")
    p_ws_net.add_argument("-o", "--output", type=str, default=None, help="输出 JSON 路径（默认 sidecars/citation-network.json）")
    p_ws_net.add_argument("--print-json", action="store_true", help="写文件后同时输出 JSON")

    p_ws_fig = p_ws_sub.add_parser("figure-status", help="检查 table-figure-plan 中计划图片是否已导出")
    p_ws_fig.add_argument("name", help="工作区名称")
    p_ws_fig.add_argument("--fail-if-missing", action="store_true", help="存在未导出的计划图片时返回非零状态")
    p_ws_fig.add_argument("-o", "--output", type=str, default=None, help="输出检查报告路径")

    # --- import-endnote ---
    p_ie = sub.add_parser("import-endnote", help="从 Endnote XML/RIS 导入论文元数据")
    p_ie.set_defaults(func=cmd_import_endnote)
    p_ie.add_argument("files", nargs="+", help="Endnote 导出文件（.xml 或 .ris）")
    p_ie.add_argument("--no-api", action="store_true", help="跳过 API 查询，仅用文件中的元数据")
    p_ie.add_argument("--dry-run", action="store_true", help="预览，不实际导入")
    p_ie.add_argument("--no-convert", action="store_true", help="跳过 PDF → paper.md 转换（默认自动转换）")

    # --- import-zotero ---
    p_iz = sub.add_parser("import-zotero", help="从 Zotero 导入论文元数据和 PDF")
    p_iz.set_defaults(func=cmd_import_zotero)
    p_iz.add_argument("--local", metavar="SQLITE_PATH", help="使用本地 zotero.sqlite")
    p_iz.add_argument("--api-key", help="Zotero API key")
    p_iz.add_argument("--library-id", help="Zotero library ID")
    p_iz.add_argument("--library-type", choices=["user", "group"], help="Library 类型（默认 user）")
    p_iz.add_argument("--collection", metavar="KEY", help="仅导入指定 collection")
    p_iz.add_argument("--item-type", nargs="+", help="限定 item 类型（如 journalArticle conferencePaper）")
    p_iz.add_argument("--list-collections", action="store_true", help="列出所有 collections 后退出")
    p_iz.add_argument("--no-pdf", action="store_true", help="跳过 PDF 下载/复制")
    p_iz.add_argument("--no-api", action="store_true", help="跳过学术 API 查询")
    p_iz.add_argument("--dry-run", action="store_true", help="预览，不实际导入")
    p_iz.add_argument("--no-convert", action="store_true", help="跳过 PDF → paper.md 转换")
    p_iz.add_argument("--import-collections", action="store_true", help="将 Zotero collections 创建为工作区")

    # --- attach-pdf ---
    p_ap = sub.add_parser("attach-pdf", help="为已入库论文补充 PDF 并生成 paper.md")
    p_ap.set_defaults(func=cmd_attach_pdf)
    p_ap.add_argument("paper_id", help="论文 ID（目录名 / UUID / DOI）")
    p_ap.add_argument("pdf_path", help="PDF 文件路径")
    p_ap.add_argument("--dry-run", action="store_true", help="预览将要执行的操作，不实际运行")

    # --- citation-check ---
    p_cc = sub.add_parser("citation-check", help="验证文本中的引用是否在本地知识库中")
    p_cc.set_defaults(func=cmd_citation_check)
    p_cc.add_argument("file", nargs="?", default=None, help="待检查的文件路径（省略则从 stdin 读取）")
    p_cc.add_argument("--ws", type=str, default=None, help="在指定工作区范围内验证")

    # --- plot ---
    p_plot = sub.add_parser("plot", help="调用 GPT Image 2 生成图片并保存到 workspace/")
    p_plot.set_defaults(func=cmd_plot)
    p_plot.add_argument("prompt", nargs="*", help="绘图提示词（省略时可用 --prompt-file）")
    p_plot.add_argument("--prompt-file", type=str, default=None, help="从文件读取完整 prompt")
    p_plot.add_argument("--ws", dest="workspace", type=str, default=None, help="输出到 workspace/<name>/figure/")
    p_plot.add_argument("--name", type=str, default=None, help="输出文件名 stem（不含扩展名）")
    p_plot.add_argument("--output-dir", type=str, default=None, help="显式输出目录（覆盖 --ws 默认路径）")
    p_plot.add_argument("--ref-url", action="append", default=None, help="参考图 URL，可重复传入")
    p_plot.add_argument("--host", type=str, default=None, help="临时覆盖 plot.host")
    p_plot.add_argument("--api-key", type=str, default=None, help="临时覆盖 plot.api_key")
    p_plot.add_argument("--model", type=str, default=None, help="临时覆盖绘图模型（默认读 config plot.model）")
    p_plot.add_argument(
        "--aspect-ratio",
        choices=["auto", "1:1", "3:2", "2:3", "16:9", "9:16", "5:4", "4:5", "4:3", "3:4", "21:9", "9:21", "1:3", "3:1", "2:1", "1:2"],
        default=None,
        help="输出长宽比（默认读配置）",
    )
    p_plot.add_argument("--timeout", type=int, default=None, help="总超时秒数（默认读配置）")
    p_plot.add_argument("--poll-interval", type=int, default=None, help="结果轮询间隔秒数（默认读配置）")

    # --- setup ---
    p_setup = sub.add_parser("setup", help="环境检测与安装向导 / Setup wizard")
    p_setup.set_defaults(func=cmd_setup)
    p_setup_sub = p_setup.add_subparsers(dest="setup_action")
    p_setup_check = p_setup_sub.add_parser("check", help="检查环境状态 / Check environment status")
    p_setup_check.add_argument(
        "--lang", choices=["en", "zh"], default="zh", help="输出语言 / Output language (default: zh)"
    )

    # --- migrate-dirs ---
    p_migrate = sub.add_parser("migrate-dirs", help="迁移 data/papers/ 从平铺结构到每篇一目录")
    p_migrate.set_defaults(func=cmd_migrate_dirs)
    p_migrate.add_argument("--execute", action="store_true", help="实际执行迁移（默认 dry-run）")

    # --- fsearch ---
    p_fsearch = sub.add_parser("fsearch", help="联邦搜索：同时搜索主库、explore 库和 arXiv")
    p_fsearch.set_defaults(func=cmd_fsearch)
    p_fsearch.add_argument("query", nargs="+", help="检索词")
    p_fsearch.add_argument(
        "--scope",
        type=str,
        default="main",
        help="搜索范围（逗号分隔）：main / explore:NAME / explore:* / arxiv（默认 main）",
    )
    p_fsearch.add_argument("--top", type=int, default=None, help="每个来源最多返回 N 条（默认 10）")

    # --- insights ---
    p_insights = sub.add_parser("insights", help="研究行为分析：搜索热词、最常阅读论文等")
    p_insights.set_defaults(func=cmd_insights)
    p_insights.add_argument("--days", type=int, default=30, help="分析最近 N 天的数据（默认 30）")

    # --- metrics ---
    p_metrics = sub.add_parser("metrics", help="查看 LLM token 用量和调用统计")
    p_metrics.set_defaults(func=cmd_metrics)
    p_metrics.add_argument("--last", type=int, default=20, help="最近 N 条记录")
    p_metrics.add_argument("--category", default="llm", help="事件类别（llm/api/step，默认 llm）")
    p_metrics.add_argument("--since", default=None, help="起始时间（ISO 格式，如 2026-03-01）")
    p_metrics.add_argument("--summary", action="store_true", help="仅显示汇总统计")

    # --- style ---
    p_style = sub.add_parser("style", help="引用格式管理（列出 / 查看自定义格式）")
    p_style.set_defaults(func=cmd_style)
    p_style_sub = p_style.add_subparsers(dest="style_sub", required=True)

    p_style_list = p_style_sub.add_parser("list", help="列出所有可用引用格式")
    del p_style_list  # no extra args needed

    p_style_show = p_style_sub.add_parser("show", help="查看引用格式的格式化函数代码")
    p_style_show.add_argument("name", help="格式名称，如 jcp / apa / vancouver")

    # --- document ---
    p_doc = sub.add_parser("document", help="Office 文档工具（inspect 等）")
    p_doc.set_defaults(func=cmd_document)
    p_doc_sub = p_doc.add_subparsers(dest="doc_action", required=True)

    p_doc_inspect = p_doc_sub.add_parser("inspect", help="检查 Office 文档结构（DOCX / PPTX / XLSX）")
    p_doc_inspect.add_argument("file", help="文件路径")
    p_doc_inspect.add_argument(
        "--format",
        choices=["docx", "pptx", "xlsx"],
        default=None,
        help="文件格式（默认从扩展名推断）",
    )

    # --- enrich-l3 ---
    p_l3 = sub.add_parser("enrich-l3", help="LLM 生成 L3 结论层写入 JSON")
    p_l3.set_defaults(func=cmd_enrich_l3)
    p_l3.add_argument("paper_id", nargs="?", help="论文 ID（省略则需 --all）")
    p_l3.add_argument("--all", action="store_true", help="处理 papers_dir 中所有论文")
    p_l3.add_argument("--workspace", "-w", help="只处理指定工作区中的论文")
    p_l3.add_argument("--only-missing", action="store_true", help="仅处理缺少 L3 的论文（需配合 --workspace）")
    p_l3.add_argument("--force", action="store_true", help="强制重新提取（覆盖已有结果）")
    p_l3.add_argument("--inspect", action="store_true", help="展示提取过程详情")
    p_l3.add_argument("--max-retries", type=int, default=2, help="最大重试次数（默认 2）")

    args = parser.parse_args()
    cfg = load_config()
    cfg.ensure_dirs()

    from autor import log as _log
    from autor import metrics as _metrics
    from autor.ingest.metadata._models import configure_metadata_sessions

    session_id = _log.setup(cfg)
    _metrics.init(cfg.metrics_db_path, session_id)
    configure_metadata_sessions(
        cfg.ingest.contact_email,
        cfg.resolved_s2_api_key(),
        cfg.resolved_ncbi_api_key(),
    )

    args.func(args, cfg)


if __name__ == "__main__":
    main()
