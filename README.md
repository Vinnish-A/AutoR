<div align="center">

<!-- TODO: Replace after logo is available -->
<!-- <img src="docs/assets/logo.png" width="200" alt="autor Logo"> -->

# AutoR

**AutoR — Author without Human**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP Tools](https://img.shields.io/badge/MCP_Tools-31-green.svg)](autor/mcp_server.py)

</div>

---

Auto Review. Author without human. One terminal, one agent, one end-to-end research workflow.

<!-- TODO: Add demo GIF -->
<!-- <div align="center">
  <img src="docs/assets/demo.gif" width="700" alt="autor Demo">
</div> -->

## Quick Start

```bash
# 1. Install
git clone https://github.com/Vinnish-A/AutoR.git && cd AutoR
pip install -e ".[full]"

# 2. Configure
cp config.local.example.yaml config.local.yaml
# Add API keys if you need them (all are optional; see the configuration section below)

# 3. Launch
codex    # Start codex in the project directory and begin chatting
```

> You can also use the CLI directly: `autor search "your topic"` | MCP server: `autor-mcp`

If you use this repository from WSL, you can run:

```bash
./scripts/start.sh
./scripts/stop.sh
./scripts/run-mcp.sh
```

- `start.sh`: starts local MinerU and proxies to AutoDownload on the Windows side (default `F:\AutoDownload`, port `8001`)
- `stop.sh`: stops MinerU and AutoDownload
- `run-mcp.sh`: launches `autor-mcp` in the foreground

Note: `autor-mcp` uses `stdio` transport and is not meant to stay alive in the background like an HTTP service. In practice, it works best when your MCP client invokes `scripts/run-mcp.sh` directly.

WSL will try to detect Windows PowerShell automatically. If your environment is unusual, set `AUTOR_WINDOWS_POWERSHELL` explicitly. To change the Windows-side AutoDownload path, set `AUTOR_AUTODOWNLOAD_WIN_DIR`.

## Core Features

|  | Feature | Description |
|--|---------|-------------|
| **PDF Parsing** | Deep structural extraction | [MinerU](https://github.com/opendatalab/MinerU) → Markdown with figures and equations preserved. Supports journal articles, theses, technical reports, and other document types |
| **Hybrid Retrieval** | Keywords + semantics | FTS5 + chunk-aware semantic embeddings + FAISS → RRF rank fusion |
| **Topic Discovery** | Automatic clustering | BERTopic + 6 interactive HTML visualizations — works for both the main library and explore datasets |
| **Literature Exploration** | Multi-dimensional discovery | OpenAlex 9-dimensional filtering (journal, concept, author, institution, keyword, source type, year, citation count, document type) → vectorization → clustering → search |
| **Citation Graph** | References and influence | Forward/backward citations and shared-reference analysis |
| **Layered Reading** | Load on demand | L1 metadata → L2 abstract → L3 conclusion → L4 full text |
| **Multi-source Import** | Bring your existing library | Endnote XML/RIS, Zotero (API + SQLite, including collection → workspace mapping), PDF, Markdown — with more sources on the way |
| **Workspace** | Organize by project | Manage subsets of papers, search within scope, and export BibTeX / RIS / Markdown / DOCX |
| **Federated Search** | Search beyond one silo | `autor fsearch` queries the main library, `explore` datasets, and arXiv together |
| **Translation** | Read across languages | `autor translate` preserves formulas, code blocks, and images while translating Markdown papers |
| **Office Documents** | Inspect and ingest DOCX/PPTX/XLSX | `autor document inspect` checks layout and content; Office files can also flow through the document inbox |
| **Research Insights** | Learn from your own workflow | `autor insights` surfaces hot queries, frequently read papers, reading trends, and semantic neighbors |
| **Academic Writing** | AI-assisted drafting | Literature reviews, paper sections, reviewer-driven revision, citation verification, reviewer responses, and research-gap analysis — every citation remains traceable to your own library |
| **MCP Server** | 31 tools | Works with Claude Desktop, Cursor, and other MCP clients |

## More Than Paper Management

autor turns PDFs into clean Markdown with accurate LaTeX equations and complete image attachments. That means your coding agent does more than just “read” papers:

- **Reproduce methods** — read an algorithm description, implement it, and run it immediately
- **Verify claims** — extract data from figures, recompute results independently, and cross-check the paper
- **Extend derivations** — continue a paper's math, then validate edge cases numerically
- **Visualize comparisons** — plot paper results alongside your own experiments

The knowledge base is infrastructure. What the agent can do on top of it is limited mostly by your imagination.

## Works With Your Agent

autor is designed to be **agent-agnostic**. It already ships with ready-to-use integrations for multiple agents and IDEs:

| Agent / IDE | Integration | Config files |
|-------------|-------------|--------------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Full skills + instructions | `CLAUDE.md` + `.claude/skills/` |
| [Cursor](https://cursor.sh) | Instruction wrapper | `.cursorrules` |
| [Windsurf](https://codeium.com/windsurf) | Instruction wrapper | `.windsurfrules` |
| [Cline](https://github.com/cline/cline) | Instructions + skills | `.clinerules` + `.claude/skills/` |
| [GitHub Copilot](https://github.com/features/copilot) | Instruction wrapper | `.github/copilot-instructions.md` |
| [Codex](https://openai.com/codex) / OpenClaw | Full instructions + skills | `AGENTS.md` + `.agents/skills/` |

The **MCP server** (`autor-mcp`, 31 tools) works with any MCP-compatible client. Skills follow the open [AgentSkills.io](https://agentskills.io) standard — `.agents/skills/` and `.claude/skills/` mirror the canonical `.github/skills/` tree for easier cross-agent discovery.

For a quick overview of built-in skills, see `.github/skills/`, `CLAUDE.md`, or `AGENTS.md`. If you are new to the project, start with `autor-overview`.

**Migrating from existing tools?** You can import directly from Endnote (XML/RIS) and Zotero (Web API or local SQLite) — PDFs, metadata, and citation relationships all come along. More import sources are under active development.

## Workflow

```
PDF → MinerU → Structured Markdown (figures + LaTeX preserved)
                    ↓
          Metadata extraction (regex + LLM cross-check)
          API enrichment (Crossref / Semantic Scholar / OpenAlex)
                    ↓
          DOI dedup → data/papers/<Author-Year-Title>/
                    ↓
      ┌─────────────┼─────────────┐
   FTS5 index      FAISS vectors      BERTopic
   (keywords)      (semantic)        (clustering)
      └─────────────┼─────────────┘
                    ↓
      Your agent (CodeX / Cursor / CLI / MCP / ...)
```

### Batch ingest straight into a workspace

You can send a new ingest batch directly into a project workspace during the same pipeline run:

```bash
autor pipeline ingest --workspace my_research_project
```

The workspace is created automatically if needed. Only papers that are newly written to `data/papers/` in that run are added, so pending items without a DOI and duplicates stopped by deduplication are excluded automatically.

## Configuration

Main config: `config.yaml` (tracked in git). Sensitive data: `config.local.yaml` (not tracked).

| Key | Purpose | How to get it |
|-----|---------|---------------|
| `DEEPSEEK_API_KEY` | LLM — metadata extraction, content enrichment, academic discussion | [DeepSeek](https://platform.deepseek.com/) (default) or any OpenAI-compatible API |
| `MINERU_API_KEY` | PDF → structured Markdown | Free from [mineru.net](https://mineru.net/apiManage/token), or [self-host](https://github.com/opendatalab/MinerU) |

> **Both are optional.** Without an LLM key, autor falls back to regex-only extraction. Without a MinerU key, place `.md` files directly into `data/inbox/`.

The default embedding model is `Alibaba-NLP/gte-Qwen2-1.5B-instruct`. On the main library, `autor embed` now reads full `paper.md`, chunks it with overlap, and stores chunk-level evidence vectors for retrieval. The default download source is Hugging Face; if this model is mirrored in your environment, you can switch `embed.source`.

Full configuration reference → [`config.yaml`](config.yaml)

## Three Ways to Use It

| Mode | Best for | Command |
|------|----------|---------|
| **Agent** (recommended) | Full research workflow with conversational interaction | Run `claude` or your preferred agent in the project directory |
| **MCP Server** | MCP clients such as Claude Desktop or Cursor | `autor-mcp` |
| **CLI** | Scripting and quick lookups | `autor --help` |

<details>
<summary><strong>CLI command reference</strong></summary>

```
autor search QUERY         Keyword search
autor vsearch QUERY        Semantic vector search
autor usearch QUERY        Hybrid search
autor search-author NAME   Search by author
autor top-cited            Rank by citation count
autor show PAPER           View paper content (L1-L4)
autor refs PAPER           View references
autor citing PAPER         View citing papers
autor shared-refs A B      Shared-reference analysis
autor fsearch QUERY        Federated search across library / explore / arXiv
autor pipeline PRESET      Run the ingest pipeline
autor index                Build the FTS5 search index
autor embed                Generate semantic vectors
autor enrich-toc           Extract table of contents
autor enrich-l3            Extract conclusion section
autor backfill-abstract    Fill in missing abstracts
autor refetch              Refresh citation counts
autor translate PAPER      Translate markdown papers
autor explore ...          OpenAlex exploration workflow
autor topics               BERTopic topic modeling
autor export ...           Export BibTeX / RIS / Markdown / DOCX
autor ws ...               Workspace management
autor import-endnote       Import from Endnote
autor import-zotero        Import from Zotero
autor attach-pdf           Attach a PDF to an existing paper
autor citation-check FILE  Verify in-text citations
autor style ...            Manage citation styles
autor document inspect ... Inspect DOCX / PPTX / XLSX
autor audit                Audit data quality
autor repair               Repair metadata
autor rename               Standardize directory names
autor setup                Environment setup wizard
autor insights             View research behavior insights
autor metrics              View LLM usage statistics
```

</details>

## Project Structure

```
autor/          # Python package
  cli.py             # CLI entry point (35 top-level commands)
  mcp_server.py      # MCP server (31 tools)
  ingest/            # PDF parsing + metadata pipeline
  index.py           # FTS5 full-text search
  vectors.py         # Full-text chunk embeddings + FAISS retrieval
  topics.py          # BERTopic topic modeling
  loader.py          # L1-L4 layered loading
  explore.py         # OpenAlex literature exploration
  workspace.py       # Workspace management
  export.py          # BibTeX / RIS / Markdown / DOCX export
  audit.py           # Data quality auditing
  citation_check.py  # Citation verification
  document.py        # Office document inspection
  translate.py       # Paper translation

.github/skills/      # Canonical agent skills (35 total)
.claude/skills/      # Mirror for Claude / Cline
.agents/skills/      # Mirror for Codex / OpenClaw
data/papers/         # Your paper library (not tracked in git)
data/inbox/          # Drop PDFs here to ingest them
```
