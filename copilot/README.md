# GitHub Copilot CLI — Token Optimization Setup

Activates the shared optimization layer (see repository root README) for Copilot CLI.

## Setup

```bash
source copilot_env.sh
```

Runs automatically on first activation:
- installs Node >= 20 and the `copilot` binary if missing (`npm install -g @github/copilot`)
- syncs `common/` scripts to `~/.copilot/scripts/`
- writes the compact global instructions to `~/.copilot/copilot-instructions.md`
- installs a persistent `copilot()` wrapper in `.zshrc` / `.bashrc`

After that, run `copilot` from any project directory — the wrapper regenerates the
project symbol index when stale, then launches Copilot CLI.

## Headroom (launcher mode)

Copilot has no durable settings routing: headroom builds a transient BYOK
environment at launch, so the `copilot()` wrapper launches through
`headroom wrap copilot` when routing credentials are available:
- `ANTHROPIC_API_KEY` (or `COPILOT_PROVIDER_API_KEY`) in the environment → BYOK mode;
- otherwise a saved Copilot OAuth token (`headroom copilot-auth login`) → `--subscription` mode;
- neither → plain launch, compression idle (nothing breaks).

Opt out for one session with `LLM_CLI_NO_HEADROOM=1 copilot`.

### GitHub Enterprise (ghe.com / GHE Server)

If your Copilot subscription lives on a GitHub Enterprise instance, the default
OAuth login (github.com) will not see your license. Configure the domain once:

1. `bash common/setup_atlassian.sh` and fill the optional
   "GitHub Enterprise domain for Copilot" prompt (or add
   `GITHUB_COPILOT_ENTERPRISE_DOMAIN=mycompany.ghe.com` to
   `~/.config/llm_cli/atlassian.env`).
2. `headroom copilot-auth login --domain mycompany.ghe.com` — every idle/help
   message prints this exact command once the domain is configured.
3. Relaunch `copilot`: the wrapper exports the domain so headroom routes the
   subscription through `copilot-api.<domain>`. If a proxy was already running
   without it, restart it once: `pkill -f "headroom proxy"`.

## Copilot specifics

- The local instructions file is `AGENTS.md` (Copilot CLI's primary instructions
  file); the index pointer entry is injected there by `setup_context_cache.sh`.
- Copilot CLI has no PreToolUse/PostToolUse hook system, so:
  - cache refresh relies on the shell wrapper and git hooks only;
  - RTK compression is driven through instructions (`rtk git status`, `rtk grep`, ...)
    instead of an automatic hook.
- Global instructions include "code only, no explanation" — output tokens cost ~5x
  input tokens under usage-based billing.
- `GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP=true` is exported so any project-local
  `.mcp.json` is also loaded in prompt mode (`copilot -p`). Atlassian/Bitbucket MCP
  itself is registered globally (see root README, MCP section), not per project.

## Files

| File | Description |
|---|---|
| `copilot_env.sh` | Orchestrator — profile export, prerequisites, common setup, wrapper |
| `scripts/setup_prerequisites.sh` | Installs Node >= 20 and the Copilot CLI when missing |

All the scripts (index generation, instructions, git hooks, MCP setup, diagnostics)
are shared and live in `../common/` — see the root README.
