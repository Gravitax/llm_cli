"""prelaunch — everything that must happen right before a tool launch:
RTK hook repair, context-cache staleness check/rebuild, headroom proxy start
(port of the lib_cache.sh wrapper body + tool_hooks.sh).

Contract: never blocks the launch — every failure degrades to a warning.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from llm_cli import tool_profile
from llm_cli.services import (
    cache,
    claude_provider,
    git,
    headroom,
    log,
    settings_editor,
)
from llm_cli.tool_profile import ToolProfile


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "prelaunch", help="cache refresh + rtk repair + headroom proxy (never fails)"
    )
    parser.add_argument("tool", choices=list(tool_profile.TOOL_NAMES))
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    run_steps(tool_profile.resolve(args.tool))
    return 0


def run_steps(profile: ToolProfile) -> None:
    """Executes each pre-launch step independently; one failure never hides
    the others and never blocks the tool."""
    for step in (_repair_rtk_hook, _refresh_cache, _ensure_proxy):
        try:
            step(profile)
        except Exception as error:  # noqa: BLE001 — never block the launch.
            log.print_warn(f"pre-launch step skipped: {error}")


def _repair_rtk_hook(profile: ToolProfile) -> None:
    """Repairs the RTK PreToolUse hook if it disappeared from settings.json."""
    if not profile.has_rtk_hook:
        return
    if settings_editor.contains(profile.settings_json, f"hook {profile.name}"):
        return
    print("RTK hook missing — reinstalling...")
    from llm_cli.commands import setup_env

    setup_env.run(argparse.Namespace(tool=profile.name))


def _refresh_cache(profile: ToolProfile) -> None:
    # project — git root, indexing scope and cache hash key.
    # launch_dir — where the tool was invoked; receives the local
    # instructions entry and the ignore file.
    project = git.toplevel()
    launch_dir = Path.cwd()
    cache_file = cache.cache_file_for(profile, project)
    if cache.is_stale(cache_file, project):
        print("Updating context cache...")
        from llm_cli.commands import setup_context_cache

        setup_context_cache.generate_index(profile, project, launch_dir)
    else:
        print(
            f"Context cache up to date (< {cache.max_age_minutes()}min, no source changes)."
        )


def _ensure_proxy(profile: ToolProfile) -> None:
    if (
        profile.name == "claude"
        and claude_provider.active() != claude_provider.ANTHROPIC
    ):
        return
    # Launcher mode routes at launch time (`headroom wrap`) — no proxy needed.
    if profile.headroom_mode == "settings":
        headroom.ensure_proxy(profile)
