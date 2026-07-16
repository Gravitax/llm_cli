# OpenCode — Token Optimization Setup

Activates the shared optimization layer (see repository root README) for
[OpenCode](https://opencode.ai), with the GLM models (provider `zai-coding-plan`).

OpenCode is wrapped like Claude/Copilot, with three differences driven by its
design:

- **No hook system** (like Copilot) → RTK runs through instructions, and cache
  refresh relies on the launch check + git hooks only.
- **No Headroom** → OpenCode routes to its own provider (GLM via `zai-coding-plan`),
  not the Anthropic API that Headroom proxifies. API-level compression does not
  apply here.
- **Config lives in `~/.config/opencode/`** (not `~/.opencode/`) → global
  instructions are written to `~/.config/opencode/AGENTS.md` and registered in
  `opencode.json["instructions"]`; MCP servers go under `opencode.json["mcp"]`.

## Setup

```bash
python install.py           # installs everything, then run `opencode`
```

Runs automatically on activation:
- installs Node >= 20 and the `opencode` binary if missing
  (`npm install -g opencode-ai`; a system install via curl/brew is left as-is)
- installs the Python core to `~/.llm_cli/` (`sync`) + the `opencode` entry point
- writes the compact global instructions to `~/.config/opencode/AGENTS.md` and
  adds it to `opencode.json["instructions"]`
- registers the persistent PATH activation block in `.zshrc` / `.bashrc`

After that, run `opencode` from any project directory — `launch` regenerates the
project symbol index when stale, then launches OpenCode.

The model/provider is **not** touched by this layer — configure `model`,
`small_model` and the `provider` block (e.g. `zai-coding-plan/glm-4.6`) in
`~/.config/opencode/opencode.json` yourself. llm_cli only appends to that file
(global instructions reference + Atlassian MCP); existing fields are preserved.

## What you get

| Optimization | Applies | Mechanism |
|---|---|---|
| Project symbol index | ✓ | `path \| LOC \| symbols` cache read at session start |
| Compact global instructions | ✓ | `~/.config/opencode/AGENTS.md`, loaded via `opencode.json["instructions"]` |
| RTK output compression | ✓ (opt-in) | instructions tell the agent to prefix commands with `rtk` |
| Auto cache refresh | ✓ | launch staleness check + git hooks |
| Atlassian & Bitbucket MCP | ✓ | global `opencode.json["mcp"]` registration |
| Headroom | ✗ | OpenCode uses GLM, not the Anthropic API Headroom proxifies |

## CLI output compression (RTK)

OpenCode has no PreToolUse hook, so compression is opt-in: the global
instructions tell the agent to prefix shell commands with `rtk` when the binary
is available (`rtk git status`, `rtk git diff`, `rtk grep`, `rtk read <file>`),
falling back to the plain command if `rtk` fails.

```bash
python3 ~/.llm_cli/run.py setup-rtk       # install RTK (shared across tools)
rtk gain                                  # savings stats after a session
```

## Atlassian & Bitbucket MCP

Registered globally under `opencode.json["mcp"]` (OpenCode's MCP shape:
`{type: "local", command: [...], env: {...}}`). Enable with the shared commands:

```bash
python3 ~/.llm_cli/run.py setup-atlassian   # one-time credentials
python3 ~/.llm_cli/run.py setup-mcp         # (re)apply the global registration
python3 ~/.llm_cli/run.py setup-mcp -u      # remove it
```

## Files

| File | Description |
|---|---|
| `../install.py` | One-command installer (pip + wizard) |
| `../llm_cli/entry.py` | `opencode` console entry point (pip-installed wrapper) |
| `../llm_cli/commands/activate.py` | Activation flow (prerequisites, env, wrapper) |
| `../llm_cli/commands/launch.py` | Direct launch (no headroom routing) |
| `../llm_cli/services/instructions.py` | Global instructions + `opencode.json` wiring |

All the logic (index generation, instructions, git hooks, MCP setup, diagnostics)
is shared in `../llm_cli/` — see the root README.
