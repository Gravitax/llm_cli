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
| Atlassian & Bitbucket MCP | Global, user-scope registration — enabled once for every session | ✓ | ✓ |

## Layout

```
common/    shared scripts, parameterized by tool profile (claude | copilot)
claude/    Claude Code orchestrator + Claude-only scripts (RTK, PostToolUse hooks)
copilot/   Copilot CLI orchestrator
windows/   Windows PowerShell 5.1 port (Claude only) — mirror tree of the above
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

## Windows (PowerShell 5.1)

The `windows/` tree is a native port of the core (Claude only — no Copilot,
no Atlassian/MCP setup). It expects `python` (>= 3.9), Node >= 20, git for
Windows, and a Windows `rtk.exe` on PATH.

```powershell
. .\windows\bootstrap.ps1        # dot-source it: wizard + activation + diagnostics
```

Notable differences from the bash layer, everything else is equivalent:

- The `claude` wrapper function is written to `$PROFILE.CurrentUserAllHosts`
  (marker-delimited block) instead of `~/.bashrc`/`~/.zshrc`.
- The project hash is always delegated to Python (`Get-ProjectHash` in
  `lib_cache.ps1`) so it matches `gen_context_cache.py` regardless of path
  casing or separators; nothing else may compute it.
- Git hooks stay `sh` scripts (git for Windows runs hooks under its own
  `sh.exe`) but delegate to `git_hook_refresh.ps1` via `cygpath -w`.
- `settings.json` is edited natively (`lib_settings.ps1`) — jq is not needed.
- `setup_rtk.ps1` never installs RTK itself (the curl|sh installer is
  Unix-only); it configures the hook and prints install guidance if missing.

## MCP — Atlassian & Bitbucket (global, one-time)

MCP servers are registered globally (user scope), once, so Jira/Confluence/
Bitbucket tools are available in every session without per-project setup.
This trades the ~150 tool definitions being loaded in every session (token
cost) for a simpler, one-time init:

```bash
bash common/setup_atlassian.sh       # one-time: prompt + validate + store tokens, then registers MCP globally
bash common/setup_mcp_global.sh      # (re)apply the global registration on its own
bash common/setup_mcp_global.sh -u   # remove the global registration
```

`setup_mcp_global.sh` writes the servers directly into each tool's user-scope
config (`~/.claude.json` for Claude Code, `~/.copilot/mcp-config.json` for
Copilot CLI). Tokens live in `~/.config/llm_cli/atlassian.env` (chmod 600) and
are passed through the environment, never through argv.

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
