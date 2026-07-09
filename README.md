# llm_cli — Token-optimization layer for Claude Code & GitHub Copilot CLI

Wraps `claude` and `copilot` with a shared optimization layer that cuts token
consumption and gives both agents a precise, pre-built view of each project.

## What it does

| Optimization | Mechanism | Claude | Copilot |
|---|---|---|---|
| Project symbol index | `path \| LOC \| symbols` cache read at session start instead of scanning files | ✓ | ✓ |
| Compact global instructions | Behavioral rules kept short — loaded every turn, every session | ✓ | ✓ |
| CLI output compression (RTK) | PreToolUse hook rewrites bash commands, ~70-80% savings on output | hook | via instructions |
| Auto cache refresh | Shell wrapper + git hooks (+ PostToolUse hooks for Claude) | ✓ | ✓ |
| Atlassian & Bitbucket MCP | Per-project `.mcp.json` — ~150 tool definitions load only where needed | ✓ | ✓ |

## Layout

```
common/    shared scripts, parameterized by tool profile (claude | copilot)
claude/    Claude Code orchestrator + Claude-only scripts (RTK, PostToolUse hooks)
copilot/   Copilot CLI orchestrator
```

`common/tool_profile.sh` resolves all tool-specific paths (`~/.claude` vs `~/.copilot`,
`CLAUDE.md` vs `AGENTS.md`, `.claudeignore` vs `.copilotignore`) and feature flags.
Every shared script reads the profile instead of hardcoding a tool.

## Setup

```bash
source bootstrap.sh             # interactive wizard: activation + Atlassian + MCP + diagnostics
```

or activate a single tool directly:

```bash
source claude/claude_env.sh     # Claude Code
source copilot/copilot_env.sh   # Copilot CLI
```

Each orchestrator syncs the scripts to the tool home (`~/.claude/scripts/` or
`~/.copilot/scripts/`), writes the global instructions file, installs the shell
wrapper and hooks, then defines the wrapped command for the current shell.
After the first activation, just run `claude` or `copilot` from any project.

## MCP — Atlassian & Bitbucket (per project)

Registering MCP servers at user scope injects their ~150 tool definitions into
**every** session — tens of thousands of tokens wasted in projects that never
touch Jira. Instead, credentials are stored once and MCP is enabled per project:

```bash
bash common/setup_atlassian.sh              # one-time: prompt + validate + store tokens
cd <project> && bash common/setup_mcp_project.sh   # per project that needs Atlassian
bash common/setup_mcp_project.sh -u         # disable for a project
```

`setup_mcp_project.sh` writes a local `.mcp.json` — read natively by both Claude
Code and Copilot CLI — and excludes it from git via `.git/info/exclude` (it
contains tokens). Tokens live in `~/.config/llm_cli/atlassian.env` (chmod 600).

The three servers use the exact IDs of the enterprise MCP registry
(`mcp-registry.exail.com`): `io.github.b1ff/atlassian-dc-mcp-{jira,confluence,bitbucket}`.
Copilot's enterprise "Registry only" allowlist matches on server name — a server
configured under any other name (e.g. `jira`, `mcp-atlassian`) is blocked.

## Diagnostics

```bash
bash common/check_optimizations.sh claude  [project_path]
bash common/check_optimizations.sh copilot [project_path]
rtk gain    # RTK token savings after a session
```

See `claude/README.md` and `copilot/README.md` for tool-specific details.
