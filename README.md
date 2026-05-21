<div align="center">

<!-- TODO: Replace after logo is available -->
<!-- <img src="docs/assets/logo.png" width="200" alt="autor Logo"> -->

# AutoR

**AutoR — Author without Human**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP Tools](https://img.shields.io/badge/MCP_Tools-40-green.svg)](autor/mcp_server.py)

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

- `start.sh`: starts local MinerU and the Records-backed AutoDownload service on the Windows side (default repo path `F:\Records`, port `8001`)
- `stop.sh`: stops MinerU and the Records-backed AutoDownload service
- `run-mcp.sh`: launches `autor-mcp` in the foreground

Note: `autor-mcp` uses `stdio` transport and is not meant to stay alive in the background like an HTTP service. In practice, it works best when your MCP client invokes `scripts/run-mcp.sh` directly.

WSL will try to detect Windows PowerShell automatically. If your environment is unusual, set `AUTOR_WINDOWS_POWERSHELL` explicitly. To change the Windows-side Records repo path, set `AUTOR_AUTODOWNLOAD_WIN_DIR` (default `F:\Records`, seen from WSL as `/mnt/f/Records`).

## Core Features

|  | Feature | Description |
|--|---------|-------------|
| **PDF Parsing** | Deep structural extraction | [MinerU](https://github.com/opendatalab/MinerU) → Markdown with equations, tables, and structure preserved. Image attachments are discarded by default to keep the knowledge base text-first |
| **Retrieval** | Auditable evidence search | Node-level SQLite FTS5 over metadata and `paper.md`; `autor research` writes bundle/trace/verify artifacts for provenance |
| **Literature Exploration** | Multi-dimensional discovery | OpenAlex 9-dimensional filtering (journal, concept, author, institution, keyword, source type, year, citation count, document type) → FTS5 search |
| **Citation Graph** | References and influence | Forward/backward citations and shared-reference analysis |
| **Layered Reading** | Load on demand | L1 metadata → L2 abstract → L3 paper-level conclusion card generated during normal ingest → L4 full text |
| **Multi-source Import** | Bring your existing library | Endnote XML/RIS, Zotero (API + SQLite, including collection → workspace mapping), PDF, Markdown — with more sources on the way |
| **Workspace** | Organize by project | Manage subsets of papers, search within scope, inspect corpus status, export evidence ledgers, and generate planning-package skeletons |
| **Federated Search** | Search beyond one silo | `autor fsearch` queries the main library, `explore` datasets, and arXiv together |
| **Office Documents** | Inspect and ingest DOCX/PPTX/XLSX | `autor document inspect` checks layout and content; Office files can also flow through the document inbox |
| **Research Insights** | Learn from your own workflow | `autor insights` surfaces hot queries, frequently read papers, reading trends, and adjacent unread papers |
| **Academic Writing** | AI-assisted drafting | Literature reviews, paper sections, reviewer-driven revision, citation verification, reviewer responses, and research-gap analysis — every citation remains traceable to your own library |
| **MCP Server** | Tool interface | Works with Claude Desktop, Cursor, and other MCP clients |

## More Than Paper Management

autor turns PDFs into clean Markdown with accurate LaTeX equations and structured text. MinerU image attachments are intentionally discarded; generated review figures should use `autor plot` / `autor/plot.py` explicitly. That means your coding agent does more than just “read” papers:

- **Reproduce methods** — read an algorithm description, implement it, and run it immediately
- **Verify claims** — recompute results independently, cross-check the paper, and analyze only explicitly provided or generated images
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

The **MCP server** (`autor-mcp`) works with any MCP-compatible client. Skills follow the open [AgentSkills.io](https://agentskills.io) standard — `.agents/skills/` and `.claude/skills/` mirror the canonical `.github/skills/` tree for easier cross-agent discovery.

Before asking an external system to fetch or download a paper, call the MCP `identify` tool to check exact DOI / PMID / title duplicates in the library and an optional workspace.

For a quick overview of built-in skills, see `.github/skills/`, `CLAUDE.md`, or `AGENTS.md`. If you are new to the project, start with `autor-overview`.

**Migrating from existing tools?** You can import directly from Endnote (XML/RIS) and Zotero (Web API or local SQLite) — PDFs, metadata, and citation relationships all come along. More import sources are under active development.

## Workflow

```
PDF → MinerU → Structured Markdown (LaTeX and tables preserved; image artifacts discarded)
                    ↓
          Metadata extraction (regex + LLM cross-check)
          API enrichment (Crossref / Semantic Scholar / OpenAlex / PubMed)
                    ↓
          DOI / PMID dedup → data/papers/<Author-Year-Title>/
                    ↓
                    ↓
   Node-level FTS5 evidence index
   (paper_nodes + paper_node_fts; no vectors)
                    ↓
      Your agent (CodeX / Cursor / CLI / MCP / ...)
```

### Batch ingest straight into a workspace

You can send a new ingest batch directly into a project workspace during the same pipeline run:

```bash
autor pipeline ingest --workspace my_research_project
```

The workspace is created automatically if needed. Only papers that are newly written to `data/papers/` in that run are added, so pending items without a DOI and duplicates stopped by deduplication are excluded automatically.

For existing workspace corpora, the same `--workspace/-w` flag now scopes non-inbox paper/global steps instead of scanning the whole library:

```bash
autor pipeline enrich -w my_research_project
autor enrich-l3 --workspace my_research_project --only-missing
```

Useful pre-writing workspace checks:

```bash
autor ws status my_research_project --papers
autor ws export-evidence my_research_project -o workspace/my_research_project/evidence.json
autor ws screen my_research_project --criteria "breast cancer immunotherapy resistance" --target 150 -o workspace/my_research_project/screening.json
autor ws plan-package my_research_project --title "Breast cancer immunotherapy resistance"
```

## Configuration

Main config: `config.yaml` (tracked in git). Sensitive data: `config.local.yaml` (not tracked).

| Key | Purpose | How to get it |
|-----|---------|---------------|
| `DEEPSEEK_API_KEY` | LLM — metadata extraction, content enrichment, academic discussion | [DeepSeek](https://platform.deepseek.com/) (default) or any OpenAI-compatible API |
| `MINERU_API_KEYS` | PDF → structured Markdown cloud tokens, comma-separated for parallel accounts; in `hybrid` mode each token runs alongside the local MinerU source | Free from [mineru.net](https://mineru.net/apiManage/token), or [self-host](https://github.com/opendatalab/MinerU) |
| `NCBI_API_KEY` | PubMed / E-utilities PMID lookup with higher rate limits | [NCBI account settings](https://www.ncbi.nlm.nih.gov/account/settings/) |

> **Both are optional.** Without an LLM key, autor falls back to regex-only extraction. Without MinerU tokens, place `.md` files directly into `data/inbox/` or run a local MinerU endpoint. In `hybrid` mode, a running local MinerU endpoint and all configured MinerU tokens process batch PDFs together. MinerU tokens belong in `config.local.yaml` or `MINERU_API_KEYS`, not `config.yaml`.

Normal ingest now generates L3 paper-level conclusion cards and updates the node-level FTS5 evidence index, so papers are immediately useful for layered reading, search, and auditable bundle generation. L3 first uses explicit conclusion/summary sections when present; otherwise it synthesizes a constrained takeaway from abstract, results, discussion, and table/caption text present in Markdown. AutoR no longer builds semantic vectors or FAISS storage.

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
autor research QUERY       Generate evidence bundle + trace/verify
autor search-author NAME   Search by author
autor top-cited            Rank by citation count
autor show PAPER           View paper content (L1-L4)
autor refs PAPER           View references
autor citing PAPER         View citing papers
autor shared-refs A B      Shared-reference analysis
autor fsearch QUERY        Federated search across library / explore / arXiv
autor pipeline PRESET      Run the ingest pipeline
autor index                Build the node-level FTS5 evidence index
autor enrich-toc           Extract table of contents
autor enrich-l3            Generate L3 paper-level conclusion card
autor backfill-abstract    Fill in missing abstracts
autor refetch              Refresh citation counts
autor explore ...          OpenAlex exploration workflow
autor export ...           Export BibTeX / RIS / Markdown / DOCX
autor ws ...               Workspace management
autor ws status            Inspect workspace corpus completeness
autor ws export-evidence   Export workspace evidence JSON
autor ws screen            Score/apply scope screening
autor ws plan-package      Create references.bib / reference-map.json planning skeleton
autor ws citation-coverage Check manuscript citations against reference-map.json
autor ws figure-status     Check planned figure exports before final delivery
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
  cli.py             # CLI entry point
  mcp_server.py      # MCP server tools
  ingest/            # PDF parsing + metadata pipeline
  index.py           # Node-level FTS5 search + evidence bundles
  loader.py          # L1-L4 layered loading
  explore.py         # OpenAlex literature exploration
  workspace.py       # Workspace management
  export.py          # BibTeX / RIS / Markdown / DOCX export
  audit.py           # Data quality auditing
  citation_check.py  # Citation verification
  document.py        # Office document inspection
.github/skills/      # Canonical agent skills
.claude/skills/      # Mirror for Claude / Cline
.agents/skills/      # Mirror for Codex / OpenClaw
data/papers/         # Your paper library (not tracked in git)
data/inbox/          # Drop PDFs here to ingest them
```
