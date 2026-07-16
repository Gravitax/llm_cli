# Claude Code — Token Optimization Setup

Activates the shared optimization layer (see repository root README) for Claude Code,
plus the Claude-only features: RTK output compression and PostToolUse cache hooks.

## Setup

```bash
python install.py           # installs everything, then run `claude`
```

Runs automatically on activation:
- checks Node.js >= 20 and installs Claude Code if missing
- installs the Python core to `~/.llm_cli/` (`sync`) + the `claude` entry point (pip)
- writes the compact global instructions to `~/.claude/CLAUDE.md`
- installs RTK and its PreToolUse bash-compression hook
- registers PostToolUse hooks (cache refresh on git commands and new files)
- writes the persistent PATH activation block in `.zshrc` / `.bashrc`
  (`$PROFILE.CurrentUserAllHosts` on Windows)

After that, run `claude` from any project directory — `launch` regenerates the
project symbol index when stale, starts the headroom proxy if wrapped, then
launches Claude Code (telemetry opt-out exported).

## GLM provider (z.ai) — `claude -glm`

`claude -glm` toggles the provider between the Anthropic API (default) and the
GLM Coding Plan via z.ai's Anthropic-compatible endpoint. The toggle is
**persistent**: after switching, every plain `claude` launch stays on the last
chosen provider (each GLM launch prints `Provider: GLM (z.ai)` as a reminder)
until the next `claude -glm`.

In GLM mode the launcher exports `ANTHROPIC_BASE_URL`
(`https://api.z.ai/api/anthropic`), `ANTHROPIC_AUTH_TOKEN`, and remaps the
Opus/Sonnet/Haiku model slots to `glm-5.2[1m]` / `glm-4.7`, so the GLM models
appear in the in-session `/model` picker. Pass `--model <id>` to override.

**API key — environment variable only (by design).** The z.ai key is read
exclusively from `GLM_API_KEY`; llm_cli never writes it to any file, so the
credential cannot leak through configs, backups, or commits. Set it yourself:

```powershell
$env:GLM_API_KEY = "<your z.ai key>"     # PowerShell ($PROFILE to persist)
```
```bash
export GLM_API_KEY=<your z.ai key>       # bash/zsh (.bashrc to persist)
```

If GLM mode is active and the variable is missing, the launch fails with a
banner instead of silently falling back to (and billing) the Anthropic API.
Only the provider choice is persisted (`CLAUDE_PROVIDER` in
`~/.config/llm_cli/atlassian.env`) — never the key.

## Claude-only optimizations

### RTK — CLI output compression (~70-80% savings on bash output)

A PreToolUse hook rewrites bash tool calls to RTK equivalents before execution:
the model only ever sees the compressed result (`git status/diff/log`, `ls`, `cat`,
`grep`, test runners, Docker, kubectl).

```bash
python3 ~/.llm_cli/run.py setup-rtk       # install / repair
python3 ~/.llm_cli/run.py setup-rtk -u    # remove hook (keeps binary)
rtk gain                                  # savings stats after a session
```

### PostToolUse cache hooks

Registered in `~/.claude/settings.json`, both invoking the installed core:
- `hook cache-refresh-git` — refreshes the index after structural git commands
- `hook cache-refresh-write` — refreshes the index when Claude creates a file

## Files

| File | Description |
|---|---|
| `../install.py` | One-command installer (pip + wizard) |
| `../llm_cli/entry.py` | `claude` console entry point (pip-installed wrapper) |
| `../llm_cli/commands/activate.py` | Activation flow (prerequisites, env, wrapper) |
| `../llm_cli/commands/setup_rtk.py` | RTK install + PreToolUse hook registration |
| `../llm_cli/commands/hooks.py` | PostToolUse + git hook entry points |

All the logic (index generation, instructions, git hooks, MCP setup, diagnostics)
is shared in `../llm_cli/` — see the root README.
