"""Instructions and ignore-file templates (port of setup_context.sh and the
template parts of setup_context_cache.sh, plus their PowerShell twins).

Templates use {{NAME}} placeholders substituted by plain replace — the content
itself contains markdown braces, so str.format would be a trap.
"""

from __future__ import annotations

from pathlib import Path

from llm_cli import paths, platforms
from llm_cli.services import config, fs, settings_editor, text_blocks
from llm_cli.tool_profile import ToolProfile

INDEX_ENTRY_MARKER = "# Project context index"

_IGNORE_TEMPLATE = """\
# {{IGNORE_FILE}} — files excluded from the context index (gitignore-style)

# Hidden files and directories
.*
!{{IGNORE_FILE}}
!.gitignore
!.env.example

# Dependencies
node_modules/
vendor/
.venv/
venv/
env/
site-packages/

# Build and dist
dist/
build/
out/
target/
__pycache__/
*.pyc
*.class
*.o
*.a
*.so
*.dll
*.exe

# Generated and minified assets
*.min.js
*.min.css
*.bundle.js
*.map

# Locks
package-lock.json
yarn.lock
pnpm-lock.yaml
poetry.lock
Pipfile.lock
Cargo.lock
composer.lock
Gemfile.lock

# Logs and coverage
*.log
logs/
*.out
coverage/
htmlcov/
lcov.info

# IDE and OS
.idea/
.vscode/
*.swp
.DS_Store
Thumbs.db

# Certificates and secrets
*.pem
*.key
*.cert
*.p12
*.pfx
*.jks

# Archives, binaries and media
*.zip
*.tar
*.tar.gz
*.rar
*.7z
*.jar
*.war
*.bin
*.dat
*.db
*.sqlite
*.sqlite3
*.png
*.jpg
*.jpeg
*.gif
*.ico
*.svg
*.webp
*.mp4
*.mp3
*.pdf
"""

_INDEX_ENTRY_TEMPLATE = """\
# Project context index
A compact symbol index of {{PROJECT_PATH}} is pre-generated at:
  `{{CACHE_FILE}}`
Read it at session start, identify the 2-3 relevant files, then open only those.
Format: path | LOC | symbols. A missing file is either in {{IGNORE_FILE}} or not yet created.

Auto-refresh (re-read the index after these events):
{{REFRESH_TRIGGERS}}

Regenerate manually after large structural changes:
  {{RUN}} setup-context-cache {{PROJECT_PATH}} --tool {{TOOL_NAME}}

Global standards, MCP tools reference and git clone helper: see {{INSTRUCTIONS_GLOBAL}}
"""

# Shared behavioral core — deliberately compact: it is loaded into context on
# every turn of every session, so every line here has a permanent token cost.
_GLOBAL_TEMPLATE = """\
# Code quality (SOLID)
- Naming: snake_case variables, CamelCase classes, UPPER_SNAKE_CASE constants. Descriptive names, no cryptic abbreviations.
- Functions: single responsibility, max ~20 lines, guard clauses, max 2 nesting levels, no magic numbers or strings.
- Comments: English, explain why not what, no commented-out code, one-line doc per public function/class.
- Modules: single responsibility, depend on abstractions, open for extension closed for modification.
- Architecture: keep the tree clean and coherent — create new folders, files and classes whenever it
  preserves structure and organization; never cram unrelated logic into an existing file.
- Errors: never swallowed silently; always carry context (what failed, where, why).
- No duplicate logic — extract immediately. Consistency with existing codebase patterns wins over preference.

# Engineering context
All code and data are confidential. Jira = tracking, Confluence = docs, Bitbucket = source.
Research before assuming: verify any API, interface or module in Bitbucket (`search_code`, `get_file_content`),
Confluence (architecture docs) or Jira (acceptance criteria) — never guess what can be checked.
Jira workflow: read the full ticket description AND all comments before working; comment status when done or blocked.

# Commits & PRs
Commit format: [JIRA-KEY] short imperative description. Branch: feature/JIRA-KEY-short-description.
Reference the Jira ticket in commits and PR descriptions.
NEVER run git push without explicit user confirmation. Force push is strictly forbidden.

# Security
Never log, print, commit or hardcode credentials, tokens, API keys or PII — env vars or secret managers only.
Internal company URLs must not appear in external-facing documentation or public code.
Delete temporary credential files immediately after use.

# Destructive actions
Before a multi-file refactor: summarize the plan and wait for confirmation.
Never delete files or overwrite uncommitted changes without explicit user confirmation.

# Token economy
Be concise. For code tasks: return code only, no explanation, unless the user asks for one.
Read the project context index first (see the local {{INSTRUCTIONS_LOCAL}}) and open only the 2-3 relevant files
instead of scanning the tree. Avoid re-reading files already in context.
Scope tasks narrowly: one focused objective per session beats one sprawling session.

# MCP tools — Atlassian & Bitbucket (global, user scope)
MCP servers are registered globally (user scope), once, for this user — active in every session.
If Jira/Confluence/Bitbucket tools are needed but unavailable, (re)run:
  {{RUN}} setup-mcp
Three Data Center servers (io.github.b1ff/atlassian-dc-mcp-*): Jira (issues, search, comments),
Confluence (pages, search), Bitbucket (repos, files, code search — REST API, no git operations).
Prefer MCP browsing to read individual files; git clone only to run code or tests locally:
  {{RUN}} git-clone <PROJECT>/<repo>
URL pattern: {{BITBUCKET_URL}}/scm/<PROJECT_KEY>/<repo-slug>.git (key uppercase, slug lowercase).

# Maintenance commands ({{RUN}} ...)
- setup-env --tool {{TOOL_NAME}} — full environment repair (sync, instructions, hooks). Run when anything seems out of date.
- setup-context-cache [path] — regenerate the project symbol index after structural changes (-u to remove).
- setup-mcp — enable Atlassian+Bitbucket MCP globally, once (-u to remove).
- setup-headroom --tool {{TOOL_NAME}} — install/repair the Headroom compression proxy wrap (-u to unwrap).
- check {{TOOL_NAME}} [path] — diagnose the optimization setup (cache, wrapper, hooks, headroom).
- git-clone <PROJECT>/<repo> — clone from the configured Bitbucket host with stored credentials.
"""

_CLAUDE_EXTRA = """\

# Subagents
For large codebase exploration or parallel research, delegate to subagents to keep the main context clean.
Reports must stay under 500 words — no raw file dumps. Not for small targeted reads (use Read/Grep directly).

# Context hygiene
Around 60% context usage, run /compact with a hint on what to keep (current task, key files, decisions).
Use /context to audit what is consuming the window before starting a long task.

@RTK.md
"""

_COPILOT_EXTRA = """\

# CLI output compression (RTK)
If the `rtk` binary is available, prefix shell commands with it to compress their output
before it reaches context: `rtk git status`, `rtk git diff`, `rtk grep`, `rtk ls`, `rtk read <file>`.
Fall back to the plain command if rtk fails.
"""

_OPENCODE_EXTRA = """\

# CLI output compression (RTK)
OpenCode has no PreToolUse hook system, so compression is opt-in: when the `rtk`
binary is available, prefix shell commands with it to compress their output
before it reaches context (`rtk git status`, `rtk git diff`, `rtk grep`, `rtk ls`,
`rtk read <file>`). Fall back to the plain command if rtk fails.
"""

# Per-tool tail appended to the shared behavioral core.
_TOOL_EXTRA = {
    "claude": _CLAUDE_EXTRA,
    "copilot": _COPILOT_EXTRA,
    "opencode": _OPENCODE_EXTRA,
}


def run_command_prefix() -> str:
    """How generated docs tell the agent to invoke llm_cli."""
    python = platforms.current().default_python_hint()
    return f"{python} {paths.run_py()}"


def write_ignore_file(profile: ToolProfile, directory: Path) -> bool:
    """Creates the tool ignore file when absent; returns True when created."""
    ignore_file = directory / profile.ignore_file
    if ignore_file.is_file():
        return False
    body = _IGNORE_TEMPLATE.replace("{{IGNORE_FILE}}", profile.ignore_file)
    fs.write_text_atomic(ignore_file, body)
    return True


def inject_index_entry(
    profile: ToolProfile, cache_file: Path, project_path: Path, launch_dir: Path
) -> Path:
    """Writes the index pointer entry into the local instructions file
    (removes any previous entry first so the path stays current)."""
    instructions_file = launch_dir / profile.instructions_local
    text_blocks.strip_markdown_section(instructions_file, INDEX_ENTRY_MARKER)

    entry = (
        _INDEX_ENTRY_TEMPLATE
        .replace("{{PROJECT_PATH}}", str(project_path))
        .replace("{{CACHE_FILE}}", str(cache_file))
        .replace("{{IGNORE_FILE}}", profile.ignore_file)
        .replace("{{REFRESH_TRIGGERS}}", _refresh_triggers(profile))
        .replace("{{RUN}}", run_command_prefix())
        .replace("{{TOOL_NAME}}", profile.name)
        .replace("{{INSTRUCTIONS_GLOBAL}}", str(profile.instructions_global))
    )
    text_blocks.append_section(instructions_file, entry)
    return instructions_file


def strip_index_entry(profile: ToolProfile, directory: Path) -> bool:
    """Removes the index pointer entry; returns True when one was present."""
    instructions_file = directory / profile.instructions_local
    return text_blocks.strip_markdown_section(instructions_file, INDEX_ENTRY_MARKER)


def write_global_instructions(profile: ToolProfile) -> Path:
    """Overwrites the global instructions file entirely — always authoritative."""
    extra = _TOOL_EXTRA.get(profile.name, _COPILOT_EXTRA)
    body = (
        (_GLOBAL_TEMPLATE + extra)
        .replace("{{INSTRUCTIONS_LOCAL}}", profile.instructions_local)
        .replace("{{RUN}}", run_command_prefix())
        .replace("{{TOOL_NAME}}", profile.name)
    )
    body = _substitute_bitbucket_url(body)
    # opencode's config dir (~/.config/opencode) may not exist yet on first run.
    profile.instructions_global.parent.mkdir(parents=True, exist_ok=True)
    fs.write_text_atomic(profile.instructions_global, body)
    if profile.name == "opencode":
        _register_global_in_opencode_config(profile)
    return profile.instructions_global


def _register_global_in_opencode_config(profile: ToolProfile) -> None:
    """opencode only loads a global instructions file when it is listed in the
    `instructions` array of its config — register ours there (idempotent),
    preserving every other field of opencode.json (provider, model, ...)."""
    config_file = profile.settings_json  # ~/.config/opencode/opencode.json
    config = settings_editor.load_json(config_file)
    instructions_list = config.setdefault("instructions", [])
    global_path = str(profile.instructions_global)
    if global_path not in instructions_list:
        instructions_list.append(global_path)
    settings_editor.save_json(config_file, config)


def _refresh_triggers(profile: ToolProfile) -> str:
    if profile.has_agent_hooks:
        return (
            "- Any Write tool call (new file created)\n"
            "- git checkout, switch, merge, pull, rebase, clone\n"
            f"- Every `{profile.name}` launch (stale detection via shell wrapper)"
        )
    return (
        f"- Every `{profile.name}` launch (stale detection via shell wrapper)\n"
        "- git checkout, switch, merge, pull, rebase (via git hooks)"
    )


def _substitute_bitbucket_url(body: str) -> str:
    """The Bitbucket URL comes from the llm_cli config; its line is dropped
    entirely when not configured yet."""
    bitbucket_url = config.load().get("BITBUCKET_URL", "")
    if bitbucket_url:
        return body.replace("{{BITBUCKET_URL}}", bitbucket_url)
    return "".join(
        line for line in body.splitlines(keepends=True)
        if "{{BITBUCKET_URL}}" not in line
    )
