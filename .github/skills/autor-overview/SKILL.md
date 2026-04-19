---
name: autor-overview
description: Understand the autor codebase at a high level. Use when the user asks how to use autor, what built-in skills it has, what features it supports, which workflow to choose, or wants a project overview before using other skills.
---

# autor Overview

When the user has not yet given a concrete task and is asking things like "How do I use this software?", "What skills are available?", "What other features does it have?", or "Where should I start?", use this skill first to build a high-level view, then switch to a more specific skill if needed.

## The three things you need to explain

### 1. How to use autor

Start with the three main entry points:

- **Agent mode**: launch Claude Code, Copilot, Codex, Cline, or another agent in the project directory, then use natural language for search, reading, writing, and analysis
- **CLI mode**: run `autor --help` directly; ideal for scripting and quick lookups
- **MCP mode**: run `autor-mcp` for Claude Desktop, Cursor, and other MCP clients

When the user asks "How do I get started?", give them the shortest path:

```bash
git clone https://github.com/ZimoLiao/autor.git && cd autor
pip install -e ".[full]"
cp config.local.example.yaml config.local.yaml
autor setup check --lang en
```

Then add the key notes:

- an LLM key is optional; without it, metadata extraction falls back to regex only
- a MinerU key is optional; without it, `.md` files can still be processed directly, but cloud PDF -> Markdown parsing is unavailable
- common entry commands include `autor search`, `autor show`, `autor pipeline`, `autor ws`, and `autor-mcp`

### 2. Which skills autor includes

Summarize them by group. Start with the overview, then go deeper only if the user asks.

#### Project overview
- `autor-overview`: explains how to use the software, outlines the available skills, clarifies feature boundaries, and recommends where to start

#### External acquisition / Records service integration
- `autodownload`: explains how autor works with the Records-backed AutoDownload service, where the REST boundary is, which endpoints to use, and how to build or expand a workspace through external acquisition

#### Knowledge-base management
- `search`: search the local literature library
- `show`: view paper content layer by layer
- `enrich`: extract TOC / conclusions / abstracts / citation counts
- `ingest`: batch-ingest papers, theses, and general documents
- `index`: rebuild FTS5 / FAISS indexes
- `explore`: fetch independent exploration datasets from OpenAlex
- `topics`: BERTopic clustering and visualization
- `graph`: citation-graph and shared-reference analysis
- `citations`: top-cited rankings and citation-count refresh
- `export`: export BibTeX
- `import`: import Endnote / Zotero libraries
- `rename`: normalize paper-directory naming
- `audit`: audit and repair metadata problems
- `trials`: retrieve and organize clinical-trial information

#### Academic writing
- `plan`: prepare a review in a Springer Nature Reviews style through outline revision, paper classification, and fixed task / table design
- `write`: pick up directly from `/plan` and draft the formal review text using workspace-grounded evidence, Markdown + CSL citations, and more natural prose
- `literature-review`: write a literature review
- `paper-writing`: draft individual paper sections
- `update`: revise a manuscript under reviewer or editor comments with minimum-necessary, traceable edits and evidence-gated outside supplementation
- `citation-check`: verify whether citations are real and accurate
- `polish`: polish academic text, remove AI/workflow artifacts, normalize terminology, and adapt the style
- `review-response`: draft reviewer responses
- `research-gap`: identify research gaps

#### System maintenance
- `setup`: initialize and diagnose the environment
- `metrics`: inspect token usage, runtime, and call statistics

Additional note:

- `workspace` is a core autor capability, but it is not currently implemented as a standalone skill file; use `autor ws ...` or the related MCP tools when needed
- If the task involves external literature acquisition and PDF downloads, switch explicitly to `autodownload` instead of treating it as ordinary local-library search
- For Records-service workflows, prefer REST endpoints over CLI. Treat `/download`, `/search`, and `/fetch` as long-running acquisition phases rather than quick metadata calls

### 3. Other core features

Beyond the skills, explain the underlying system capabilities autor provides:

- **PDF -> Markdown**: MinerU preserves figures, LaTeX formulas, and image attachments
- **Layered loading**: L1 metadata, L2 abstract, L3 conclusion, L4 full text
- **Hybrid retrieval**: FTS5 keywords + Qwen3 embeddings + FAISS semantic search + RRF fusion
- **Topic modeling**: BERTopic clustering with HTML visualizations
- **Explore's isolated data flow**: build external exploration libraries from OpenAlex without affecting the main library
- **Citation graph**: references, citations, and shared-citation analysis
- **Multi-source import**: Endnote, Zotero, PDF, Markdown
- **Workspace isolation**: writing, notes, and drafts are all written under `workspace/`
- **Multi-agent compatibility**: Claude Code, Copilot, Codex, OpenClaw, Cline, Cursor, Windsurf, and MCP clients
- **Records service integration**: the Records-backed AutoDownload service can be used as an external REST service for PubMed retrieval and PDF downloads
- **Multiple document types**: regular papers, theses, technical reports, lecture notes, and other document types

## Recommended answer structure

When the user asks a broad question, organize the answer in this order by default:

1. Explain in one sentence what autor is
2. Give the three usage modes
3. List the skills by group
4. Add the features that differentiate autor from ordinary paper managers
5. Recommend the next most relevant skill or CLI command if the user wants to continue

## When to switch to another skill

- The user wants to install dependencies or troubleshoot the environment: switch to `setup`
- The user wants to find papers: switch to `search`
- The user wants to read a paper: switch to `show`
- The user wants to ingest new literature: switch to `ingest`
- The user wants topic analysis: switch to `topics` or `explore`
- The user wants to expand an existing workspace through external acquisition: switch to `autodownload`
- The user wants to build a new workspace from a topic / outline and needs external literature acquisition: switch to `autodownload`
- The user wants to revise structure, classify papers, and design tables before writing a review: switch to `plan`
- The user wants to formally draft the review text following `/plan`: switch to `write`
- The user wants a more open-ended review or direct section drafting: switch to `literature-review` or `paper-writing`
- The user wants reviewer-driven manuscript revision with minimum necessary changes: switch to `update`
- The user wants to verify citations: switch to `citation-check`

## Boundary facts

- autor is a **research terminal / knowledge infrastructure**, not just a PDF manager
- Skills are agent-oriented workflow wrappers; they do not exhaust the system's underlying capabilities
- User-facing outputs should be written to `workspace/` by default, not the project root or the `autor/` package directory
- If the user's question is already specific enough, move quickly into the corresponding specialized skill instead of staying at the overview layer
