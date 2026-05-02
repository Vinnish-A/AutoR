# autor — Coding Agent Instructions

> This file provides project instructions for any AI coding agent (Codex, OpenClaw, etc.).
> Claude Code users: see `CLAUDE.md` for the Claude-specific version of these instructions.

## Project Overview

autor is a research terminal built around AI coding agents. Users interact with a local academic knowledge base through natural language, performing literature search, reading, discussion, analysis, and writing — all via CLI tools. The `autor` Python package provides the infrastructure (PDF parsing, hybrid retrieval, topic modeling, citation graphs, etc.), and the coding agent is responsible for understanding user intent, invoking the right CLI commands, integrating results, and engaging in academic discussion.

### Interaction Model

Users interact with their knowledge base through you (the coding agent) using natural language. Your role is to understand user intent, invoke the appropriate CLI commands, synthesize results, and participate in academic discussions.

MinerU-parsed Markdown preserves high-quality formulas (LaTeX) and image attachments (`images/` directory), enabling you to:
- **Analyze figures**: View experimental charts, flowcharts, and diagrams from papers to help interpret results
- **Derive formulas**: Work with mathematical formulas from papers — derive, verify, and extend them
- **Write verification code**: Implement analysis code based on paper methods, run tests, and cross-validate paper conclusions with computed results
- **Multi-modal verification**: Combine text, images, and formulas to assess paper reliability

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
| `index.py` | FTS5 full-text search + papers_registry + citations graph |
| `vectors.py` | Qwen3 semantic vectors + FAISS incremental indexing |
| `topics.py` | BERTopic topic modeling + 6 HTML visualizations |
| `loader.py` | L1-L4 layered loading + enrich_toc + enrich_l3 |
| `explore.py` | Multi-dimensional literature exploration (OpenAlex multi-filter + FTS5 + semantic + unified search + topics, isolated in `data/explore/`) |
| `workspace.py` | Workspace paper subset management (reuses search/export) |
| `export.py` | BibTeX export |
| `audit.py` | Data quality audit + repair |
| `sources/` | Data source adapters (local / endnote / zotero) |
| `cli.py` | Full CLI entry point |
| `mcp_server.py` | MCP server (32 tools) |
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
             index.py → data/index.db (SQLite FTS5)
             vectors.py → data/index.db (paper_vectors table)
             topics.py → data/topic_model/ (BERTopic, reuses paper_vectors)
                   ↓
             cli.py → skills → coding agent

explore.py — Multi-dimensional literature exploration (independent data flow, isolated from main library)
  OpenAlex API (multi-filter: ISSN/concept/author/institution/keyword/source-type etc.)
    → data/explore/<name>/papers.jsonl (supports incremental update, DOI-based dedup)
                 → explore.db (paper_vectors + explore_fts FTS5 full-text index)
                 → faiss.index (FAISS semantic search)
  Search: semantic / keyword(FTS5) / unified(RRF) — three modes
  Topic modeling/visualization/queries reuse topics.py (via papers_map parameter)
                 → topic_model/ (BERTopic, unified format) + viz/ (HTML)

workspace.py — Workspace paper subset management (thin layer, reuses search/export)
  workspace/<name>/papers.json → references papers in data/papers/ (UUID index)
  Search/export via paper_ids parameter injected into search()/vsearch()/unified_search()/export_bibtex()

import-endnote / import-zotero — External reference manager import (full pipeline)
  sources/endnote.py | sources/zotero.py → parse metadata + match PDFs
    → pipeline.import_external() → DOI dedup + ingest + PDF copy + embed + index
    → pipeline.batch_convert_pdfs(enrich=True)
       → batch PDF→MD (cloud batch API, per-token batch size: config ingest.mineru_cloud_batch_size)
       → abstract backfill + toc + l3 extraction + embed + index
```

### Layered Loading Design (L1-L4)

| Level | Content | Source |
|-------|---------|--------|
| L1 | title, authors, year, journal, doi, pmid, volume, issue, pages, publisher, issn | JSON file |
| L2 | abstract | JSON field |
| L3 | conclusion section | JSON field (requires running enrich-l3 first) |
| L4 | full markdown | Read .md directly |

### data/papers/ Directory Structure

```
data/papers/
└── <Author-Year-Title>/
    ├── meta.json    # L1+L2+L3 metadata (includes "id": "<uuid>")
    ├── paper.md     # L4 source (MinerU output)
    ├── images/      # MinerU-extracted images (referenced in md)
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
    ├── images/            # MinerU-extracted images (if any)
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
├── explore.db          # SQLite (paper_vectors table + explore_fts FTS5 full-text index)
├── faiss.index         # FAISS IndexFlatIP (cosine similarity)
├── faiss_ids.json      # paper_id list corresponding to FAISS index
└── topic_model/
    ├── bertopic_model.pkl   # BERTopic model (unified format, same as main library)
    ├── autor_meta.pkl  # Additional metadata (paper_ids/metas/topics/embeddings/docs)
    ├── info.json            # Statistics (n_topics/n_outliers/n_papers)
    └── viz/                 # 6 HTML visualizations
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

## Code Style

- **Docstrings**: Library modules (`index.py`, `loader.py`, `vectors.py`, etc.) public API functions use Google-style docstrings (with Args / Returns / Raises). CLI handler functions (`cmd_*` in `cli.py`) have no docstrings.
- **User-facing text**: CLI output, help text, and error messages are in Chinese.
- **Code comments**: English, added only when logic is not self-evident.

## Agent Skills

Skills are authored in `.github/skills/`, which preserves the existing Copilot layout. For cross-agent discovery, expose the same skill tree through `.agents/skills/` (Codex / OpenClaw) and `.claude/skills/` (Claude / Cline). All skills follow the [Agent Skills](https://agentskills.io) open standard, with one folder per skill and a `SKILL.md` file as the entry point.

**Available skills (36):**

Project overview:
- `autor-overview` — Project overview (how to use the software / what skills exist / what other features are available / what to do next)

Literature acquisition:
- `autodownload` — Use the Records-backed AutoDownload service for PubMed retrieval, PMID resolution, and PDF download in support of autor workspaces

Knowledge base management:
- `search` — Literature search (keyword / semantic / author / hybrid retrieval / top-cited ranking)
- `show` — View paper content (L1-L4 layered)
- `enrich` — Enrich paper content (TOC / conclusion / abstract / citation count)
- `ingest` — Ingest papers + rebuild indexes (pipeline presets)
- `topics` — Topic exploration (BERTopic clustering + merge + visualization)
- `explore` — Multi-dimensional literature exploration (OpenAlex multi-filter + FTS5/semantic/unified search + BERTopic)
- `graph` — Citation graph queries
- `citations` — Citation count queries and refresh
- `index` — Rebuild FTS5 / FAISS indexes
- `workspace` — Workspace management (create / add / search / export)
- `export` — BibTeX export
- `import` — Endnote / Zotero import
- `rename` — Paper file renaming
- `audit` — Paper audit (rule checks + LLM deep diagnosis + repair)
- `document` — Generate and inspect Office documents (DOCX, PPTX, XLSX)
- `draw` — Generate diagrams and vector graphics for workspace outputs
- `insights` — Analyze research behavior data and discover overlooked papers
- `translate` — Translate paper markdown to a target language
- `trials` — Clinical trial retrieval with workspace-attached outputs

Academic writing:
- `plan` — Pre-writing review planning in a Springer Nature Reviews style (outline revision, paper classification, fixed task/table design)
- `write` — Formal review drafting after /plan using workspace-grounded evidence, humanized Springer Nature Reviews-style prose, and Markdown + CSL citations
- `literature-review` — Literature review writing (workspace-based, topic grouping + critical narrative)
- `paper-writing` — Paper section writing (Introduction / Related Work / Method / Results / Discussion)
- `update` — Reviewer-driven manuscript revision with minimum-necessary, traceable edits and evidence-gated external supplementation
- `citation-check` — Citation verification (anti-AI hallucination, local library cross-check)
- `polish` — Writing polish (remove AI/system artifacts, normalize terminology, style adaptation + EN/ZH)
- `writing-polish` — Prose polishing focused on removing AI-generated patterns
- `review-response` — Review response (point-by-point analysis + evidence search + rebuttal)
- `research-gap` — Research gap identification (multi-dimensional analysis + open question discovery)
- `check` — Final-draft structural and quality review before submission

System maintenance:
- `setup` — Environment detection and setup wizard
- `metrics` — LLM token usage and call statistics

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
- Embedding model (Qwen3-Embedding-0.6B, ~1.2GB) auto-downloads on first embed/vsearch. International users: set `embed.source` to `huggingface` in `config.yaml`

## Key Conventions

- **Workspace isolation**: All user output (writing, notes, drafts) goes in the `workspace/` directory. When creating new files (literature reviews, research notes), default to `workspace/`, not the project root or `autor/` source directory
- **Do not modify `metadata/_extract.py` regex logic** — extend only through the extractor abstraction layer
- `data/`, `workspace/` are not tracked in git (.gitignore configured)
- Python 3.10+, runtime environment: conda `autor`
- Tests: `python -m pytest tests/ -v`

## Multi-Agent Compatibility

This project supports multiple AI coding agents:

| Agent | Instructions File | Skills |
|-------|-------------------|--------|
| Claude Code | `CLAUDE.md` | `.claude/skills/` → `.github/skills/` |
| Codex (OpenAI) | `AGENTS.md` (this file) | `.agents/skills/` → `.github/skills/` |
| OpenClaw | `AGENTS.md` (this file) | `.agents/skills/` → `.github/skills/` |
| Cursor | `.cursorrules` (wrapper → read this file) | — |
| Windsurf | `.windsurfrules` (wrapper → read this file) | — |
| GitHub Copilot | `.github/copilot-instructions.md` (wrapper → read this file) | `.github/skills/` |
| Cline | `.clinerules` (wrapper → read this file) | `.claude/skills/` → `.github/skills/` |

Skills use the [AgentSkills.io](https://agentskills.io) open standard (`SKILL.md` format). The canonical location is `.github/skills/`; `.agents/skills/` and `.claude/skills/` should point to the same tree for cross-agent discovery.
