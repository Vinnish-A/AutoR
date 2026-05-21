# autor — Coding Agent Instructions

> This file provides project instructions for any AI coding agent (Codex, OpenClaw, etc.).
> Claude Code users: see `CLAUDE.md` for the Claude-specific version of these instructions.

## Project Overview

autor is a research terminal built around AI coding agents. Users interact with a local academic knowledge base through natural language, performing literature search, reading, discussion, analysis, and writing — all via CLI tools. The `autor` Python package provides the infrastructure (PDF parsing, auditable node-level retrieval, citation graphs, etc.), and the coding agent is responsible for understanding user intent, invoking the right CLI commands, integrating results, and engaging in academic discussion.

### Interaction Model

Users interact with their knowledge base through you (the coding agent) using natural language. Your role is to understand user intent, invoke the appropriate CLI commands, synthesize results, and participate in academic discussions.

MinerU-parsed Markdown preserves high-quality formulas (LaTeX) and structured text, but image extraction is intentionally disabled and image attachments are discarded during ingest. This keeps inbox and paper directories text-first and avoids uncontrolled MinerU image artifacts. Use explicit user-provided images or generated figures from `autor/plot.py` when image analysis is required, enabling you to:
- **Derive formulas**: Work with mathematical formulas from papers — derive, verify, and extend them
- **Write verification code**: Implement analysis code based on paper methods, run tests, and cross-validate paper conclusions with computed results
- **Multi-modal verification**: Combine text, formulas, and explicitly provided/generated images to assess paper reliability

Your role goes beyond tool invocation — you are the user's **research partner**:
- **Exploration**: Help discover connections between papers, cross-topic links, and overlooked research directions
- **Discussion**: Question paper claims, point out contradictions, suggest comparative angles
- **Research support**: Proactively suggest search strategies and recommend related papers based on the user's research questions
- **Writing assistance**: Help structure literature reviews, summarize the state of research, and identify research gaps
- **Claim verification**: When the user makes an academic judgment, help verify or challenge it using evidence from the knowledge base
- **Programming**: Write code to reproduce paper methods, run comparative experiments, and create data visualizations

### Academic Attitude

Paper conclusions are the authors' **claims**, not established truths. Approach the literature with the mindset of a seasoned scholar:
- **Don't blindly trust authority**: Even top-journal papers may have limitations, methodological flaws, or overclaims
- **Multi-dimensional judgment**: Evaluate comprehensively — journal reputation, author background, citation count, experimental conditions, peer feedback
- **Cross-validation**: When multiple papers reach different conclusions on the same question, proactively point out discrepancies and analyze possible reasons
- **Dialectical discussion**: Be willing to question paper claims, supporting judgments with evidence and logic rather than citation counts
- **Distinguish facts from opinions**: Clearly label which conclusions are backed by experimental data and which are the authors' speculation or interpretation

The goal is to help users get closer to scientific truth through argumentation and evidence, not merely to restate the literature.

You are not a passive tool awaiting instructions, but an active collaborator. Proactively ask questions, propose hypotheses, point out angles the user may have overlooked, and offer your own judgments based on the literature. Load information progressively (L1→L4) — avoid dumping large amounts of content all at once.

The above are baseline capabilities. Feel free to combine CLI tools and the coding agent's native abilities (reading/writing files, running code, multi-turn reasoning) to discover more powerful workflows — batch-comparing methodological differences across papers, auto-generating research trend reports, finding undervalued key papers from citation graphs. The tools are finite, but their combinations are open-ended.

## Module Overview

| Module | Function |
|--------|----------|
| `ingest/mineru.py` | PDF → MinerU Markdown (cloud API / local) |
| `ingest/extractor.py` | Metadata extraction (regex / auto / robust / llm — 4 modes) |
| `ingest/metadata/` | API query completion (Crossref / S2 / OpenAlex / PubMed), JSON output, file renaming |
| `ingest/pipeline.py` | Composable ingest pipeline (DOI / PMID dedup + pending + external import batch conversion) |
| `index.py` | Node-level FTS5 evidence search + bundle/trace/verify + papers_registry + citations graph |
| `loader.py` | L1-L4 layered loading + enrich_toc + enrich_l3 |
| `explore.py` | Multi-dimensional literature exploration (OpenAlex multi-filter + FTS5 search, isolated in `data/explore/`) |
| `workspace.py` | Workspace paper subset management, evidence export, screening, and planning-package skeletons |
| `export.py` | BibTeX export |
| `audit.py` | Data quality audit + repair |
| `sources/` | Data source adapters (local / endnote / zotero) |
| `cli.py` | Full CLI entry point |
| `mcp_server.py` | MCP server tools |
| `setup.py` | Environment detection + setup wizard |
| `metrics.py` | LLM token usage + API timing |

CLI command reference: `autor --help`

## Architecture

```
PDF → mineru.py → .md     (or place .md directly to skip MinerU)
                   ↓
             extractor.py (Stage 1: extract fields from md header; regex/auto/robust/llm)
             metadata/    (Stage 2: API query completion, JSON output, file renaming)
                   ↓
             pipeline.py  (DOI dedup check)
               ├─ Has DOI → data/papers/<Author-Year-Title>/meta.json + paper.md
               └─ No DOI  → data/pending/ (awaiting manual confirmation)
                   ↓
             index.py → data/index.db (paper_nodes + paper_node_fts + registry + citations)
                   ↓
             cli.py → skills → coding agent

explore.py — Multi-dimensional literature exploration (independent data flow, isolated from main library)
  OpenAlex API (multi-filter: ISSN/concept/author/institution/keyword/source-type etc.)
    → data/explore/<name>/papers.jsonl (supports incremental update, DOI-based dedup)
                 → explore.db (explore_fts FTS5 full-text index)
  Search: deterministic keyword/node FTS5; no vector/FAISS modes

workspace.py — Workspace paper subset management (thin layer, reuses search/export)
  workspace/<name>/papers.json → references papers in data/papers/ (UUID index)
  Search/export via paper_ids parameter injected into search()/export_bibtex()
  Status/evidence/planning helpers:
    autor ws status <name> [--papers]
    autor ws export-evidence <name> [-o FILE]
    autor ws screen <name> --criteria TEXT [--target N] [--apply]
    autor ws plan-package <name> [--title TITLE] [--criteria TEXT]
    autor ws citation-coverage <name> [--manuscript FILE] [--require retained|citable|must_cite]
    autor ws figure-status <name> [--fail-if-missing]
    autor plot "prompt" -w <name> --name F1-overview
  Pipeline workspace semantics:
    - inbox pipelines add only newly persisted papers to the workspace
    - non-inbox pipelines such as `pipeline enrich -w <name>` are restricted to existing workspace papers

import-endnote / import-zotero — External reference manager import (full pipeline)
  sources/endnote.py | sources/zotero.py → parse metadata + match PDFs
    → pipeline.import_external() → DOI dedup + ingest + PDF copy + FTS5 index
    → pipeline.batch_convert_pdfs(enrich=True)
       → batch PDF→MD (cloud batch API, per-token batch size: config ingest.mineru_cloud_batch_size)
       → abstract backfill + toc + l3 extraction + FTS5 index
```

### Layered Loading Design (L1-L4)

| Level | Content | Source |
|-------|---------|--------|
| L1 | title, authors, year, journal, doi, pmid, volume, issue, pages, publisher, issn | JSON file |
| L2 | abstract | JSON field |
| L3 | paper-level conclusion card: explicit conclusion when available, otherwise constrained synthesis from abstract/results/discussion/tables and captions | JSON field (generated by normal ingest or enrich-l3) |
| L4 | full markdown | Read .md directly |

### data/papers/ Directory Structure

```
data/papers/
└── <Author-Year-Title>/
    ├── meta.json    # L1+L2+L3 metadata (includes "id": "<uuid>")
    ├── paper.md     # L4 source (MinerU output, image links stripped)
    ├── layout.json  # MinerU layout analysis (optional)
    └── *_content_list.json  # MinerU structured content (optional)
```

Each paper has its own directory. UUID serves as the internal unique identifier (written to `meta.json["id"]`, never changes).
Directory name is human-readable `Author-Year-Title`; rename only changes the directory name.
`data/index.db` contains a `papers_registry` table providing UUID ↔ DOI/PMID ↔ dir_name bidirectional lookup.

### data/inbox/ Directory

```
data/inbox/
├── paper.pdf     # PDF awaiting ingest (deleted after pipeline processing)
└── paper.md      # Or place .md directly (skip MinerU, ingest directly)
```

### data/inbox-thesis/ Directory

```
data/inbox-thesis/
└── thesis.pdf    # Thesis PDF (auto-tagged paper_type: thesis, skips DOI dedup)
```

Note: Papers without DOI in the regular inbox are auto-classified by LLM — if thesis, tagged and ingested; otherwise moved to pending.
The thesis inbox skips this classification and ingests directly.

### data/inbox-doc/ Directory

```
data/inbox-doc/
├── report.pdf    # Non-paper document PDF (technical reports, standards, lecture notes, etc.)
└── notes.md      # Or place .md directly
```

Non-paper document ingest flow:
- Skips DOI dedup and API queries
- LLM auto-generates title and summary (ensures search indexability)
- Without LLM, degrades: first markdown heading or filename → title, first 500 words → summary
- paper_type tagged as `document` (or specific type: `technical-report` / `lecture-notes` / etc.)
- Audit rules skip `missing_doi` warning for document types

Long PDFs (default >100 pages) are auto-split into shorter PDFs, parsed separately, then merged.

### data/pending/ Directory

```
data/pending/
└── <PDF-stem>/
    ├── paper.md           # Paper markdown without DOI
    ├── <original-name>.pdf # Original PDF (if available)
    ├── pending.json       # Marker file (reason + extracted metadata)
    ├── layout.json        # MinerU layout info (if any)
    └── *_content_list.json # MinerU structured content (if any)
```

`pending.json` `issue` field indicates the reason:
- `no_doi` — No DOI and not a thesis; needs manual confirmation before adding DOI and ingesting
- `duplicate` — DOI duplicates an existing paper (includes `duplicate_of` field pointing to existing paper directory); user can decide to overwrite

Note: Theses are auto-ingested (from thesis inbox or LLM classification) and never go to pending.

### data/explore/ Directory

```
data/explore/<name>/
├── papers.jsonl        # Papers fetched from OpenAlex (title/abstract/authors/year/doi/cited_by_count)
├── meta.json           # Exploration metadata (query params/count/fetched_at)
└── explore.db          # SQLite explore_fts FTS5 full-text index
```

### sources/ Abstraction Layer

`sources/local.py` iterates `data/papers/` subdirectories, yielding `(paper_id, meta_dict, md_path)` tuples (paper_id is UUID).
`papers.py` provides path helpers; all modules access paper paths through it.

## Configuration

Main config: `config.yaml` (tracked in git)
Sensitive info: `config.local.yaml` (not tracked, overrides config.yaml)

LLM API key lookup order:
1. `config.local.yaml` → `llm.api_key`
2. Environment variable `AUTOR_LLM_API_KEY`
3. Environment variable `DEEPSEEK_API_KEY`
4. Environment variable `OPENAI_API_KEY`

Default LLM backend: DeepSeek (`deepseek-chat`), OpenAI-compatible protocol.
`ingest.extractor: robust` (default) — regex + LLM dual-run; LLM corrects OCR errors + full-text multi-DOI detection. Other modes: `auto` (LLM fallback only), `regex` (pure regex), `llm` (pure LLM).

## Agent Skills

Skills are authored in `.github/skills/`; `.agents/skills/` and
`.claude/skills/` should expose the same skill tree for cross-agent discovery.
Each skill is a folder with a `SKILL.md` entry point following the
[Agent Skills](https://agentskills.io) standard.

Do not maintain a long hand-written skill inventory in this file. It becomes
stale quickly and can cause agents to call removed commands. When a task maps
to a skill, read the relevant `.github/skills/<name>/SKILL.md` directly and
follow its current commands. When changing CLI, MCP, config, or data contracts,
update the affected skill files in the same change.

Skill selection should follow capability, not habit:
- Knowledge-base work: search, show, ingest, enrich, index, workspace, export, import, audit, graph/citations, explore, insights, trials.
- Writing work: plan, write, literature-review, paper-writing, update, citation-check, polish, review-response, research-gap, check.
- System and output work: setup, metrics, document, draw, plot-related helpers.

Search-related skills must use the canonical retrieval surface:
`autor search` for paper retrieval and `autor research` for evidence bundles.
Do not instruct agents to call removed vector, hybrid, topic-model, or alias
commands.

## Getting Started

When the project is not yet configured, use `autor setup` to guide the user:

1. **Diagnose**: Run `autor setup check` to see current status
2. **Install**: `pip install -e .` (core) or `pip install -e ".[full]"` (all features)
3. **Configure**: Run `autor setup` interactive wizard (bilingual EN/ZH), auto-creates `config.yaml` + `config.local.yaml`
4. **Directories**: Auto-created on CLI startup (`ensure_dirs()`), no manual action needed

### Bash Environment and Service Startup

When operating from bash/WSL, prefer the repository scripts instead of ad-hoc service commands:

1. Activate the project environment first:
  - `cd /mnt/f/AutoR`
  - `source .venv/bin/activate`
2. Start long-running local services with `scripts/start.sh`:
  - Starts local MinerU on `127.0.0.1:8000`
  - Starts the Records-backed AutoDownload service on the Windows side, default `127.0.0.1:8001`
3. Start MCP for a client with `scripts/run-mcp.sh`:
  - `autor-mcp` uses **stdio**, not an HTTP daemon
  - Do **not** daemonize MCP in `start.sh` / `stop.sh`
4. Stop long-running local services with `scripts/stop.sh`

Useful environment variables for bash sessions:

- `AUTOR_ROOT`: repo root, default detected from script location
- `AUTOR_VENV`: override virtualenv path, default `.venv`
- `AUTOR_WINDOWS_POWERSHELL`: explicit Windows PowerShell path if WSL cannot find `powershell.exe` / `pwsh.exe`
- `AUTOR_MINERU_PORT`: override MinerU port, default `8000`
- `AUTOR_AUTODOWNLOAD_PORT`: override the Records service port, default `8001`
- `AUTOR_AUTODOWNLOAD_WIN_DIR`: override the Windows-side Records repo path, default `F:\Records` (`/mnt/f/Records` from WSL)

API key notes:
- **LLM key** (DeepSeek / OpenAI): Metadata extraction + content enrichment. Without it, falls back to pure regex; enrich unavailable
- **MinerU key**: PDF → Markdown cloud conversion. Without it, only manual `.md` placement works
- Vector/FAISS search has been removed. Run `autor index --rebuild` to refresh the node-level FTS5 evidence index, and use `autor search` or `autor research`.

## Key Conventions

- **Workspace isolation**: All user output (writing, notes, drafts) goes in the `workspace/` directory. When creating new files (literature reviews, research notes), default to `workspace/`, not the project root or `autor/` source directory
- **Workspace-scoped enrichment**: For existing review corpora, prefer `autor pipeline enrich -w <name>` or `autor enrich-l3 --workspace <name> --only-missing` so L3/TOC/index work stays inside the workspace.
- **Do not modify `metadata/_extract.py` regex logic** — extend only through the extractor abstraction layer
- `data/`, `workspace/` are not tracked in git (.gitignore configured)
- Python 3.10+, runtime environment: conda `autor`
- Tests: `python -m pytest tests/ -v`

## Development Discipline

Prefer the smallest useful system. Do not add structure, length, prompts, wrappers,
compatibility shims, or new files by default. Add them only when there is clear
evidence that they improve reliability, traceability, speed, maintainability, or
user workflow; acceptable evidence includes a failing test, a benchmark,
measured runtime/cost data, a concrete bug, or repeated code that cannot be
kept correct locally.

Hard rules for development work:
- **Delete obsolete paths instead of preserving aliases** when an interface has been abandoned. A compatibility layer is allowed only when current user data would otherwise become unreadable, and it must be documented as a temporary data-migration concern rather than a normal feature.
- **Keep one canonical path per capability**. Search is `autor search` / `autor research` over node-level FTS5 evidence; do not reintroduce parallel vector, hybrid, or prompt-expanded retrieval paths without benchmarks showing a real advantage.
- **Do not solve weak behavior by adding prompt mass first**. Prefer better data contracts, deterministic preprocessing, smaller evidence bundles, clearer tests, or simpler control flow. Increase prompt length only when a specific failure shows missing instructions, and keep the added instruction narrow.
- **Treat docs, skills, CLI, MCP, tests, and config as one interface surface**. Any command or data contract change must update all of them in the same change; stale skills are bugs because agents execute them.
- **Prefer structured data over duplicate display fields**. Keep canonical machine-readable fields such as `meta["l3"]`; avoid parallel summary strings that can drift.
- **Prefer explicit rebuild/migration over hidden runtime repair**. If an index or generated artifact is obsolete, make the user run `autor index --rebuild` or a migration command instead of silently maintaining old schemas forever.
- **Budget evidence, not context**. Retrieval should emit bounded bundles with trace/verify artifacts. Do not expand context windows, collect more snippets, or add broader searches unless coverage or answerability checks show a gap.
- **Tests should protect removals as well as additions**. When cleaning historical APIs, assert that old commands/options/modules are absent and that the canonical command still works.

Abstract lessons from this project:
- The most reliable retrieval surface was achieved by removing RAG/vector branches and consolidating on deterministic node FTS5 plus auditable bundles.
- Agent-facing documentation is executable infrastructure; if it says to call an old command, the old command still effectively exists.
- Compatibility debt compounds across CLI, MCP, config, skills, docs, and tests. Removing one old API usually requires touching all six.
- A smaller schema with one source of truth is easier to audit than a richer schema with mirrored convenience fields.
- Benchmark-free “flexibility” often becomes ambiguity. Keep extension points narrow until a concrete workflow proves they are needed.

## Code Style

- **Docstrings**: Library modules (`index.py`, `loader.py`, etc.) public API functions use Google-style docstrings (with Args / Returns / Raises). CLI handler functions (`cmd_*` in `cli.py`) have no docstrings.
- **User-facing text**: CLI output, help text, and error messages are in Chinese.
- **Code comments**: English, added only when logic is not self-evident.
