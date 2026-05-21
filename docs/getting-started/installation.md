# Installation

## Requirements

- Python 3.10+
- Git

## Install from Source

```bash
git clone https://github.com/Vinnish-A/AutoR.git
cd AutoR

# Core only (search, export, audit)
pip install -e .

# Full installation (import/office/pdf extras)
pip install -e ".[full]"
```

## Optional Dependencies

| Extra | What it adds |
|-------|-------------|
| `import` | Endnote / Zotero import |
| `full` | All of the above |
| `dev` | Development tools (pytest, ruff, mypy) |

## Setup Wizard

Run the interactive setup wizard to configure API keys and directories:

```bash
autor setup
```

Or check what's already configured:

```bash
autor setup check
```

## Agent Setup

If you want to know which path to use for Claude Code, Codex, OpenClaw, Cursor, or other agents, see:

- [Agent Setup](agent-setup.md)

That guide separates:

- opening this repository directly
- registering AutoR for use from another project
- choosing between native skills and plugins

## Search Index

AutoR no longer installs embedding or FAISS dependencies. Run `autor index` to
build the node-level SQLite FTS5 evidence index, then use `autor search` or
`autor research`.
