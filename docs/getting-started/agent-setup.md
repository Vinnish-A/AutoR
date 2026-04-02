# Agent Setup

AutoR can be used in two different ways:

1. Open this repository directly with your coding agent.
2. Register AutoR skills or tools so they are available from another project.

The right setup depends on which agent you use and whether it supports native skills or plugins.

## Start Here

| If you want to... | Recommended path |
|-------------------|------------------|
| Try AutoR, inspect the codebase, or contribute | Open this repository directly |
| Use AutoR from any project in Claude Code | Install the Claude Code plugin |
| Reuse AutoR skills in Codex / OpenClaw | Clone the repo once, then symlink the skills into `~/.agents/skills/` |

## Open This Repository Directly

This is the simplest and most complete experience. You get the bundled instructions and local skills exactly as maintained in this repo.

```bash
git clone https://github.com/Vinnish-A/AutoR.git
cd AutoR
pip install -e ".[full]"
autor setup
```

Then start your agent in the repository root:

| Agent | What happens in this repo |
|-------|----------------------------|
| Claude Code | Reads `CLAUDE.md` and loads `.claude/skills/` |
| Codex / OpenClaw | Reads `AGENTS.md` and discovers `.agents/skills/` |
| Cline | Reads `.clinerules` and can use `.claude/skills/` |
| Cursor | Reads `.cursorrules` |
| Windsurf | Reads `.windsurfrules` |
| GitHub Copilot | Reads `.github/copilot-instructions.md` |

This mode is best when you want the full project context, not just the AutoR skills.

## Claude Code Plugin

Claude Code has the cleanest cross-project install path because AutoR ships as a plugin and marketplace entry.

### Install into any project

Run these commands inside Claude Code as slash-commands, not in your system shell:

```text
/plugin marketplace add Vinnish-A/AutoR
/plugin install autor@autor-marketplace
```

After installation, start a new Claude Code session in your target project. AutoR skills will be available with the `/autor:*` namespace, for example:

```text
/autor:search
/autor:show
/autor:workspace
```

### What the plugin sets up

- Installs the `autor` Python package on first session
- Creates `~/.autor/config.yaml`
- Creates `~/.autor/data/` and related workspace directories

This is the recommended way to make AutoR available outside this repository.

## Codex / OpenClaw Skill Registration

Codex-style agents can use AutoR outside this repository through native skill discovery.

### One-time setup

Clone AutoR somewhere stable:

```bash
git clone https://github.com/Vinnish-A/AutoR.git ~/.codex/autor
cd ~/.codex/autor
pip install -e ".[full]"
autor setup
```

Create a global skills symlink:

```bash
mkdir -p ~/.agents/skills
ln -s ~/.codex/autor/.claude/skills ~/.agents/skills/autor
```

Make config discovery explicit for cross-project use:

```bash
# Option A: keep AutoR data rooted in the cloned repo
export AUTOR_CONFIG="$HOME/.codex/autor/config.yaml"

# Option B: move/copy the config into the global fallback location
mkdir -p ~/.autor
cp ~/.codex/autor/config.yaml ~/.autor/config.yaml
```

Without one of those two options, running `autor` from another project may fall back to defaults rooted in that current project and create `data/` plus `workspace/` there.

Restart Codex or OpenClaw after creating the symlink.

### Windows

Clone the repo somewhere stable first, for example:

```powershell
git clone https://github.com/Vinnish-A/AutoR.git "$env:USERPROFILE\.codex\autor"
cd "$env:USERPROFILE\.codex\autor"
pip install -e ".[full]"
autor setup
```

Then use a junction instead of a symlink:

```powershell
$repoRoot = "$env:USERPROFILE\.codex\autor"

New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills"
cmd /c mklink /J "$env:USERPROFILE\.agents\skills\autor" "$repoRoot\.claude\skills"
```

For cross-project use on Windows, either set `AUTOR_CONFIG` to `"$repoRoot\config.yaml"` or copy that config to `$env:USERPROFILE\.autor\config.yaml`.

### What this gives you

- Global access to the AutoR skill library
- Native discovery through `~/.agents/skills/`
- A setup path similar to other Codex skill packs

### Important limitation

This registers the skills, not the full repository instructions. If you want the agent to also read AutoR's bundled project guidance, open this repository directly instead of only linking the skills.

## Which Path Should I Choose?

| Situation | Best choice |
|-----------|-------------|
| You are evaluating AutoR itself | Open this repository directly |
| You want AutoR in Claude Code across projects | Claude Code plugin |
| You want AutoR skills in Codex / OpenClaw across projects | Global skill symlink |

## Verify the Setup

Use one of these checks after installation:

- In this repository: ask your agent to search or show a paper and confirm it can see AutoR instructions or skills.
- In Claude Code plugin mode: verify `/autor:search` appears.
- In Codex / OpenClaw: restart the agent and ask it to use the `search` or `show` skill.

## Related Guides

- [Installation](installation.md)
- [Configuration](configuration.md)
- [Docs Home](../index.md)
