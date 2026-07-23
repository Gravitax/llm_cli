"""Tool-specific paths and feature flags (port of tool_profile.sh / tool_profile.ps1).

Every command receives the tool explicitly — the old profile.env indirection
(needed because sourced shell scripts shared mutable globals) disappears.
"""

from dataclasses import dataclass
from pathlib import Path

from llm_cli import paths


@dataclass(frozen=True)
class ToolProfile:
    """Immutable description of one supported agent CLI."""

    name: str
    instructions_global_name: str
    instructions_local: str
    ignore_file: str
    # Claude Code supports settings.json hooks: RTK PreToolUse + cache PostToolUse.
    has_rtk_hook: bool
    has_agent_hooks: bool
    # Claude Code reads user slash commands from <home>/commands/*.md.
    has_slash_commands: bool
    # "settings": durable proxy routing in settings.json (proxy must be up).
    # "launcher": no durable routing — the launch itself goes through `headroom wrap`.
    headroom_mode: str

    @property
    def home(self) -> Path:
        """User directory for this tool — config, cache and projects live here."""
        return paths.home() / f".{self.name}"

    @property
    def instructions_global(self) -> Path:
        return self.home / self.instructions_global_name

    @property
    def settings_json(self) -> Path:
        # Plain JSON round-tripped by settings_editor; the hook/wrap fields are
        # only touched under their feature flags.
        return self.home / "settings.json"

    @property
    def projects_dir(self) -> Path:
        return self.home / "projects"


CLAUDE = ToolProfile(
    name="claude",
    instructions_global_name="CLAUDE.md",
    instructions_local="CLAUDE.md",
    ignore_file=".claudeignore",
    has_rtk_hook=True,
    has_agent_hooks=True,
    has_slash_commands=True,
    headroom_mode="settings",
)

COPILOT = ToolProfile(
    name="copilot",
    instructions_global_name="copilot-instructions.md",
    instructions_local="AGENTS.md",
    ignore_file=".copilotignore",
    has_rtk_hook=False,
    has_agent_hooks=False,
    has_slash_commands=False,
    headroom_mode="launcher",
)

ALL_PROFILES = (CLAUDE, COPILOT)

# Single source of truth for argparse `choices=` — replaces the scattered
# hardcoded ["claude", "copilot"] lists.
TOOL_NAMES = tuple(profile.name for profile in ALL_PROFILES)


def resolve(name: str) -> ToolProfile:
    """Maps a tool name to its profile; fails loudly on anything unknown."""
    for profile in ALL_PROFILES:
        if profile.name == name:
            return profile
    raise ValueError(
        f"unknown tool profile '{name}' (expected: {' | '.join(TOOL_NAMES)})"
    )
