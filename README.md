# llm_cli — Token-optimization layer for Claude Code & Copilot CLI

Wraps `claude` and `copilot` with a shared optimization layer that cuts token
consumption and gives every agent a precise, pre-built view of each project.

One cross-platform Python core (Linux, macOS, Windows) — the former parallel
bash and PowerShell trees are gone, and so are the last shell shims. The
`claude`/`copilot` wrappers now ship as pip **console entry points**, so the
exact same install works everywhere with zero `.sh`/`.ps1` files.

## What it does

| Optimization | Mechanism | Claude | Copilot |
|---|---|---|---|
| Project symbol index | tree-sitter `path \| LOC \| symbols` cache, PageRank-ordered, read at session start instead of scanning files | ✓ | ✓ |
| Compact global instructions | Behavioral rules kept short — loaded every turn, every session | ✓ | ✓ |
| CLI output compression (RTK) | PreToolUse hook rewrites bash commands, ~70-80% savings on output | hook | via instructions |
| API-level compression (Headroom) | Proxy routing, ~15-20% savings on coding agents (60-95% on JSON) | settings wrap | launcher |
| GLM provider (z.ai) | `claude -glm` toggles Claude Code between Anthropic and the GLM Coding Plan | ✓ | ✗ |
| Copilot provider | `claude -copilot` routes Claude Code through the local `copilot-api` bridge | ✓ | ✗ |
| Auto cache refresh | Launch checks + git hooks (+ PostToolUse hooks for Claude) | ✓ | ✓ |
| Atlassian & Bitbucket MCP | Global, user-scope registration — enabled once for every session | ✓ | ✓ |

## Layout

```
llm_cli/             the Python core (invoked as `python3 run.py <command>`)
  cli.py             argparse tree + dispatch
  entry.py           `claude`/`copilot` console entry points (pip-installed)
  tool_profile.py    tool paths & feature flags (claude | copilot)
  platforms/         the ONLY place that branches on the OS (posix / windows)
  services/          reusable logic: indexer, cache, settings.json editor,
                     instructions templates, headroom, deps, atlassian API...
  commands/          one module per subcommand (orchestration only)
  vendor/            third-party trees shipped with the package (copilot-api)
install.py           one-command cross-platform installer (venv + pip + wizard)
pyproject.toml       packaging + the claude/copilot/llm_cli entry points
run.py               launcher — installed to ~/.llm_cli/run.py for hooks
claude/, copilot/    tool-specific docs
```

The package lives in the managed virtualenv `~/.llm_cli/.venv`, whose
`bin`/`Scripts` directory holds the `claude`/`copilot`/`llm_cli` executables and
is the directory added to PATH; the package and `run.py` are also copied to
`~/.llm_cli/` (via `sync`) so the settings.json hooks can reference a fixed path.
Requires a Python >= 3.9 interpreter to build that venv — `install.py` itself
runs on any Python and picks a suitable one from PATH.

## Setup

```bash
python install.py                # Linux/macOS/WSL/Windows — install + wizard
```

```bash
python install.py --no-wizard    # install the package + entry points only
```

`install.py` creates `~/.llm_cli/.venv` when missing then runs `pip install .`
inside it (installing the `claude`/`copilot` console executables), writes the
PATH activation block pointing at that venv into your shell profiles,
then runs the interactive wizard. The wizard installs missing dependencies
(node >= 20, uv, rtk, headroom and the selected agent CLIs — winget guidance
only on Windows), activates the layer, offers the Atlassian credentials + global
MCP setup, then runs the diagnostics. Or activate a single tool directly:

```bash
~/.llm_cli/.venv/bin/python ~/.llm_cli/run.py activate claude     # or: ... activate copilot
```

> Open a **new terminal** after installing so `claude`/`copilot` are on PATH —
> a running process cannot change its parent shell's PATH, on any OS.

After the first activation, just run `claude` or `copilot` from any project.
Every other operation is a subcommand of the core:

```bash
~/.llm_cli/.venv/bin/python ~/.llm_cli/run.py <command>

setup-env --tool claude        # full environment repair (sync, instructions, hooks)
setup-context-cache [path]     # regenerate the project symbol index (-u to remove)
setup-atlassian                # one-time credentials setup or token rotation
setup-mcp                      # global Atlassian+Bitbucket MCP (-u to remove)
setup-headroom --tool claude   # install/repair the compression proxy wrap (-u to unwrap)
check claude [path]            # diagnostics (cache, wrapper, hooks, headroom, MCP)
git-clone PROJECT/repo         # clone from the configured Bitbucket host
```

The `claude -glm` provider toggle switches Claude Code between the Anthropic API
and the GLM Coding Plan (z.ai).

The `claude -copilot` toggle switches Claude Code between Anthropic and GitHub
Copilot. On the first Copilot-backed launch, `llm_cli` installs
[`copilot-api`](https://github.com/ericc-ch/copilot-api), starts GitHub's device
authentication flow, then keeps the local Anthropic-compatible proxy running on
`127.0.0.1:4141`. The proxy stores its GitHub token itself in its user-private
data directory; `llm_cli` never reads, prints or copies that token.

That build is **not** the one on npm: a patched copy is vendored in
`llm_cli/vendor/copilot-api`, deployed to `~/.llm_cli/copilot-api` and installed
from there, so a clone of this repository is self-sufficient. The registry build
is github.com-only, binds to every network interface and answers `/token` with
the live Copilot bearer without authenticating the caller. See
`llm_cli/vendor/copilot-api/VENDORED.md` for the full list of changes — and for
the rule that any edit under its `src/` must be rebuilt and committed, since the
prebuilt bundle is what gets deployed.

```bash
claude -copilot   # switch to GitHub Copilot
claude            # authenticate on first use, then launch through Copilot
claude -copilot   # switch back to Anthropic
```

Models are picked from the live Copilot catalog and can be pinned in
`~/.config/llm_cli/atlassian.env`:

```text
CLAUDE_COPILOT_MODEL=gpt-5.6-terra
CLAUDE_COPILOT_OPUS_MODEL=claude-opus-4.8
CLAUDE_COPILOT_SMALL_MODEL=gpt-5.6-luna
CLAUDE_COPILOT_EXTRA_MODEL=gpt-5.6-sol
COPILOT_API_ACCOUNT_TYPE=individual
COPILOT_API_PORT=4141
```

`COPILOT_API_ACCOUNT_TYPE` accepts `individual`, `business` or `enterprise`.

## What `/model` can show

Claude Code's picker is not the provider's catalog. It lists its own model
slots, each remapped by an `ANTHROPIC_DEFAULT_*_MODEL` variable, plus what two
documented mechanisms add:

| Source | Copilot | GLM |
| --- | --- | --- |
| Slots (`sonnet`, `opus`, `haiku`) | `CLAUDE_COPILOT_MODEL`, `..._OPUS_MODEL`, `..._SMALL_MODEL` | `glm-5-turbo`, `glm-5.2[1m]`, `glm-4.6` |
| Gateway discovery of `/v1/models` | yes — but only ids starting with `claude` | no — every id starts with `glm-` |
| One free-form entry | `CLAUDE_COPILOT_EXTRA_MODEL` | `CLAUDE_GLM_EXTRA_MODEL` |

Discovery is on by default for Copilot and costs one request per launch; set
`CLAUDE_COPILOT_MODEL_DISCOVERY=0` to turn it off. It is mutually exclusive
with `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, which llm_cli therefore stops
exporting while discovery is on.

Everything else in the catalog is reachable at launch with
`claude --model <id>`. `claude --models` lists it: the flag is consumed by the
wrapper and follows the active provider, so it prints the Copilot catalog under
`-copilot`, the z.ai one under `-glm`, and the Anthropic aliases otherwise.

Two slash commands, installed by `setup-env` into `~/.claude/commands/` and
shared by all three providers, cover the rest:

| Command | What it does |
| --- | --- |
| `/models` | the full catalog of the active provider |
| `/quota` | the remaining quota of the active provider |

`/quota` exists because the built-in `/usage` only knows the Anthropic
subscription: it reports this session's tokens and cannot see a Copilot or
z.ai plan. It reads the GitHub Copilot quota through `copilot-api check-usage`
and the z.ai Coding Plan quota from `api.z.ai/api/monitor/usage/quota/limit`.
Both are also available outside a session:

```bash
llm_cli provider-models
llm_cli provider-usage
```

> `copilot-api` is a reverse-engineered, third-party proxy that is not supported
> by GitHub and may break when Copilot changes. Excessive automated use may
> trigger GitHub abuse detection or account restrictions; use it responsibly
> and review its upstream warnings before enabling this mode.

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
~/.llm_cli/.venv/bin/python ~/.llm_cli/run.py setup-atlassian   # one-time: prompt + validate + store tokens, then registers MCP globally
~/.llm_cli/.venv/bin/python ~/.llm_cli/run.py setup-mcp         # (re)apply the global registration on its own
~/.llm_cli/.venv/bin/python ~/.llm_cli/run.py setup-mcp -u      # remove the global registration
```

`setup-mcp` writes the servers directly into each tool's user-scope config
(`~/.claude.json` for Claude Code, `~/.copilot/mcp-config.json` for Copilot
CLI). The instance URLs and tokens are prompted by `setup-atlassian` (tokens
via hidden input; nothing company-specific is hardcoded) and live in
`~/.config/llm_cli/atlassian.env` (user-only access), passed through the
environment, never through argv.

The three servers use the exact IDs of your enterprise MCP registry (if any):
`io.github.b1ff/atlassian-dc-mcp-{jira,confluence,bitbucket}`.
Copilot's enterprise "Registry only" allowlist matches on server name — a server
configured under any other name (e.g. `jira`, `mcp-atlassian`) is blocked.

## Headroom — API-level context compression (opt-in, off by default)

[Headroom](https://github.com/headroomlabs-ai/headroom) compresses the request
payload between the agent and the provider API through a local proxy, on top of
RTK (CLI output) and the symbol index (project context) — three independent
layers.

It is **off unless you ask for it**: it inserts a proxy into every API call and
pulls a large dependency tree (`litellm` among others). Nothing is installed and
no routing is written until the toggle is on.

```bash
claude -u      # toggle headroom on, then off again — installs and wraps on first enable
copilot -u     # same switch for the copilot profile
```

The state persists as `HEADROOM_ENABLED` in the llm_cli config, and `setup-env`
skips headroom entirely while it is off. `LLM_CLI_NO_HEADROOM=1` still disables
it for a single session without touching the toggle.

Two routing modes, resolved by the tool profile:

- **claude (settings)** — durable `ANTHROPIC_BASE_URL` routing in
  `~/.claude/settings.json`; `launch` starts the proxy before each session.
- **copilot (launcher)** — no durable routing exists, so `launch` goes through
  `headroom wrap copilot` when credentials allow it (`ANTHROPIC_API_KEY` →
  BYOK, or `headroom copilot-auth login` → subscription); plain launch
  otherwise. Opt out per session: `LLM_CLI_NO_HEADROOM=1`.
  GitHub Enterprise Copilot is supported: set the domain once via
  `setup-atlassian` (`GITHUB_COPILOT_ENTERPRISE_DOMAIN`).

```bash
~/.llm_cli/.venv/bin/python ~/.llm_cli/run.py setup-headroom --tool claude      # install + wrap + verify
~/.llm_cli/.venv/bin/python ~/.llm_cli/run.py setup-headroom --tool claude -u   # unwrap — restore direct API access
headroom perf                                                                   # token savings after a session
```

## Diagnostics

```bash
~/.llm_cli/.venv/bin/python ~/.llm_cli/run.py check claude  [project_path]
~/.llm_cli/.venv/bin/python ~/.llm_cli/run.py check copilot [project_path]
rtk gain         # RTK token savings after a session
headroom perf    # Headroom savings (if wrapped)
```
