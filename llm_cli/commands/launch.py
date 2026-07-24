"""launch — runs the pre-launch steps then hands the foreground to the tool.

The `claude`/`copilot` console entry points delegate here so all routing logic
(headroom wrap for copilot, telemetry opt-out, PATH fixes) lives in one tested
place. Since our entry point shares the tool's name, the real binary comes from
the shared `tool_binary` resolver — otherwise the entry point would invoke
itself in an infinite loop.
"""

from __future__ import annotations

import argparse
import os

from llm_cli import platforms, tool_profile
from llm_cli.commands import (
    copilot_models,
    prelaunch,
    provider_models,
    setup_headroom,
)
from llm_cli.services import (
    claude_provider,
    copilot_proxy,
    deps,
    glm,
    headroom,
    log,
    tool_binary,
)
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

# Wrapper-only flags, consumed here and never forwarded to the tool.
_MODELS_FLAG = "--models"
_HEADROOM_FLAGS = ("-u", "--headroom")


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
    if _MODELS_FLAG in forwarded:
        # Wrapper-only flag: print the catalog instead of launching the tool.
        return _list_models(profile, args)
    forwarded, toggle_result = _handle_provider_toggle(profile, forwarded)
    if toggle_result is not None:
        return toggle_result
    forwarded, headroom_result = _handle_headroom_toggle(profile, forwarded)
    if headroom_result is not None:
        return headroom_result

    deps.export_local_bin_path()
    real_binary = tool_binary.resolve(profile.name)
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
    if _uses_provider(profile, claude_provider.GLM):
        if not glm.require_api_key():
            return 1
        forwarded = _apply_glm_routing(profile, forwarded)
    elif _uses_provider(profile, claude_provider.COPILOT):
        slots = copilot_proxy.prepare()
        if slots is None:
            return 1
        print(
            f"Provider: GitHub Copilot · Model: {slots.main} "
            f"(/model also offers {slots.opus} and {slots.small})"
        )
        forwarded = copilot_proxy.with_default_model(forwarded, slots.main)
    elif profile.name == "claude":
        claude_provider.reset_env()
    argv = _build_argv(profile, real_binary, forwarded)
    if _wraps_through_headroom(argv, real_binary):
        os.environ[_WRAPPED_SENTINEL] = "1"
        _print_copilot_model_hint(profile, forwarded)
    print(f"Starting {profile.name}...")
    return platforms.current().exec_or_run(argv)


def _list_models(profile: ToolProfile, args: argparse.Namespace) -> int:
    """`--models` catalog: the copilot CLI has a single provider, `claude`
    follows whichever one its toggle currently points at."""
    if profile.name == "copilot":
        return copilot_models.run(args)
    return provider_models.run(args)


def _handle_provider_toggle(
    profile: ToolProfile, arguments: list[str]
) -> tuple[list[str], int | None]:
    """Handles the wrapper-only standalone Claude provider switches."""
    if profile.name != "claude":
        return arguments, None
    flags = {
        "-glm": claude_provider.GLM,
        "--glm": claude_provider.GLM,
        "-copilot": claude_provider.COPILOT,
        "--copilot": claude_provider.COPILOT,
    }
    selected = {flags[arg] for arg in arguments if arg in flags}
    kept = [arg for arg in arguments if arg not in flags]
    if not selected:
        return arguments, None
    if len(selected) > 1:
        log.print_err("Use only one provider switch: -glm or -copilot.")
        return kept, 2
    provider = selected.pop()
    if provider == claude_provider.GLM:
        glm.toggle()
    else:
        copilot_proxy.toggle()
    return kept, 0


def _handle_headroom_toggle(
    profile: ToolProfile, arguments: list[str]
) -> tuple[list[str], int | None]:
    """Handles the wrapper-only `-u` switch: flips the persisted headroom state
    and applies it, so the routing in settings.json follows the toggle instead
    of drifting out of sync with it."""
    kept = [arg for arg in arguments if arg not in _HEADROOM_FLAGS]
    if len(kept) == len(arguments):
        return arguments, None
    enabled = headroom.toggle()
    return kept, setup_headroom.run(
        argparse.Namespace(tool=profile.name, ensure=True, remove=not enabled)
    )


def _uses_provider(profile: ToolProfile, provider: str) -> bool:
    return profile.name == "claude" and claude_provider.is_active(provider)


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
