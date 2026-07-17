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
from llm_cli.commands import copilot_models, prelaunch
from llm_cli.services import deps, glm, headroom, log
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
    if profile.name == "copilot" and "--models" in forwarded:
        # Wrapper-only flag: print the catalog instead of launching the tool.
        return copilot_models.run(args)
    forwarded = _handle_glm_toggle(profile, forwarded)

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
    if _uses_glm(profile):
        if not glm.require_api_key():
            return 1
        forwarded = _apply_glm_routing(profile, forwarded)
    argv = _build_argv(profile, real_binary, forwarded)
    if _wraps_through_headroom(argv, real_binary):
        os.environ[_WRAPPED_SENTINEL] = "1"
        _print_copilot_model_hint(profile, forwarded)
    print(f"Starting {profile.name}...")
    return platforms.current().exec_or_run(argv)


def _handle_glm_toggle(profile: ToolProfile, arguments: list[str]) -> list[str]:
    """Strips the `-glm`/`--glm` flag (claude only) and flips the persisted
    provider when present. The flag is ours, never forwarded to the tool."""
    if profile.name != "claude":
        return arguments
    kept = [arg for arg in arguments if arg not in ("-glm", "--glm")]
    if len(kept) != len(arguments):
        glm.toggle()
    return kept


def _uses_glm(profile: ToolProfile) -> bool:
    return profile.name == "claude" and glm.is_active()


def _apply_glm_routing(profile: ToolProfile, forwarded: list[str]) -> list[str]:
    """Routes this launch to the z.ai endpoint. The provider state is durable,
    so every GLM launch announces itself to avoid billing surprises.
    The process env exported here wins over the settings.json proxy routing
    (verified: claude prefers the process value of ANTHROPIC_BASE_URL)."""
    glm.export_env()
    print("Provider: GLM (z.ai)")
    return glm.with_default_model(forwarded)


def _print_copilot_model_hint(profile: ToolProfile, forwarded: list[str]) -> None:
    """Under the headroom wrap copilot runs on a custom provider and its
    in-session /model list is empty — the model is pinned at launch. Make the
    pin and the escape hatches visible whenever the default was injected."""
    if profile.name != "copilot" or not headroom.uses_default_model(forwarded):
        return
    print(
        f"Model: {headroom.default_copilot_model()} "
        "(pinned at launch — wrap mode has no /model list)."
    )
    print(
        "  List models: copilot --models · switch: copilot --model <id> · "
        "default: COPILOT_DEFAULT_MODEL in the llm_cli config"
    )


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
    if profile.headroom_mode == "launcher":
        return headroom.launch_argv(profile.name, binary, arguments)
    return [binary, *arguments]


def _strip_separator(arguments: list[str]) -> list[str]:
    if arguments and arguments[0] == "--":
        return arguments[1:]
    return arguments
