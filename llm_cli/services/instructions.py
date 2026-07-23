"""Instructions and ignore-file writers (port of setup_context.sh and the
template parts of setup_context_cache.sh, plus their PowerShell twins).

The text bodies live in llm_cli/templates/instructions.yaml. {{NAME}}
placeholders are substituted by plain replace — the content itself contains
markdown braces, so str.format would be a trap.
"""

from __future__ import annotations

from pathlib import Path

from llm_cli import paths, platforms
from llm_cli.services import fs, templates, text_blocks
from llm_cli.tool_profile import ToolProfile

# Must match the first line of the index_entry template — it is how a previous
# entry is found and replaced in the local instructions file.
INDEX_ENTRY_MARKER = "# Project context index"


def run_command_prefix() -> str:
    """How generated docs tell the agent to invoke llm_cli."""
    return f"{platforms.current().venv_python()} {paths.run_py()}"


def write_ignore_file(profile: ToolProfile, directory: Path) -> bool:
    """Creates the tool ignore file when absent; returns True when created."""
    ignore_file = directory / profile.ignore_file
    if ignore_file.is_file():
        return False
    body = templates.text("instructions", "ignore_file").replace(
        "{{IGNORE_FILE}}", profile.ignore_file
    )
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
        templates.text("instructions", "index_entry")
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
    body = (
        _global_body(profile.name)
        .replace("{{RUN}}", run_command_prefix())
        .replace("{{TOOL_NAME}}", profile.name)
    )
    # The tool's home dir (~/.claude, ~/.copilot) may not exist yet on first run.
    profile.instructions_global.parent.mkdir(parents=True, exist_ok=True)
    fs.write_text_atomic(profile.instructions_global, body)
    return profile.instructions_global


def _global_body(tool: str) -> str:
    """Shared behavioral core plus the per-tool tail (blank-line separated)."""
    rules = templates.text("instructions", "global_rules")
    extras = templates.load("instructions").get("tool_extra", {})
    extra = extras.get(tool, extras.get("copilot", ""))
    return f"{rules}\n{extra}" if extra else rules
