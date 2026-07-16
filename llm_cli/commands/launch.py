"""launch — runs the pre-launch steps then hands the foreground to the tool.

The `claude`/`copilot` console entry points delegate here so all routing logic
(headroom wrap for copilot, telemetry opt-out, PATH fixes) lives in one tested
place. Since our entry point shares the tool's name, the real binary is resolved
by scanning PATH while excluding our own executable's directory — otherwise the
entry point would invoke itself in an infinite loop.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from llm_cli import platforms, tool_profile
from llm_cli.commands import prelaunch
from llm_cli.services import deps, headroom, log
from llm_cli.tool_profile import TOOL_NAMES, ToolProfile

_CLAUDE_TELEMETRY_OPT_OUT = {
    "DO_NOT_TRACK": "1",
    "CLAUDE_TELEMETRY_DISABLED": "1",
    "NO_UPDATE_NOTIFIER": "1",
}

# Set before spawning `headroom wrap <tool>`. Headroom re-invokes the tool by
# name, which resolves back to our own entry point on PATH — the sentinel lets
# that re-entrant call exec the real binary directly and break the recursion.
_WRAPPED_SENTINEL = "LLM_CLI_WRAPPED"


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "launch", help="pre-launch checks then run the tool in the foreground"
    )
    parser.add_argument("tool", choices=list(TOOL_NAMES))
    parser.add_argument(
        "arguments", nargs=argparse.REMAINDER,
        help="arguments forwarded to the tool (after --)",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    profile = tool_profile.resolve(args.tool)
    forwarded = _strip_separator(args.arguments)

    deps.export_local_bin_path()
    real_binary = _resolve_real_binary(profile.name)
    if real_binary is None:
        log.print_err(
            f"{profile.name} is not installed — run `activate {profile.name}` "
            "(or the bootstrap wizard) first."
        )
        return 127

    if os.environ.pop(_WRAPPED_SENTINEL, None):
        # Re-entrant call from `headroom wrap <tool>`: environment is already
        # configured, so hand straight over to the real binary.
        return platforms.current().exec_or_run([real_binary, *forwarded])

    prelaunch.run_steps(profile)
    _export_tool_env(profile)
    argv = _build_argv(profile, real_binary, forwarded)
    if _wraps_through_headroom(argv, real_binary):
        os.environ[_WRAPPED_SENTINEL] = "1"
    print(f"Starting {profile.name}...")
    return platforms.current().exec_or_run(argv)


def _wraps_through_headroom(argv: list[str], real_binary: str) -> bool:
    """True when argv routes through `headroom wrap` rather than launching the
    tool directly — the case that re-invokes our own entry point."""
    return bool(argv) and argv[0] != real_binary


def _resolve_real_binary(name: str) -> str | None:
    """Locates the real tool binary, skipping the directory of our own entry
    point so the wrapper never resolves to itself (infinite recursion)."""
    own_dir = _own_executable_dir()
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    kept = [
        directory
        for directory in path_dirs
        if directory and _resolve_dir(directory) != own_dir
    ]
    return shutil.which(name, path=os.pathsep.join(kept))


def _own_executable_dir() -> Path | None:
    try:
        return Path(sys.argv[0]).resolve().parent
    except (OSError, IndexError, ValueError):
        return None


def _resolve_dir(directory: str) -> Path | None:
    try:
        return Path(directory).resolve()
    except (OSError, ValueError):
        return None


def _export_tool_env(profile: ToolProfile) -> None:
    if profile.name == "claude":
        os.environ.update(_CLAUDE_TELEMETRY_OPT_OUT)
    if profile.name == "copilot":
        # Load the project-local .mcp.json in prompt mode too (interactive
        # mode loads it by default).
        os.environ["GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP"] = "true"


def _build_argv(profile: ToolProfile, binary: str, arguments: list[str]) -> list[str]:
    if profile.has_headroom and profile.headroom_mode == "launcher":
        return headroom.launch_argv(profile.name, binary, arguments)
    return [binary, *arguments]


def _strip_separator(arguments: list[str]) -> list[str]:
    if arguments and arguments[0] == "--":
        return arguments[1:]
    return arguments
