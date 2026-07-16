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
    has_headroom: bool
    # "settings": durable proxy routing in settings.json (proxy must be up).
    # "launcher": no durable routing — the launch itself goes through `headroom wrap`.
    # "none": headroom does not apply to this tool.
    headroom_mode: str
    # Subpath under the home dir where the tool's CONFIG actually lives.
    # Empty means "~/.<name>" (claude, copilot). opencode keeps its config in
    # "~/.config/opencode" (not "~/.opencode"), so it sets this explicitly.
    config_subpath: str = ""

    @property
    def home(self) -> Path:
        """User directory for this tool — the cache/projects tree lives here."""
        return paths.home() / f".{self.name}"

    @property
    def config_dir(self) -> Path:
        """Where the tool reads its own config and global instructions."""
        if self.config_subpath:
            return paths.home() / self.config_subpath
        return self.home

    @property
    def instructions_global(self) -> Path:
        return self.config_dir / self.instructions_global_name

    @property
    def settings_json(self) -> Path:
        # The tool's main JSON config: opencode.json for opencode, settings.json
        # otherwise. Both are plain JSON round-tripped by settings_editor; the
        # hook/wrap fields are only touched under their feature flags.
        filename = "opencode.json" if self.name == "opencode" else "settings.json"
        return self.config_dir / filename

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
    has_headroom=True,
    headroom_mode="settings",
)

COPILOT = ToolProfile(
    name="copilot",
    instructions_global_name="copilot-instructions.md",
    instructions_local="AGENTS.md",
    ignore_file=".copilotignore",
    has_rtk_hook=False,
    has_agent_hooks=False,
    has_headroom=True,
    headroom_mode="launcher",
)

# opencode routes to its own provider (e.g. GLM via zai-coding-plan), not the
# Anthropic API that headroom proxifies, so it has no headroom. It also has no
# PreToolUse/PostToolUse hook system, so RTK is driven through instructions and
# cache refresh relies on the launch check + git hooks (like copilot).
OPENCODE = ToolProfile(
    name="opencode",
    instructions_global_name="AGENTS.md",
    instructions_local="AGENTS.md",
    ignore_file=".opencodeignore",
    has_rtk_hook=False,
    has_agent_hooks=False,
    has_headroom=False,
    headroom_mode="none",
    config_subpath=".config/opencode",
)

ALL_PROFILES = (CLAUDE, COPILOT, OPENCODE)

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
