"""Instructions and ignore-file templates (port of setup_context.sh and the
template parts of setup_context_cache.sh, plus their PowerShell twins).

Templates use {{NAME}} placeholders substituted by plain replace — the content
itself contains markdown braces, so str.format would be a trap.
"""

from __future__ import annotations

from pathlib import Path

from llm_cli import paths, platforms
from llm_cli.services import fs, text_blocks
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
`{{CACHE_FILE}}` is a pre-generated symbol index of {{PROJECT_PATH}} (one line per file: path | LOC | symbols).
Read it before exploring the tree, then open only the relevant files.
It refreshes automatically (hooks + launch); files absent from it are excluded by {{IGNORE_FILE}} or don't exist yet.
Manual rebuild after large structural changes: {{RUN}} setup-context-cache {{PROJECT_PATH}} --tool {{TOOL_NAME}}
Global rules: see {{INSTRUCTIONS_GLOBAL}}
"""

# Shared behavioral core — loaded into context on every turn of every session,
# so it carries only imperative, non-derivable rules: anything the model does
# natively (naming, structure, tool discovery) is deliberately absent.
_GLOBAL_TEMPLATE = """\
# Rules
- Code, comments, commit messages and docs: English only.
- Follow the existing codebase conventions; when in doubt, mirror the closest similar file.
- Apply SOLID: single responsibility per function, class and module; keep functions short — split rather than grow.
- Keep the tree clean: create new folders, files and classes freely instead of crowding existing ones.
- Before a multi-file refactor: present a short plan and wait for confirmation.
- Never delete files or overwrite uncommitted changes without explicit user confirmation.

# Commits & PRs
- Commit: `[JIRA-KEY] short imperative description`. Branch: `feature/JIRA-KEY-short-description`.
- Reference the Jira ticket in commits and PR descriptions.
- NEVER `git push` without explicit user confirmation. Force push is forbidden.

# Jira workflow
Read the full ticket description AND all comments before starting work.
Comment on the ticket when done or blocked.

# Security
All code and data are confidential.
Credentials, tokens, API keys, PII: env vars or secret managers only — never in code, logs, commits or docs.
Internal company URLs must not appear in public code or external-facing documentation.

# Maintenance ({{RUN}} ...)
Repair commands when the environment looks broken or out of date:
- setup-env --tool {{TOOL_NAME}} — full repair (sync, instructions, hooks)
- setup-context-cache [path] — rebuild the project symbol index (-u to remove)
- setup-mcp — register the Atlassian/Bitbucket MCP servers (-u to remove)
- check {{TOOL_NAME}} [path] — diagnose the setup
- git-clone <PROJECT>/<repo> — clone from the configured Bitbucket host with stored credentials
"""

# Copilot has no hook system, so RTK usage must be instruction-driven (claude
# gets it transparently through the PreToolUse hook — no instructions needed).
_COPILOT_EXTRA = """\

# CLI output compression (RTK)
Prefix shell commands with `rtk` when available — `rtk git status`, `rtk git diff`, `rtk grep`,
`rtk ls`, `rtk read <file>` — it compresses output before it reaches context.
Fall back to the plain command if rtk fails.
"""

# Per-tool tail appended to the shared behavioral core.
_TOOL_EXTRA = {
    "claude": "",
    "copilot": _COPILOT_EXTRA,
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
        .replace("{{RUN}}", run_command_prefix())
        .replace("{{TOOL_NAME}}", profile.name)
    )
    # The tool's home dir (~/.claude, ~/.copilot) may not exist yet on first run.
    profile.instructions_global.parent.mkdir(parents=True, exist_ok=True)
    fs.write_text_atomic(profile.instructions_global, body)
    return profile.instructions_global
