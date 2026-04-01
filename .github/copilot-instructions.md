# autor — GitHub Copilot Instructions

This project is an AI-powered research terminal. Full project instructions are in `AGENTS.md` at the repository root. **Read `AGENTS.md` before proceeding with any task.**

## Quick Reference

- CLI entry point: `autor --help`
- Python package: `autor/`
- Paper data: `data/papers/<Author-Year-Title>/` (meta.json + paper.md)
- User output: always write to `workspace/`, never to project root or `autor/`
- Skills (reusable workflows): canonical tree `.github/skills/*/SKILL.md`, mirrored to `.agents/skills/` and `.claude/skills/` for other agents
- Tests: `python -m pytest tests/ -v`
- Code style: Google-style docstrings for library modules, Chinese for CLI output, English for code comments
- Config: `config.yaml` (git-tracked), `config.local.yaml` (secrets, not tracked)
