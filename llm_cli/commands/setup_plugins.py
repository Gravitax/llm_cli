"""setup-plugins — installs the Claude Code plugins declared in plugins.yaml.

Registers each marketplace and installs each plugin through the official
`claude plugin` CLI. Idempotent: entries already present are skipped. This only
covers real marketplace plugins/skills; headroom and RTK keep their own setup.
"""

from __future__ import annotations

import argparse

from llm_cli import tool_profile
from llm_cli.services import log, plugin_manager


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-plugins",
        help="install Claude Code plugins and skills from plugins.yaml",
    )
    parser.add_argument("--tool", default="claude", choices=list(tool_profile.TOOL_NAMES))
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    profile = tool_profile.resolve(getattr(args, "tool", "claude"))
    print("Installing Claude Code plugins and skills from plugins.yaml...")
    plugins_ok = plugin_manager.sync_plugins(profile.settings_json)
    skills_ok = plugin_manager.sync_skills(profile.skills_dir)
    if plugins_ok and skills_ok:
        log.print_ok("Plugins ready. Restart Claude Code (or /reload-plugins) to activate.")
        return 0
    log.print_warn("Plugin setup incomplete — see warnings above.")
    return 1
