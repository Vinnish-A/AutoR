"""
mcp_server.py -- autor MCP 服务端
========================================

通过 MCP 协议暴露 autor 知识库的查询和管理功能。
使用 stdio 传输，供 Claude Desktop / Claude Code 集成。

启动：
    autor-mcp                        # entry point
    python -m autor.mcp_server       # 直接运行

配置：
    AUTOR_ROOT=/path/to/project      # 项目根目录（含 config.yaml）
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("autor")

_cfg = None
_log = logging.getLogger(__name__)


# ============================================================================
#  Config & logging helpers
# ============================================================================


def _get_cfg():
    """Lazy-load config singleton."""
    global _cfg
    if _cfg is None:
        from autor.config import load_config
        from autor.ingest.metadata import configure_metadata_sessions

        root = os.environ.get("AUTOR_ROOT")
        if root:
            _cfg = load_config(Path(root) / "config.yaml")
        else:
            _cfg = load_config()

        _init_logging(_cfg)
        _cfg.ensure_dirs()
        configure_metadata_sessions(
            _cfg.ingest.contact_email,
            _cfg.resolved_s2_api_key(),
            _cfg.resolved_ncbi_api_key(),
        )
    return _cfg


def _init_logging(cfg):
    """File-only logging -- no stdout (stdio transport occupies stdout)."""
    root = logging.getLogger()
    # Skip if already initialised (e.g. tests)
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        return
    root.setLevel(logging.DEBUG)

    log_path = cfg.log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=cfg.log.max_bytes,
        backupCount=cfg.log.backup_count,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(name)-24s %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    for name in ("httpx", "urllib3", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


# ============================================================================
#  Resolution helpers
# ============================================================================


def _resolve_paper_dir(paper_ref: str) -> Path:
    """Resolve paper_ref (dir_name, UUID, DOI, or PMID) to its directory.

    Raises:
        ValueError: If the paper is not found.
    """
    from autor.index import lookup_paper
    from autor.papers import iter_paper_dirs, read_meta

    cfg = _get_cfg()
    papers_dir = cfg.papers_dir

    # 1. Direct dir_name
    d = papers_dir / paper_ref
    if (d / "meta.json").exists():
        return d
    # 2. Registry lookup
    try:
        reg = lookup_paper(cfg.index_db, paper_ref)
    except FileNotFoundError:
        reg = None
    if reg:
        d = papers_dir / reg["dir_name"]
        if (d / "meta.json").exists():
            return d
    # 3. Filesystem scan fallback
    for pdir in iter_paper_dirs(papers_dir):
        try:
            data = read_meta(pdir)
        except (ValueError, FileNotFoundError):
            continue
        ids = data.get("ids") or {}
        if (
            data.get("id") == paper_ref
            or data.get("doi") == paper_ref
            or data.get("pmid") == paper_ref
            or ids.get("pmid") == paper_ref
        ):
            return pdir
    raise ValueError(f"Paper not found: {paper_ref}")


def _resolve_workspace_ids(workspace: str | None) -> set[str] | None:
    """Resolve workspace name to paper_ids set, or None."""
    if not workspace:
        return None
    from autor import workspace as ws_mod

    cfg = _get_cfg()
    ws_dir = cfg._root / "workspace" / workspace
    return ws_mod.read_paper_ids(ws_dir) or None


def _error(code: str, message: str, **extra) -> str:
    """Return a JSON error string for MCP tool responses."""
    return json.dumps({"error": code, "message": message, **extra}, ensure_ascii=False)


def _summarize_exact_matches(matches: dict[str, list[dict]]) -> dict:
    """Convert exact-match buckets into a stable MCP-friendly payload."""
    records = matches.get("records", [])
    return {
        "found": bool(records),
        "ambiguous": len(records) > 1,
        "match_count": len(records),
        "matches": {
            "doi": matches.get("doi", []),
            "pmid": matches.get("pmid", []),
            "title": matches.get("title", []),
        },
        "records": records,
    }


# ============================================================================
#  Search tools (5)
# ============================================================================


@mcp.tool()
def search(
    query: str,
    top_k: int = 20,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    workspace: str | None = None,
) -> str:
    """Auditable node-level FTS5 search with evidence snippets.

    Args:
        query: Search keywords.
        top_k: Maximum number of results (default 20).
        year: Year filter, e.g. "2023", "2020-2024", "2020-".
        journal: Journal name filter (substring match).
        paper_type: Paper type filter, e.g. "review", "journal-article".
        workspace: Optional workspace name to scope the search.
    """
    try:
        from autor.index import search as _search

        cfg = _get_cfg()
        paper_ids = _resolve_workspace_ids(workspace)
        results = _search(
            query, cfg.index_db, top_k=top_k, cfg=cfg,
            year=year, journal=journal, paper_type=paper_type, paper_ids=paper_ids,
        )
        return json.dumps(results, ensure_ascii=False)
    except FileNotFoundError:
        return _error("index_not_found", "Index not built. Run: autor index")
    except Exception as e:
        _log.exception("search failed")
        return _error("internal", str(e))


@mcp.tool()
def search_author(
    query: str,
    top_k: int = 20,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    workspace: str | None = None,
) -> str:
    """Search papers by author name (fuzzy LIKE match).

    Args:
        query: Author name or partial name.
        top_k: Maximum number of results.
        year: Year filter.
        journal: Journal name filter.
        paper_type: Paper type filter.
        workspace: Optional workspace name.
    """
    try:
        from autor.index import search_author as _search_author

        cfg = _get_cfg()
        paper_ids = _resolve_workspace_ids(workspace)
        results = _search_author(
            query, cfg.index_db, top_k=top_k, cfg=cfg,
            year=year, journal=journal, paper_type=paper_type, paper_ids=paper_ids,
        )
        return json.dumps(results, ensure_ascii=False)
    except FileNotFoundError:
        return _error("index_not_found", "Index not built. Run: autor index")
    except Exception as e:
        _log.exception("search_author failed")
        return _error("internal", str(e))


@mcp.tool()
def research_bundle(
    query: str,
    run_dir: str | None = None,
    top_k: int = 10,
    neighbors: int = 1,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    workspace: str | None = None,
) -> str:
    """Generate an auditable evidence bundle plus trace/verify artifacts.

    Args:
        query: Research question or search goal.
        run_dir: Optional output directory.
        top_k: Number of seed evidence nodes.
        neighbors: Previous/next node expansion count.
        year: Year filter.
        journal: Journal filter.
        paper_type: Paper type filter.
        workspace: Optional workspace scope.
    """
    try:
        from autor.index import research_bundle as _research_bundle

        cfg = _get_cfg()
        paper_ids = _resolve_workspace_ids(workspace)
        out_dir = Path(run_dir) if run_dir else cfg._root / "workspace" / "research-runs" / "mcp"
        result = _research_bundle(
            query,
            cfg.index_db,
            run_dir=out_dir,
            top_k=top_k,
            cfg=cfg,
            year=year,
            journal=journal,
            paper_type=paper_type,
            paper_ids=paper_ids,
            neighbors=neighbors,
        )
        return json.dumps(
            {
                "bundle_json": result["bundle_json"],
                "trace": result["trace"],
                "verify": result["verify"],
                "paths": result["paths"],
            },
            ensure_ascii=False,
        )
    except FileNotFoundError:
        return _error("index_not_found", "Index not built. Run: autor index --rebuild")
    except Exception as e:
        _log.exception("research_bundle failed")
        return _error("internal", str(e))


@mcp.tool()
def top_cited(
    top_k: int = 20,
    year: str | None = None,
    journal: str | None = None,
    paper_type: str | None = None,
    workspace: str | None = None,
) -> str:
    """List papers ranked by citation count (highest first).

    Args:
        top_k: Number of papers to return (default 20).
        year: Year filter.
        journal: Journal name filter.
        paper_type: Paper type filter.
        workspace: Optional workspace name.
    """
    try:
        from autor.index import top_cited as _top_cited

        cfg = _get_cfg()
        paper_ids = _resolve_workspace_ids(workspace)
        results = _top_cited(
            cfg.index_db, top_k=top_k,
            year=year, journal=journal, paper_type=paper_type, paper_ids=paper_ids,
        )
        return json.dumps(results, ensure_ascii=False)
    except FileNotFoundError:
        return _error("index_not_found", "Index not built. Run: autor index")
    except Exception as e:
        _log.exception("top_cited failed")
        return _error("internal", str(e))


# ============================================================================
#  Paper content tools (2)
# ============================================================================


@mcp.tool()
def show_paper(paper_ref: str, layer: int = 2) -> str:
    """Show paper content at the specified detail level.

    Layer 1: metadata (title, authors, year, journal, DOI, etc.)
    Layer 2: metadata + abstract
    Layer 3: metadata + abstract + conclusion
    Layer 4: metadata + full markdown text

    Args:
        paper_ref: Paper identifier (directory name, UUID, DOI, or PMID).
        layer: Detail level 1-4 (default 2).
    """
    try:
        from autor.loader import load_l1, load_l2, load_l3, load_l3_record, load_l4

        paper_d = _resolve_paper_dir(paper_ref)
        json_path = paper_d / "meta.json"
        md_path = paper_d / "paper.md"

        result = load_l1(json_path)

        if layer >= 2:
            result["abstract"] = load_l2(json_path)
        if layer >= 3:
            result["conclusion"] = load_l3(json_path)
            result["l3"] = load_l3_record(json_path)
        if layer >= 4:
            if md_path.exists():
                result["full_text"] = load_l4(md_path)
            else:
                result["full_text"] = None

        return json.dumps(result, ensure_ascii=False)
    except ValueError as e:
        return _error("not_found", str(e))
    except Exception as e:
        _log.exception("show_paper failed")
        return _error("internal", str(e))


@mcp.tool()
def lookup_paper(paper_ref: str) -> str:
    """Look up a paper by UUID, directory name, DOI, or PMID in the registry.

    Returns basic paper info (id, dir_name, title, doi, pmid, year, first_author)
    or null if not found. Faster than show_paper for simple lookups.

    Args:
        paper_ref: Paper identifier (UUID, directory name, DOI, or PMID).
    """
    try:
        from autor.index import lookup_paper as _lookup

        cfg = _get_cfg()
        result = _lookup(cfg.index_db, paper_ref)
        return json.dumps(result, ensure_ascii=False)
    except FileNotFoundError:
        return _error("index_not_found", "Index not built. Run: autor index")
    except Exception as e:
        _log.exception("lookup_paper failed")
        return _error("internal", str(e))


@mcp.tool()
def identify(
    doi: str | None = None,
    pmid: str | None = None,
    title: str | None = None,
    workspace: str | None = None,
) -> str:
    """Identify exact duplicates before fetching, downloading, or ingesting a paper.

    Call this **before** asking another system to retrieve a paper. It performs
    exact matching against the local library by DOI, PMID, and/or full title,
    and can also tell you whether the same match already exists inside a
    specific workspace.

    Args:
        doi: Exact DOI to check (case-insensitive).
        pmid: Exact PubMed ID to check.
        title: Exact full paper title to check (case-insensitive).
        workspace: Optional workspace name for a second, workspace-scoped check.
    """
    if not any((doi, pmid, title)):
        return _error("invalid_args", "Specify at least one of doi, pmid, or title.")
    try:
        from autor import workspace as ws_mod
        from autor.index import find_exact_matches

        cfg = _get_cfg()
        payload = {
            "query": {"doi": doi, "pmid": pmid, "title": title, "workspace": workspace},
            "library": _summarize_exact_matches(
                find_exact_matches(cfg.index_db, doi=doi, pmid=pmid, title=title)
            ),
        }
        if workspace is not None:
            if not ws_mod.validate_workspace_name(workspace):
                return _error("invalid_workspace", f"Invalid workspace name: {workspace}")
            ws_dir = cfg._root / "workspace" / workspace
            if ws_dir.exists():
                payload["workspace"] = {
                    "name": workspace,
                    "exists": True,
                    **_summarize_exact_matches(
                        ws_mod.identify_exact(ws_dir, cfg.index_db, doi=doi, pmid=pmid, title=title)
                    ),
                }
            else:
                payload["workspace"] = {
                    "name": workspace,
                    "exists": False,
                    "found": False,
                    "ambiguous": False,
                    "match_count": 0,
                    "matches": {"doi": [], "pmid": [], "title": []},
                    "records": [],
                }
        return json.dumps(payload, ensure_ascii=False)
    except FileNotFoundError:
        return _error("index_not_found", "Index not built. Run: autor index")
    except Exception as e:
        _log.exception("identify failed")
        return _error("internal", str(e))


@mcp.tool()
def identify_coverage(
    pmids: list[str] | None = None,
    dois: list[str] | None = None,
    workspace: str | None = None,
) -> str:
    """Check a canonical PMID/DOI seed list against the local library and workspace."""
    try:
        from autor import workspace as ws_mod
        from autor.index import lookup_paper as _lookup

        cfg = _get_cfg()
        workspace_ids: set[str] | None = None
        if workspace is not None:
            if not ws_mod.validate_workspace_name(workspace):
                return _error("invalid_workspace", f"Invalid workspace name: {workspace}")
            workspace_ids = ws_mod.read_paper_ids(cfg._root / "workspace" / workspace)

        identifiers = list(dict.fromkeys([*(pmids or []), *(dois or [])]))
        records: list[dict] = []
        missing: list[str] = []
        for ident in identifiers:
            record = _lookup(cfg.index_db, ident)
            if not record:
                missing.append(ident)
                continue
            item = dict(record)
            item["query"] = ident
            if workspace_ids is not None:
                item["in_workspace"] = item["id"] in workspace_ids
            records.append(item)
        return json.dumps(
            {
                "count": len(identifiers),
                "found_count": len(records),
                "missing_count": len(missing),
                "workspace": workspace,
                "records": records,
                "missing": missing,
            },
            ensure_ascii=False,
        )
    except FileNotFoundError:
        return _error("index_not_found", "Index not built. Run: autor index")
    except Exception as e:
        _log.exception("identify_coverage failed")
        return _error("internal", str(e))


# ============================================================================
#  Citation graph tools (3)
# ============================================================================


@mcp.tool()
def get_references(paper_ref: str, workspace: str | None = None) -> str:
    """Get the reference list of a paper (papers it cites).

    Returns two groups: references found in the local library (with metadata)
    and references only known by DOI (outside the library).

    Args:
        paper_ref: Paper identifier.
        workspace: Optional workspace name to scope results.
    """
    try:
        from autor.index import get_references as _get_refs

        cfg = _get_cfg()
        paper_ids = _resolve_workspace_ids(workspace)
        # Resolve to UUID
        paper_d = _resolve_paper_dir(paper_ref)
        from autor.papers import read_meta
        meta = read_meta(paper_d)
        uuid = meta["id"]

        results = _get_refs(uuid, cfg.index_db, paper_ids=paper_ids)
        return json.dumps(results, ensure_ascii=False)
    except ValueError as e:
        return _error("not_found", str(e))
    except FileNotFoundError:
        return _error("index_not_found", "Index not built. Run: autor index")
    except Exception as e:
        _log.exception("get_references failed")
        return _error("internal", str(e))


@mcp.tool()
def get_citing_papers(paper_ref: str, workspace: str | None = None) -> str:
    """Find papers that cite the given paper.

    Args:
        paper_ref: Paper identifier.
        workspace: Optional workspace name to scope results.
    """
    try:
        from autor.index import get_citing_papers as _get_citing

        cfg = _get_cfg()
        paper_ids = _resolve_workspace_ids(workspace)
        paper_d = _resolve_paper_dir(paper_ref)
        from autor.papers import read_meta
        meta = read_meta(paper_d)
        uuid = meta["id"]

        results = _get_citing(uuid, cfg.index_db, paper_ids=paper_ids)
        return json.dumps(results, ensure_ascii=False)
    except ValueError as e:
        return _error("not_found", str(e))
    except FileNotFoundError:
        return _error("index_not_found", "Index not built. Run: autor index")
    except Exception as e:
        _log.exception("get_citing_papers failed")
        return _error("internal", str(e))


@mcp.tool()
def get_shared_references(
    paper_refs: list[str],
    min_shared: int = 2,
    workspace: str | None = None,
) -> str:
    """Find references shared by multiple papers.

    Useful for discovering common foundations between papers.

    Args:
        paper_refs: List of 2+ paper identifiers.
        min_shared: Minimum number of papers that must cite a reference (default 2).
        workspace: Optional workspace name.
    """
    try:
        from autor.index import get_shared_references as _get_shared
        from autor.papers import read_meta

        cfg = _get_cfg()
        paper_ids = _resolve_workspace_ids(workspace)

        uuids = []
        for ref in paper_refs:
            paper_d = _resolve_paper_dir(ref)
            meta = read_meta(paper_d)
            uuids.append(meta["id"])

        results = _get_shared(uuids, cfg.index_db, min_shared=min_shared, paper_ids=paper_ids)
        return json.dumps(results, ensure_ascii=False)
    except ValueError as e:
        return _error("not_found", str(e))
    except FileNotFoundError:
        return _error("index_not_found", "Index not built. Run: autor index")
    except Exception as e:
        _log.exception("get_shared_references failed")
        return _error("internal", str(e))


# ============================================================================
#  Build tools
# ============================================================================


@mcp.tool()
def build_index(rebuild: bool = False, background: bool = False) -> str:
    """Build or rebuild the FTS5 full-text search index.

    Args:
        rebuild: If True, drop and rebuild from scratch. Otherwise incremental.
        background: If True, start the build in the background and return a job record.
    """
    try:
        from autor.index import build_index as _build_index
        from autor.index import build_index_atomic

        cfg = _get_cfg()
        if background:
            run_dir = cfg._root / ".run"
            run_dir.mkdir(parents=True, exist_ok=True)
            log_path = run_dir / "index-rebuild.log"
            job_file = run_dir / "index-job.json"
            cmd = [sys.executable, "-m", "autor.cli", "index"]
            if rebuild:
                cmd.append("--rebuild")
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
                "rebuild": rebuild,
            }
            job_file.write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return json.dumps({"status": "queued", **job}, ensure_ascii=False)
        if rebuild:
            count = build_index_atomic(cfg.papers_dir, cfg.index_db, rebuild=True)
        else:
            count = _build_index(cfg.papers_dir, cfg.index_db, rebuild=False)
        return json.dumps({"indexed": count})
    except Exception as e:
        _log.exception("build_index failed")
        return _error("internal", str(e))


@mcp.tool()
def index_status() -> str:
    """Return the local index health summary and any background job record."""
    try:
        from autor.index import index_status as _index_status

        cfg = _get_cfg()
        payload = _index_status(cfg.index_db)
        job_file = cfg._root / ".run" / "index-job.json"
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
                payload["background_job"] = {**job, "running": running}
            except (OSError, json.JSONDecodeError, ValueError):
                payload["background_job"] = {"status": "unreadable", "path": str(job_file)}
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        _log.exception("index_status failed")
        return _error("internal", str(e))


# ============================================================================
#  Workspace tools (4)
# ============================================================================


@mcp.tool()
def workspace_list() -> str:
    """List all research workspaces."""
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        ws_root = cfg._root / "workspace"
        names = ws_mod.list_workspaces(ws_root)
        return json.dumps(names, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_list failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_show(name: str) -> str:
    """Show papers in a workspace.

    Args:
        name: Workspace name.
    """
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")
        papers = ws_mod.show(ws_dir, cfg.index_db)
        return json.dumps(papers, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_show failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_add(name: str, paper_refs: list[str]) -> str:
    """Add papers to a workspace. Creates the workspace if it doesn't exist.

    Args:
        name: Workspace name.
        paper_refs: List of paper identifiers (UUID, directory name, or DOI).
    """
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            ws_mod.create(ws_dir)
        added = ws_mod.add(ws_dir, paper_refs, cfg.index_db)
        return json.dumps({"added": added}, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_add failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_dedup(name: str) -> str:
    """Remove DUP-prefixed and repeated records from a workspace."""
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")
        result = ws_mod.dedup(ws_dir, cfg.index_db)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_dedup failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_remove(name: str, paper_refs: list[str]) -> str:
    """Remove papers from a workspace.

    Args:
        name: Workspace name.
        paper_refs: List of paper identifiers to remove.
    """
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")
        removed = ws_mod.remove(ws_dir, paper_refs, cfg.index_db)
        return json.dumps({"removed": removed}, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_remove failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_status(name: str, include_papers: bool = False) -> str:
    """Inspect workspace corpus completeness and enrichment status.

    Args:
        name: Workspace name.
        include_papers: Include per-paper status rows.
    """
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")
        payload = ws_mod.status(ws_dir, cfg.papers_dir, cfg.index_db, include_papers=include_papers)
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_status failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_export_evidence(name: str) -> str:
    """Export a workspace evidence ledger as structured JSON.

    Args:
        name: Workspace name.
    """
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")
        rows = ws_mod.export_evidence(ws_dir, cfg.papers_dir, cfg.index_db)
        return json.dumps(rows, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_export_evidence failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_screen(
    name: str,
    criteria: str,
    target_count: int | None = None,
    apply: bool = False,
) -> str:
    """Score and optionally apply workspace screening by textual criteria.

    Args:
        name: Workspace name.
        criteria: Inclusion and exclusion criteria in plain text.
        target_count: Optional number of highest-scoring papers to retain.
        apply: Remove excluded papers from the workspace when true.
    """
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        if not criteria.strip():
            return _error("invalid_args", "criteria is required")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")
        result = ws_mod.screen(
            ws_dir,
            cfg.papers_dir,
            cfg.index_db,
            criteria=criteria,
            target_count=target_count,
            apply=apply,
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_screen failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_generate_planning_package(
    name: str,
    title: str | None = None,
    criteria: str = "",
) -> str:
    """Generate the canonical workspace planning package skeleton.

    Args:
        name: Workspace name.
        title: Optional review title.
        criteria: Optional screening criteria to record in review-plan.md.
    """
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")
        result = ws_mod.generate_planning_package(
            ws_dir,
            cfg.papers_dir,
            cfg.index_db,
            title=title,
            criteria=criteria,
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_generate_planning_package failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_citation_coverage(
    name: str,
    manuscript: str | None = None,
    require: str = "retained",
) -> str:
    """Check whether a manuscript cites the required reference-map entries.

    Args:
        name: Workspace name.
        manuscript: Optional Markdown path. Defaults to final.md, then write.md.
        require: Required scope: retained, citable, or must_cite.
    """
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")
        manuscript_path = Path(manuscript) if manuscript else None
        result = ws_mod.citation_coverage(ws_dir, manuscript_path, require=require)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_citation_coverage failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_citation_network(
    name: str,
    min_shared: int = 2,
    output: str | None = None,
) -> str:
    """Build and save a workspace-scoped citation-network sidecar.

    Args:
        name: Workspace name.
        min_shared: Minimum shared-reference count.
        output: Optional output JSON path. Defaults to sidecars/citation-network.json.
    """
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")
        result = ws_mod.citation_network(ws_dir, cfg.index_db, min_shared=min_shared)
        out = Path(output) if output else ws_dir / "sidecars" / "citation-network.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return json.dumps({"status": "ok", "output": str(out), "network": result}, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_citation_network failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_figure_status(name: str) -> str:
    """Check planned figure exports against table-figure-plan.md and manifest."""
    try:
        from autor import workspace as ws_mod

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")
        result = ws_mod.figure_status(ws_dir)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        _log.exception("workspace_figure_status failed")
        return _error("internal", str(e))


@mcp.tool()
def workspace_enrich_l3(
    name: str,
    only_missing: bool = True,
    force: bool = False,
    max_retries: int = 2,
) -> str:
    """Generate L3 conclusion cards strictly within a workspace.

    Args:
        name: Workspace name.
        only_missing: Skip papers that already have an L3 card.
        force: Regenerate existing cards.
        max_retries: LLM retry count per paper.
    """
    try:
        from autor import workspace as ws_mod
        from autor.loader import enrich_l3 as _enrich_l3
        from autor.papers import read_meta

        cfg = _get_cfg()
        if not ws_mod.validate_workspace_name(name):
            return _error("invalid_workspace", f"Invalid workspace name: {name}")
        ws_dir = cfg._root / "workspace" / name
        if not ws_dir.exists():
            return _error("not_found", f"Workspace not found: {name}")

        ok = fail = skipped = 0
        papers = []
        for dir_name in sorted(ws_mod.read_dir_names(ws_dir, cfg.index_db)):
            paper_d = cfg.papers_dir / dir_name
            json_path = paper_d / "meta.json"
            md_path = paper_d / "paper.md"
            if not json_path.exists() or not md_path.exists():
                skipped += 1
                papers.append({"paper": dir_name, "status": "skipped", "reason": "missing meta.json or paper.md"})
                continue

            meta = read_meta(paper_d)
            has_l3 = bool(meta.get("l3"))
            if only_missing and has_l3 and not force:
                skipped += 1
                papers.append({"paper": dir_name, "status": "skipped", "reason": "already_has_l3"})
                continue

            success = _enrich_l3(json_path, md_path, cfg, force=force, max_retries=max_retries)
            meta = read_meta(paper_d)
            if success:
                ok += 1
                status = "ok"
            else:
                fail += 1
                status = "failed"
            papers.append(
                {
                    "paper": dir_name,
                    "status": status,
                    "l3_status": meta.get("l3_last_attempt_status"),
                    "stage": meta.get("l3_last_attempt_stage"),
                    "reason": meta.get("l3_last_attempt_reason"),
                    "method": meta.get("l3_last_attempt_method"),
                }
            )

        return json.dumps(
            {
                "workspace": name,
                "ok": ok,
                "failed": fail,
                "skipped": skipped,
                "papers": papers,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        _log.exception("workspace_enrich_l3 failed")
        return _error("internal", str(e))


# ============================================================================
#  Plot, export & diagnostics (4)
# ============================================================================


@mcp.tool()
def plot(
    prompt: str,
    workspace: str | None = None,
    name: str | None = None,
    urls: list[str] | None = None,
    model: str | None = None,
    aspect_ratio: str | None = None,
) -> str:
    """Generate an image via GPT Image 2 and save it into workspace/.

    Args:
        prompt: Image-generation prompt text.
        workspace: Optional workspace name; outputs go to ``workspace/<name>/figure/``.
        name: Optional output filename stem.
        urls: Optional reference image URLs.
        model: Optional model override.
        aspect_ratio: Optional aspect-ratio override.
    """
    try:
        from autor import workspace as ws_mod
        from autor.plot import PlotError, generate_plot

        cfg = _get_cfg()
        if workspace is not None and not ws_mod.validate_workspace_name(workspace):
            return _error("invalid_workspace", f"Invalid workspace name: {workspace}")
        summary = generate_plot(
            prompt,
            cfg=cfg,
            workspace=workspace,
            name=name,
            urls=urls,
            model=model,
            aspect_ratio=aspect_ratio,
        )
        return json.dumps(summary, ensure_ascii=False)
    except PlotError as e:
        return _error("plot_failed", str(e))
    except requests.RequestException as e:
        return _error("upstream", str(e))
    except Exception as e:
        _log.exception("plot failed")
        return _error("internal", str(e))


@mcp.tool()
def export_bibtex(
    paper_refs: list[str] | None = None,
    all_papers: bool = False,
    workspace: str | None = None,
    year: str | None = None,
    journal: str | None = None,
) -> str:
    """Export papers as BibTeX entries.

    Either specify paper_refs for specific papers, or set all_papers=True for all.

    Args:
        paper_refs: List of paper identifiers (optional).
        all_papers: If True, export all papers.
        workspace: Workspace name to export all workspace papers.
        year: Year filter (when all_papers=True).
        journal: Journal name filter (when all_papers=True).
    """
    try:
        from autor import workspace as ws_mod
        from autor.export import export_bibtex as _export

        cfg = _get_cfg()

        if workspace:
            if paper_refs or all_papers:
                return _error("invalid_args", "Use only one of workspace, paper_refs, or all_papers.")
            if not ws_mod.validate_workspace_name(workspace):
                return _error("invalid_workspace", f"Invalid workspace name: {workspace}")
            ws_dir = cfg._root / "workspace" / workspace
            if not ws_dir.exists():
                return _error("not_found", f"Workspace not found: {workspace}")
            dir_names = list(ws_mod.read_dir_names(ws_dir, cfg.index_db))
            bibtex = _export(cfg.papers_dir, paper_ids=dir_names, year=year, journal=journal)
        elif paper_refs and not all_papers:
            # Export specific papers by dir_name
            dir_names = []
            for ref in paper_refs:
                paper_d = _resolve_paper_dir(ref)
                dir_names.append(paper_d.name)
            bibtex = _export(cfg.papers_dir, paper_ids=dir_names)
        elif all_papers:
            bibtex = _export(cfg.papers_dir, year=year, journal=journal)
        else:
            return _error("invalid_args", "Specify paper_refs or set all_papers=True.")

        count = bibtex.count("@")
        return json.dumps({"bibtex": bibtex, "count": count}, ensure_ascii=False)
    except ValueError as e:
        return _error("not_found", str(e))
    except Exception as e:
        _log.exception("export_bibtex failed")
        return _error("internal", str(e))


@mcp.tool()
def audit(severity: str | None = None) -> str:
    """Audit paper data quality: missing fields, DOI duplicates, naming issues, etc.

    Args:
        severity: Filter by severity level: "error", "warning", or "info". None for all.
    """
    try:
        from autor.audit import audit_papers

        cfg = _get_cfg()
        issues = audit_papers(cfg.papers_dir)

        if severity:
            issues = [i for i in issues if i.severity == severity]

        issue_dicts = [
            {"paper_id": i.paper_id, "severity": i.severity, "rule": i.rule, "message": i.message}
            for i in issues
        ]
        summary: dict[str, int] = {}
        for i in issue_dicts:
            summary[i["severity"]] = summary.get(i["severity"], 0) + 1

        return json.dumps({"issues": issue_dicts, "summary": summary}, ensure_ascii=False)
    except Exception as e:
        _log.exception("audit failed")
        return _error("internal", str(e))


@mcp.tool()
def setup_check() -> str:
    """Check the autor environment: dependencies, config, data directories, API keys.

    Returns a structured diagnostic report. Useful for troubleshooting setup issues.
    """
    try:
        from autor.setup import format_check_results, run_check

        cfg = _get_cfg()
        results = run_check(cfg)
        formatted = format_check_results(results)
        result_dicts = [
            {"label": r.label, "ok": r.ok, "detail": r.detail}
            for r in results
        ]
        return json.dumps({"checks": result_dicts, "formatted": formatted}, ensure_ascii=False)
    except Exception as e:
        _log.exception("setup_check failed")
        return _error("internal", str(e))


# ============================================================================
#  Ingest & pipeline tools (4)
# ============================================================================


@mcp.tool()
def pipeline_ingest(
    preset: str = "ingest",
    dry_run: bool = False,
    no_api: bool = False,
    force: bool = False,
) -> str:
    """Run the ingestion pipeline on PDF/markdown files in data/inbox/.

    Place PDF or .md files in data/inbox/, then call this tool to process them.
    The pipeline extracts metadata, deduplicates by DOI, and moves papers
    to data/papers/. Afterwards it rebuilds the node-level FTS5 evidence index.

    Presets: "ingest" (full), "reindex" (rebuild index only),
    "md-only" (skip MinerU, process .md files only).

    This is a long-running operation (may take minutes for PDFs).

    Args:
        preset: Pipeline preset name (default "ingest").
        dry_run: If True, show what would happen without making changes.
        no_api: If True, skip external API calls for metadata enrichment.
        force: If True, force re-processing even if already done.
    """
    try:
        from autor.ingest.pipeline import PRESETS, run_pipeline

        cfg = _get_cfg()

        if preset not in PRESETS:
            return _error("invalid_args",
                          f"Unknown preset '{preset}'. Available: {', '.join(PRESETS)}")

        step_names = PRESETS[preset]
        opts = {
            "dry_run": dry_run,
            "no_api": no_api,
            "force": force,
            "inspect": False,
            "max_retries": 3,
            "rebuild": False,
        }
        run_pipeline(step_names, cfg, opts)
        return json.dumps({"status": "ok", "preset": preset, "dry_run": dry_run})
    except ImportError as e:
        mod = getattr(e, "name", "") or ""
        return _error("missing_dependency", f"Missing dependency: {mod}",
                       install_hint="pip install autor[full]")
    except Exception as e:
        _log.exception("pipeline_ingest failed")
        return _error("internal", str(e))


@mcp.tool()
def import_endnote(
    files: list[str],
    no_api: bool = False,
    dry_run: bool = False,
    no_convert: bool = False,
) -> str:
    """Import papers from Endnote XML or RIS export files.

    Automatically matches PDFs from the Endnote library data directory,
    converts them via MinerU, and indexes the imported papers.

    This is a long-running operation.

    Args:
        files: List of file paths to Endnote XML or RIS files.
        no_api: Skip external API calls for metadata enrichment.
        dry_run: Preview what would be imported without making changes.
        no_convert: Skip MinerU PDF conversion (import metadata only).
    """
    try:
        from autor.sources.endnote import parse_endnote_full
    except ImportError:
        return _error("missing_dependency", "Endnote import dependencies not installed.",
                       install_hint="pip install autor[import]")
    try:
        from autor.ingest.pipeline import import_external

        cfg = _get_cfg()
        paths = [Path(f) for f in files]
        for p in paths:
            if not p.exists():
                return _error("not_found", f"File not found: {p}")

        records, pdf_paths = parse_endnote_full(paths)
        if not records:
            return json.dumps({"status": "empty", "message": "No records parsed"})

        stats = import_external(
            records, cfg,
            pdf_paths=pdf_paths,
            no_api=no_api,
            dry_run=dry_run,
        )

        # Batch convert PDFs → paper.md + enrich (toc/l3/abstract)
        convert_stats: dict = {}
        if not dry_run and not no_convert and stats["ingested"] > 0:
            from autor.ingest.pipeline import batch_convert_pdfs
            convert_stats = batch_convert_pdfs(cfg, enrich=True)

        return json.dumps({"status": "ok", **stats, "conversion": convert_stats, "dry_run": dry_run})
    except Exception as e:
        _log.exception("import_endnote failed")
        return _error("internal", str(e))


@mcp.tool()
def import_zotero(
    api_key: str | None = None,
    library_id: str | None = None,
    library_type: str = "user",
    local: str | None = None,
    collection: str | None = None,
    list_collections: bool = False,
    no_api: bool = False,
    dry_run: bool = False,
    no_convert: bool = False,
) -> str:
    """Import papers from Zotero (Web API or local SQLite database).

    Supports two modes:
    - Web API: provide api_key and library_id (or configure in config.local.yaml)
    - Local: provide the path to zotero.sqlite

    Use list_collections=True to see available collections before importing.

    This is a long-running operation.

    Args:
        api_key: Zotero Web API key (optional, uses config if not provided).
        library_id: Zotero library ID (optional, uses config if not provided).
        library_type: Library type: "user" or "group" (default "user").
        local: Path to local Zotero SQLite database (alternative to API mode).
        collection: Collection key to import (optional, imports all if not set).
        list_collections: If True, only list collections without importing.
        no_api: Skip external metadata enrichment APIs.
        dry_run: Preview without making changes.
        no_convert: Skip MinerU PDF conversion.
    """
    try:
        cfg = _get_cfg()

        # Resolve credentials
        _api_key = api_key or cfg.resolved_zotero_api_key()
        _library_id = library_id or cfg.resolved_zotero_library_id()
        _library_type = library_type or cfg.zotero.library_type

        if local:
            db_path = Path(local)
            if not db_path.exists():
                return _error("not_found", f"Zotero database not found: {db_path}")

            from autor.sources.zotero import list_collections_local, parse_zotero_local

            if list_collections:
                collections = list_collections_local(db_path)
                return json.dumps(collections, ensure_ascii=False)

            records, pdf_paths = parse_zotero_local(
                db_path, collection_key=collection,
            )
        else:
            if not _api_key:
                return _error("missing_config",
                              "Zotero API key required. Set --api-key, config.local.yaml, or ZOTERO_API_KEY env var.")
            if not _library_id:
                return _error("missing_config",
                              "Zotero library ID required. Set --library-id, config.local.yaml, or ZOTERO_LIBRARY_ID env var.")

            try:
                from autor.sources.zotero import fetch_zotero_api, list_collections_api
            except ImportError:
                return _error("missing_dependency", "Zotero import dependencies not installed.",
                               install_hint="pip install autor[import]")

            if list_collections:
                collections = list_collections_api(_library_id, _api_key, library_type=_library_type)
                return json.dumps(collections, ensure_ascii=False)

            import tempfile
            pdf_dir = Path(tempfile.mkdtemp(prefix="autor_zotero_"))
            records, pdf_paths = fetch_zotero_api(
                _library_id, _api_key,
                library_type=_library_type,
                collection_key=collection,
                download_pdfs=True,
                pdf_dir=pdf_dir,
            )

        if not records:
            return json.dumps({"status": "empty", "message": "No records found"})

        from autor.ingest.pipeline import import_external
        stats = import_external(
            records, cfg,
            pdf_paths=pdf_paths,
            no_api=no_api,
            dry_run=dry_run,
        )

        # Batch convert PDFs → paper.md + enrich (toc/l3/abstract)
        convert_stats: dict = {}
        if not dry_run and not no_convert and stats["ingested"] > 0:
            from autor.ingest.pipeline import batch_convert_pdfs
            convert_stats = batch_convert_pdfs(cfg, enrich=True)

        return json.dumps({"status": "ok", **stats, "conversion": convert_stats, "dry_run": dry_run})
    except ImportError as e:
        mod = getattr(e, "name", "") or ""
        return _error("missing_dependency", f"Missing dependency: {mod}",
                       install_hint="pip install autor[import]")
    except Exception as e:
        _log.exception("import_zotero failed")
        return _error("internal", str(e))


@mcp.tool()
def attach_pdf(paper_ref: str, pdf_path: str) -> str:
    """Attach a PDF to an existing paper, converting it to markdown via MinerU.

    Replaces any existing paper.md. After conversion, updates the abstract
    if missing and rebuilds the search index.

    Args:
        paper_ref: Paper identifier (directory name, UUID, or DOI).
        pdf_path: Absolute path to the PDF file.
    """
    try:
        import shutil

        from autor.papers import read_meta, write_meta

        cfg = _get_cfg()
        paper_d = _resolve_paper_dir(paper_ref)
        src = Path(pdf_path)
        if not src.exists():
            return _error("not_found", f"PDF file not found: {pdf_path}")

        # Copy PDF
        dest_pdf = paper_d / src.name
        shutil.copy2(str(src), str(dest_pdf))

        # Convert via MinerU
        from autor.ingest.mineru import ConvertOptions, check_server, convert_pdf, strip_markdown_images

        mineru_opts = ConvertOptions(
            api_url=cfg.ingest.mineru_endpoint,
            output_dir=paper_d,
        )

        if check_server(cfg.ingest.mineru_endpoint):
            result = convert_pdf(dest_pdf, mineru_opts)
        else:
            api_keys = cfg.resolved_mineru_api_keys()
            if not api_keys:
                return _error("missing_config",
                              "MinerU not reachable and no cloud API key configured.")
            from autor.ingest.mineru import convert_pdf_cloud
            result = convert_pdf_cloud(
                dest_pdf, mineru_opts,
                api_key=api_keys[0],
                cloud_url=cfg.ingest.mineru_cloud_url,
            )

        if not result.success:
            return _error("conversion_failed", f"MinerU conversion failed: {result.error}")

        # Move output to paper.md
        paper_md = paper_d / "paper.md"
        if result.md_path and result.md_path != paper_md:
            if paper_md.exists():
                paper_md.unlink()
            shutil.move(str(result.md_path), str(paper_md))
        if paper_md.exists():
            paper_md.write_text(strip_markdown_images(paper_md.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")

        # Clean up MinerU artifacts; images are not retained.
        for pattern in ["*_layout.json", "*_content_list.json", "*_origin.pdf"]:
            for f in paper_d.glob(pattern):
                f.unlink(missing_ok=True)
        for img_dir in list(paper_d.glob("*_images")) + list(paper_d.glob("*_mineru_images")) + [paper_d / "images"]:
            if img_dir.is_dir():
                shutil.rmtree(img_dir)

        # Backfill abstract
        try:
            data = read_meta(paper_d)
            if not data.get("abstract") and paper_md.exists():
                from autor.ingest.metadata import extract_abstract_from_md
                abstract = extract_abstract_from_md(paper_md, cfg)
                if abstract:
                    data["abstract"] = abstract
                    write_meta(paper_d, data)
        except (ValueError, FileNotFoundError):
            pass

        return json.dumps({"status": "ok", "paper": paper_d.name})
    except ValueError as e:
        return _error("not_found", str(e))
    except Exception as e:
        _log.exception("attach_pdf failed")
        return _error("internal", str(e))


# ============================================================================
#  Enrichment tools (4)
# ============================================================================


@mcp.tool()
def enrich_toc(paper_ref: str, force: bool = False) -> str:
    """Extract table of contents from a paper using LLM.

    Requires LLM API key (DeepSeek) in config.

    Args:
        paper_ref: Paper identifier.
        force: Re-extract even if TOC already exists.
    """
    try:
        from autor.loader import enrich_toc as _enrich_toc

        cfg = _get_cfg()
        paper_d = _resolve_paper_dir(paper_ref)
        json_path = paper_d / "meta.json"
        md_path = paper_d / "paper.md"

        if not md_path.exists():
            return _error("not_found", f"No paper.md in {paper_d.name}")

        success = _enrich_toc(json_path, md_path, cfg, force=force)
        return json.dumps({"status": "ok" if success else "failed", "paper": paper_d.name})
    except ValueError as e:
        return _error("not_found", str(e))
    except Exception as e:
        _log.exception("enrich_toc failed")
        return _error("internal", str(e))


@mcp.tool()
def enrich_l3(paper_ref: str, force: bool = False) -> str:
    """Generate the L3 paper-level conclusion card using LLM.

    Requires LLM API key (DeepSeek) in config.

    Args:
        paper_ref: Paper identifier.
        force: Regenerate even if L3 already exists.
    """
    try:
        from autor.loader import enrich_l3 as _enrich_l3
        from autor.papers import read_meta

        cfg = _get_cfg()
        paper_d = _resolve_paper_dir(paper_ref)
        json_path = paper_d / "meta.json"
        md_path = paper_d / "paper.md"

        if not md_path.exists():
            return _error("not_found", f"No paper.md in {paper_d.name}")

        success = _enrich_l3(json_path, md_path, cfg, force=force)
        meta = read_meta(paper_d)
        return json.dumps(
            {
                "status": "ok" if success else "failed",
                "paper": paper_d.name,
                "l3_status": meta.get("l3_last_attempt_status"),
                "stage": meta.get("l3_last_attempt_stage"),
                "reason": meta.get("l3_last_attempt_reason"),
                "method": meta.get("l3_last_attempt_method"),
            }
        )
    except ValueError as e:
        return _error("not_found", str(e))
    except Exception as e:
        _log.exception("enrich_l3 failed")
        return _error("internal", str(e))


@mcp.tool()
def refetch(
    paper_ref: str | None = None,
    all_papers: bool = False,
    force: bool = False,
    workspace: str | None = None,
) -> str:
    """Refetch citation counts and bibliographic details from external APIs.

    Specify a single paper, a workspace, or set all_papers=True.

    Args:
        paper_ref: Single paper identifier (optional).
        workspace: Optional workspace name to refetch only that corpus.
        all_papers: If True, refetch all papers missing citation data.
        force: If True, refetch all papers regardless of existing data.
    """
    try:
        import json as _json

        from autor import workspace as ws_mod
        from autor.ingest.metadata import refetch_metadata
        from autor.papers import iter_paper_dirs

        cfg = _get_cfg()

        if paper_ref:
            paper_d = _resolve_paper_dir(paper_ref)
            jp = paper_d / "meta.json"
            changed = refetch_metadata(jp)
            return _json.dumps({"status": "ok", "changed": changed, "paper": paper_d.name})
        elif workspace or all_papers:
            if workspace:
                if not ws_mod.validate_workspace_name(workspace):
                    return _error("invalid_workspace", f"Invalid workspace name: {workspace}")
                ws_dir = cfg._root / "workspace" / workspace
                if not ws_dir.exists():
                    return _error("not_found", f"Workspace not found: {workspace}")
                targets = []
                for entry in ws_mod.read_entries(ws_dir):
                    dir_name = entry.get("dir_name", "")
                    jp = cfg.papers_dir / dir_name / "meta.json"
                    if jp.exists():
                        targets.append(jp)
                targets = sorted(set(targets))
            else:
                targets = sorted(d / "meta.json" for d in iter_paper_dirs(cfg.papers_dir))
            if not force:
                filtered = []
                for jp in targets:
                    data = _json.loads(jp.read_text(encoding="utf-8"))
                    if not data.get("doi"):
                        continue
                    if (
                        not data.get("citation_count")
                        or not data.get("references")
                        or not all(data.get(k) for k in ("volume", "publisher"))
                    ):
                        filtered.append(jp)
                targets = filtered

            ok = fail = skip = 0
            for jp in targets:
                try:
                    changed = refetch_metadata(jp)
                    if changed:
                        ok += 1
                    else:
                        skip += 1
                except Exception:
                    fail += 1
            return _json.dumps(
                {
                    "status": "ok",
                    "workspace": workspace,
                    "target_count": len(targets),
                    "updated": ok,
                    "skipped": skip,
                    "failed": fail,
                }
            )
        else:
            return _error("invalid_args", "Specify paper_ref, workspace, or set all_papers=True.")
    except ValueError as e:
        return _error("not_found", str(e))
    except Exception as e:
        _log.exception("refetch failed")
        return _error("internal", str(e))


@mcp.tool()
def backfill_abstract(dry_run: bool = False) -> str:
    """Backfill missing abstracts for papers that have paper.md but no abstract.

    Uses regex extraction, DOI-based fetch, and optionally LLM extraction.

    Args:
        dry_run: If True, show what would be updated without making changes.
    """
    try:
        from autor.ingest.metadata import extract_abstract_from_md
        from autor.papers import iter_paper_dirs, read_meta, write_meta

        cfg = _get_cfg()
        updated = skipped = 0

        for pdir in iter_paper_dirs(cfg.papers_dir):
            try:
                meta = read_meta(pdir)
            except (ValueError, FileNotFoundError):
                continue
            if meta.get("abstract"):
                continue
            md_path = pdir / "paper.md"
            if not md_path.exists():
                continue

            abstract = extract_abstract_from_md(md_path, cfg)
            if abstract:
                if not dry_run:
                    meta["abstract"] = abstract
                    write_meta(pdir, meta)
                updated += 1
            else:
                skipped += 1

        return json.dumps({"status": "ok", "updated": updated, "skipped": skipped, "dry_run": dry_run})
    except Exception as e:
        _log.exception("backfill_abstract failed")
        return _error("internal", str(e))


# ============================================================================
#  Rename tool (1)
# ============================================================================


@mcp.tool()
def rename_paper(
    paper_ref: str | None = None,
    all_papers: bool = False,
    dry_run: bool = False,
) -> str:
    """Rename paper directories to match metadata (Author-Year-Title format).

    Args:
        paper_ref: Single paper identifier (optional).
        all_papers: If True, rename all papers.
        dry_run: If True, show what would be renamed without making changes.
    """
    try:
        from autor.ingest.metadata import generate_new_stem, rename_files
        from autor.papers import iter_paper_dirs, read_meta

        cfg = _get_cfg()

        if paper_ref:
            targets = [_resolve_paper_dir(paper_ref)]
        elif all_papers:
            targets = sorted(iter_paper_dirs(cfg.papers_dir))
        else:
            return _error("invalid_args", "Specify paper_ref or set all_papers=True.")

        renamed = skipped = 0
        results = []
        for paper_d in targets:
            try:
                meta = read_meta(paper_d)
            except (ValueError, FileNotFoundError):
                skipped += 1
                continue

            from autor.ingest.metadata import PaperMetadata
            pm = PaperMetadata()
            for k, v in meta.items():
                if hasattr(pm, k):
                    setattr(pm, k, v)

            new_stem = generate_new_stem(pm)
            if new_stem == paper_d.name:
                skipped += 1
                continue

            if not dry_run:
                md_path = paper_d / "paper.md"
                json_path = paper_d / "meta.json"
                rename_files(md_path, json_path, new_stem, dry_run=False)
            renamed += 1
            results.append({"old": paper_d.name, "new": new_stem})

        return json.dumps({
            "status": "ok", "renamed": renamed, "skipped": skipped,
            "dry_run": dry_run, "changes": results,
        }, ensure_ascii=False)
    except ValueError as e:
        return _error("not_found", str(e))
    except Exception as e:
        _log.exception("rename_paper failed")
        return _error("internal", str(e))


# ============================================================================
#  WriteAgent tools
# ============================================================================


@mcp.tool()
def write_agent_preflight(workspace: str) -> str:
    """Validate canonical planning-package inputs before write-agent drafting."""
    try:
        from autor.write_agent import runner

        cfg = _get_cfg()
        return json.dumps(runner.preflight(workspace, cfg).to_dict(), ensure_ascii=False)
    except Exception as e:
        _log.exception("write_agent_preflight failed")
        return _error("internal", str(e))


@mcp.tool()
def write_agent_build(workspace: str) -> str:
    """Build section kernels and seed bank for a workspace."""
    try:
        from autor.write_agent import runner

        cfg = _get_cfg()
        return json.dumps(runner.build(workspace, cfg).to_dict(), ensure_ascii=False)
    except Exception as e:
        _log.exception("write_agent_build failed")
        return _error("internal", str(e))


@mcp.tool()
def write_agent_run(workspace: str, section: str | None = None, round: int = 1) -> str:
    """Generate gated manuscript candidates and update write.md anchors."""
    try:
        from autor.write_agent import runner

        cfg = _get_cfg()
        sections = [section] if section else None
        return json.dumps(runner.run(workspace, cfg, sections=sections, round_no=round).to_dict(), ensure_ascii=False)
    except Exception as e:
        _log.exception("write_agent_run failed")
        return _error("internal", str(e))


@mcp.tool()
def write_agent_write(workspace: str, section: str | None = None, round: int = 1) -> str:
    """Run preflight/build/run and leave the manuscript ready for polish."""
    try:
        from autor.write_agent import runner

        cfg = _get_cfg()
        sections = [section] if section else None
        return json.dumps(runner.write(workspace, cfg, sections=sections, round_no=round).to_dict(), ensure_ascii=False)
    except Exception as e:
        _log.exception("write_agent_write failed")
        return _error("internal", str(e))


@mcp.tool()
def write_agent_polish(workspace: str, round: int = 1, in_place: bool = True) -> str:
    """Polish anchored write.md sections and rerun internal pattern gates."""
    try:
        from autor.write_agent import runner

        cfg = _get_cfg()
        return json.dumps(runner.polish(workspace, cfg, round_no=round, in_place=in_place).to_dict(), ensure_ascii=False)
    except Exception as e:
        _log.exception("write_agent_polish failed")
        return _error("internal", str(e))


@mcp.tool()
def write_agent_revise(workspace: str, ticket_paths: list[str]) -> str:
    """Revise affected anchors from external critic/check ticket files."""
    try:
        from autor.write_agent import runner

        cfg = _get_cfg()
        return json.dumps(runner.revise(workspace, cfg, ticket_paths).to_dict(), ensure_ascii=False)
    except Exception as e:
        _log.exception("write_agent_revise failed")
        return _error("internal", str(e))


@mcp.tool()
def write_agent_status(workspace: str) -> str:
    """Return write-agent state for a workspace."""
    try:
        from autor.write_agent import runner

        cfg = _get_cfg()
        return json.dumps(runner.status(workspace, cfg), ensure_ascii=False)
    except Exception as e:
        _log.exception("write_agent_status failed")
        return _error("internal", str(e))


@mcp.tool()
def write_agent_clean(workspace: str) -> str:
    """Clean old write/QA artifacts while preserving literature preparation files."""
    try:
        from autor.write_agent.orchestrator import clean_workspace

        cfg = _get_cfg()
        return json.dumps(clean_workspace(cfg._root, workspace), ensure_ascii=False)
    except Exception as e:
        _log.exception("write_agent_clean failed")
        return _error("internal", str(e))


@mcp.tool()
def write_agent_audit(workspace: str) -> str:
    """Audit manuscript completion, citation coverage, and section depth contracts."""
    try:
        from autor.write_agent.orchestrator import audit_completion

        cfg = _get_cfg()
        return json.dumps(audit_completion(cfg._root, workspace), ensure_ascii=False)
    except Exception as e:
        _log.exception("write_agent_audit failed")
        return _error("internal", str(e))


@mcp.tool()
def write_agent_orchestrate(workspace: str, rounds: int = 1, clean: bool = False, execute: bool = False) -> str:
    """Run deterministic write orchestration, completion audit, and strategy comparison."""
    try:
        from autor.write_agent.orchestrator import orchestrate

        cfg = _get_cfg()
        return json.dumps(
            orchestrate(cfg._root, workspace, cfg=cfg, rounds=rounds, clean=clean, execute=execute),
            ensure_ascii=False,
        )
    except Exception as e:
        _log.exception("write_agent_orchestrate failed")
        return _error("internal", str(e))


# ============================================================================
#  Entry point
# ============================================================================


def main():
    """Entry point for autor-mcp command."""
    mcp.run()


if __name__ == "__main__":
    main()
