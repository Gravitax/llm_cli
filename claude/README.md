# Claude Code — Token Optimization Setup

Activates the shared optimization layer (see repository root README) for Claude Code,
plus the Claude-only features: RTK output compression and PostToolUse cache hooks.

## Setup

```bash
source claude_env.sh
```

Runs automatically on first activation:
- checks Node.js >= 20 and installs Claude Code if missing
- syncs `common/` + `claude/scripts/` to `~/.claude/scripts/`
- writes the compact global instructions to `~/.claude/CLAUDE.md`
- installs RTK and its PreToolUse bash-compression hook
- registers PostToolUse hooks (cache refresh on git commands and new files)
- installs a persistent `claude()` wrapper in `.zshrc` / `.bashrc`

After that, run `claude` from any project directory — the wrapper regenerates the
project symbol index when stale, then launches Claude Code.

## Claude-only optimizations

### RTK — CLI output compression (~70-80% savings on bash output)

A PreToolUse hook rewrites bash tool calls to RTK equivalents before execution:
the model only ever sees the compressed result (`git status/diff/log`, `ls`, `cat`,
`grep`, test runners, Docker, kubectl).

```bash
bash ~/.claude/scripts/setup_rtk.sh      # install / repair
bash ~/.claude/scripts/setup_rtk.sh -u   # remove hook (keeps binary)
rtk gain                                 # savings stats after a session
```

### PostToolUse cache hooks

Registered in `~/.claude/settings.json`:
- `cache_refresh_on_git.sh` — refreshes the index after structural git commands
- `cache_refresh_on_write.sh` — refreshes the index when Claude creates a file

## Files

| File | Description |
|---|---|
| `claude_env.sh` | Orchestrator — profile export, prerequisites, common setup, wrapper |
| `scripts/setup_prerequisites.sh` | Node.js check, npm PATH, Claude Code install, telemetry off |
| `scripts/setup_rtk.sh` | RTK binary install + PreToolUse hook registration |
| `scripts/tool_hooks.sh` | Pre-launch RTK repair, sourced by `common/lib_cache.sh` |
| `scripts/cache_refresh_on_git.sh` | PostToolUse Bash hook |
| `scripts/cache_refresh_on_write.sh` | PostToolUse Write hook |

Shared scripts (index generation, instructions, git hooks, MCP setup, diagnostics)
live in `../common/` — see the root README.
