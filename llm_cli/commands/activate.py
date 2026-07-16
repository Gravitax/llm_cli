"""activate — installs and activates a tool's optimization layer.

Ensures the tool's prerequisites (Node + the agent CLI), installs the hooks and
headroom wrap, and registers the PATH block so the pip-installed `claude`/
`copilot` wrappers resolve in new shells.
"""

from __future__ import annotations

import argparse

from llm_cli import tool_profile
from llm_cli.commands import setup_env, setup_shell_wrapper
from llm_cli.services import deps, headroom, log
from llm_cli.tool_profile import TOOL_NAMES, ToolProfile

_TOOL_PACKAGES = {
    "claude": "@anthropic-ai/claude-code",
    "copilot": "@github/copilot",
    # Already present system-wide → ensure_npm_cli short-circuits; otherwise it
    # installs the npm distribution (opencode-ai), same binary name.
    "opencode": "opencode-ai",
}


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "activate", help="install + activate a tool's optimization layer"
    )
    parser.add_argument("tool", choices=list(TOOL_NAMES))
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    profile = tool_profile.resolve(args.tool)
    if not _ensure_prerequisites(profile):
        return 1
    setup_env.run(args)
    setup_shell_wrapper.run(args)
    _warn_when_compression_idle(profile)
    log.print_ok(f"Ready. Run: {profile.name}")
    return 0


def _ensure_prerequisites(profile: ToolProfile) -> bool:
    """Node + the agent CLI itself (port of setup_prerequisites.sh)."""
    installer = deps.installer()
    if not installer.ensure_node():
        return False
    return installer.ensure_npm_cli(_TOOL_PACKAGES[profile.name], profile.name)


def _warn_when_compression_idle(profile: ToolProfile) -> None:
    """Surfaces the exact OAuth commands whenever compression would stay idle."""
    if profile.headroom_mode != "launcher" or not headroom.is_installed():
        return
    headroom.export_ghe_env()
    if headroom.copilot_mode() is None:
        headroom.print_login_warning()
