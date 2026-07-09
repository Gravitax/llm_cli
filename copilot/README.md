# GitHub Copilot CLI — Token Optimization Setup

Activates the shared optimization layer (see repository root README) for Copilot CLI.

## Setup

```bash
source copilot_env.sh
```

Runs automatically on first activation:
- checks the `copilot` binary (install: `npm install -g @github/copilot`)
- syncs `common/` scripts to `~/.copilot/scripts/`
- writes the compact global instructions to `~/.copilot/copilot-instructions.md`
- installs a persistent `copilot()` wrapper in `.zshrc` / `.bashrc`

After that, run `copilot` from any project directory — the wrapper regenerates the
project symbol index when stale, then launches Copilot CLI.

## Copilot specifics

- The local instructions file is `AGENTS.md` (Copilot CLI's primary instructions
  file); the index pointer entry is injected there by `setup_context_cache.sh`.
- Copilot CLI has no PreToolUse/PostToolUse hook system, so:
  - cache refresh relies on the shell wrapper and git hooks only;
  - RTK compression is driven through instructions (`rtk git status`, `rtk grep`, ...)
    instead of an automatic hook.
- Global instructions include "code only, no explanation" — output tokens cost ~5x
  input tokens under usage-based billing.
- `GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP=true` is exported so the project-local
  `.mcp.json` (see root README, MCP section) is also loaded in prompt mode (`copilot -p`).

## Files

| File | Description |
|---|---|
| `copilot_env.sh` | Orchestrator — profile export, binary check, common setup, wrapper |

All the scripts (index generation, instructions, git hooks, MCP setup, diagnostics)
are shared and live in `../common/` — see the root README.
