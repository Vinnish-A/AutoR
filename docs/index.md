# AutoR

**AutoR** — an AI-native research terminal for coding agents.

AutoR is a research terminal built around AI coding agents. You interact with your literature knowledge base through natural language — searching, reading, analyzing, and writing — all from the command line.

## Features

- **PDF Ingestion**: Convert PDFs to structured Markdown via MinerU (cloud or local)
- **Hybrid Search**: FTS5 keyword search + FAISS semantic search + RRF fusion
- **Topic Modeling**: BERTopic clustering with interactive HTML visualizations
- **Citation Graph**: View references, citing papers, and shared references
- **BibTeX Export**: Filtered export with standard citation formats
- **Literature Exploration**: Multi-dimensional OpenAlex queries with isolated data
- **Workspace Management**: Organize papers into subsets for focused work
- **26 Agent Skills**: Literature review, paper writing, gap analysis, and more

## Quick Start

```bash
pip install -e ".[full]"
autor setup
```

See [Installation](getting-started/installation.md) for detailed instructions.
See [Agent Setup](getting-started/agent-setup.md) for repo-open vs plugin setup paths.

## Two Usage Modes

| Mode | Interface | Best for |
|------|-----------|----------|
| **Agent** | Claude Code CLI | Full research workflow via natural language |
| **CLI** | Terminal | Scripting and automation |
