# llm_cli — Token-optimization layer for Claude Code, Copilot CLI & OpenCode

Wraps `claude`, `copilot` and `opencode` with a shared optimization layer that
cuts token consumption and gives every agent a precise, pre-built view of each
project.

One cross-platform Python core (Linux, macOS, Windows) — the former parallel
bash and PowerShell trees are gone, and so are the last shell shims. The
`claude`/`copilot`/`opencode` wrappers now ship as pip **console entry points**,
so the exact same install works everywhere with zero `.sh`/`.ps1` files.

## What it does

| Optimization | Mechanism | Claude | Copilot | OpenCode |
|---|---|---|---|---|
| Project symbol index | `path \| LOC \| symbols` cache read at session start instead of scanning files | ✓ | ✓ | ✓ |
| Compact global instructions | Behavioral rules kept short — loaded every turn, every session | ✓ | ✓ | ✓ |
| CLI output compression (RTK) | PreToolUse hook rewrites bash commands, ~70-80% savings on output | hook | via instructions | via instructions |
| API-level compression (Headroom) | Proxy routing, ~15-20% savings on coding agents (60-95% on JSON) | settings wrap | launcher | ✗ (GLM provider) |
| Auto cache refresh | Launch checks + git hooks (+ PostToolUse hooks for Claude) | ✓ | ✓ | ✓ |
| Atlassian & Bitbucket MCP | Global, user-scope registration — enabled once for every session | ✓ | ✓ | ✓ |

## Layout

```
llm_cli/             the Python core (invoked as `python3 run.py <command>`)
  cli.py             argparse tree + dispatch
  entry.py           `claude`/`copilot`/`opencode` console entry points (pip-installed)
  tool_profile.py    tool paths & feature flags (claude | copilot | opencode)
  platforms/         the ONLY place that branches on the OS (posix / windows)
  services/          reusable logic: indexer, cache, settings.json editor,
                     instructions templates, headroom, deps, atlassian API...
  commands/          one module per subcommand (orchestration only)
install.py           one-command cross-platform installer (pip + wizard)
pyproject.toml       packaging + the claude/copilot/opencode/llm_cli entry points
run.py               launcher — installed to ~/.llm_cli/run.py for hooks
claude/, copilot/, opencode/    tool-specific docs
```

`pip install` places the `claude`/`copilot`/`opencode`/`llm_cli` executables on
PATH; the package and `run.py` are also copied to `~/.llm_cli/` (via `sync`) so
the settings.json hooks can reference a fixed path. Requires Python >= 3.8
(`python3` on POSIX, `python` or `py -3` on Windows; override with `PYTHON_BIN`).

## Setup

```bash
python install.py                # Linux/macOS/WSL/Windows — install + wizard
```

```bash
python install.py --no-wizard    # install the package + entry points only
```

`install.py` runs `pip install --user .` (installing the `claude`/`copilot`
console executables), writes the PATH activation block into your shell profiles,
then runs the interactive wizard. The wizard installs missing dependencies
(node >= 20, uv, rtk, headroom and the selected agent CLIs — winget guidance
only on Windows), activates the layer, offers the Atlassian credentials + global
MCP setup, then runs the diagnostics. Or activate a single tool directly:

```bash
python3 ~/.llm_cli/run.py activate claude     # or: ... activate copilot | opencode
```

> Open a **new terminal** after installing so `claude`/`copilot`/`opencode` are
> on PATH — a running process cannot change its parent shell's PATH, on any OS.

After the first activation, just run `claude`, `copilot` or `opencode` from any
project. Every other operation is a subcommand of the core:

```bash
python3 ~/.llm_cli/run.py <command>

setup-env --tool claude        # full environment repair (sync, instructions, hooks)
setup-context-cache [path]     # regenerate the project symbol index (-u to remove)
setup-atlassian                # one-time credentials setup or token rotation
setup-mcp                      # global Atlassian+Bitbucket MCP (-u to remove)
setup-headroom --tool claude   # install/repair the compression proxy wrap (-u to unwrap)
check claude [path]            # diagnostics (cache, wrapper, hooks, headroom, MCP)
git-clone PROJECT/repo         # clone from the configured Bitbucket host
```

See `claude/README.md`, `copilot/README.md` and `opencode/README.md` for
tool-specific details. Note: OpenCode routes to its own provider (e.g. GLM via
`zai-coding-plan`), so the Headroom proxy does not apply to it — it gets the
index, instructions, RTK (via instructions) and MCP, but not API compression.

## Windows notes

Same Python core, same commands. The platform differences are isolated in
`llm_cli/platforms/windows.py`:

- The PATH activation block goes to `$PROFILE.CurrentUserAllHosts` (UTF-8 BOM +
  CRLF for PS 5.1) instead of `~/.bashrc`/`~/.zshrc`.
- Hook entries in `settings.json` carry `"shell": "powershell"` and an
  absolute interpreter path (immune to the Store `python` alias).
- Git hooks stay POSIX `sh` (Git for Windows bundles `sh.exe`); the shared
  hook body converts paths with `cygpath` before delegating to `run.py`.
- RTK is never auto-installed (the curl|sh installer is Unix-only): install
  `rtk.exe` from https://github.com/rtk-ai/rtk/releases into `~\.local\bin`.
- Synced files get their `Zone.Identifier` stream cleared (Unblock-File).

## MCP — Atlassian & Bitbucket (global, one-time)

MCP servers are registered globally (user scope), once, so Jira/Confluence/
Bitbucket tools are available in every session without per-project setup.
This trades the ~150 tool definitions being loaded in every session (token
cost) for a simpler, one-time init:

```bash
python3 ~/.llm_cli/run.py setup-atlassian   # one-time: prompt + validate + store tokens, then registers MCP globally
python3 ~/.llm_cli/run.py setup-mcp         # (re)apply the global registration on its own
python3 ~/.llm_cli/run.py setup-mcp -u      # remove the global registration
```

`setup-mcp` writes the servers directly into each tool's user-scope config
(`~/.claude.json` for Claude Code, `~/.copilot/mcp-config.json` for Copilot CLI,
`~/.config/opencode/opencode.json` under the `mcp` key for OpenCode). The instance URLs and tokens are prompted by `setup-atlassian` (tokens
via hidden input; nothing company-specific is hardcoded) and live in
`~/.config/llm_cli/atlassian.env` (user-only access), passed through the
environment, never through argv.

The three servers use the exact IDs of your enterprise MCP registry (if any):
`io.github.b1ff/atlassian-dc-mcp-{jira,confluence,bitbucket}`.
Copilot's enterprise "Registry only" allowlist matches on server name — a server
configured under any other name (e.g. `jira`, `mcp-atlassian`) is blocked.

## Headroom — API-level context compression (optional)

[Headroom](https://github.com/headroomlabs-ai/headroom) compresses the request
payload between the agent and the provider API through a local proxy, on top of
RTK (CLI output) and the symbol index (project context) — three independent
layers. Two routing modes, resolved by the tool profile:

- **claude (settings)** — durable `ANTHROPIC_BASE_URL` routing in
  `~/.claude/settings.json`; `launch` starts the proxy before each session.
- **copilot (launcher)** — no durable routing exists, so `launch` goes through
  `headroom wrap copilot` when credentials allow it (`ANTHROPIC_API_KEY` →
  BYOK, or `headroom copilot-auth login` → subscription); plain launch
  otherwise. Opt out per session: `LLM_CLI_NO_HEADROOM=1`.
  GitHub Enterprise Copilot is supported: set the domain once via
  `setup-atlassian` (`GITHUB_COPILOT_ENTERPRISE_DOMAIN`) — see `copilot/README.md`.

```bash
python3 ~/.llm_cli/run.py setup-headroom --tool claude      # install + wrap + verify
python3 ~/.llm_cli/run.py setup-headroom --tool claude -u   # unwrap — restore direct API access
headroom perf                                               # token savings after a session
```

## Diagnostics

```bash
python3 ~/.llm_cli/run.py check claude  [project_path]
python3 ~/.llm_cli/run.py check copilot [project_path]
python3 ~/.llm_cli/run.py check opencode [project_path]
rtk gain         # RTK token savings after a session
headroom perf    # Headroom savings (if wrapped)
```

See `claude/README.md`, `copilot/README.md` and `opencode/README.md` for
tool-specific details.
