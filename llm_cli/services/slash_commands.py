"""Slash commands written into the Claude config home.

Claude Code reads user commands from ~/.claude/commands/<name>.md, and
claude_config.py already symlinks that directory into every provider config
home — so one file here is the same command under `claude`, `claude -glm` and
`claude -copilot`. The bodies live in templates/slash_commands.yaml.

Names must not collide with a built-in (/model, /usage): the built-in wins.
"""

from __future__ import annotations

from pathlib import Path

from llm_cli import paths
from llm_cli.services import fs, instructions, templates

COMMAND_NAMES = ("models", "quota")
_COMMANDS_DIR = "commands"
_TEMPLATE = "slash_commands"


def commands_dir(home: Path) -> Path:
    """Where Claude Code looks for user commands under a config home."""
    return home / _COMMANDS_DIR


def install(home: Path) -> list[Path]:
    """Writes every llm_cli slash command; returns the files written."""
    target = commands_dir(home)
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for name in COMMAND_NAMES:
        body = (
            templates.text(_TEMPLATE, name)
            .replace("{{RUN}}", instructions.run_command_prefix())
            .replace("{{CONFIG_FILE}}", str(paths.config_env()))
        )
        command_file = target / f"{name}.md"
        fs.write_text_atomic(command_file, body)
        written.append(command_file)
    return written


def remove(home: Path) -> list[Path]:
    """Deletes the llm_cli slash commands only; leaves the user's own alone."""
    removed = []
    for name in COMMAND_NAMES:
        command_file = commands_dir(home) / f"{name}.md"
        if command_file.is_file():
            command_file.unlink()
            removed.append(command_file)
    return removed
