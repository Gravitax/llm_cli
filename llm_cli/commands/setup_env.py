"""setup-env — repairs the tool environment: install sync, global instructions,
tool-specific hooks, headroom wrap (port of setup_env.sh / setup_env.ps1).

Also migrates machines off the retired bash/PowerShell hook entries: legacy
PostToolUse commands are dropped and re-registered against run.py.
"""

from __future__ import annotations

import argparse
import json
import shutil

from llm_cli import platforms, tool_profile
from llm_cli.commands import setup_context, setup_headroom, setup_plugins, setup_rtk, sync
from llm_cli.services import log, settings_editor, slash_commands
from llm_cli.tool_profile import TOOL_NAMES, ToolProfile

_CACHE_HOOKS = (("Bash", "cache-refresh-git"), ("Write", "cache-refresh-write"))
_LEGACY_HOOK_NEEDLES = (
    "cache_refresh_on_git.sh", "cache_refresh_on_write.sh",
    "cache_refresh_on_git.ps1", "cache_refresh_on_write.ps1",
)


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-env", help="full environment repair (sync, instructions, hooks)"
    )
    parser.add_argument("--tool", required=True, choices=list(TOOL_NAMES))
    parser.add_argument(
        "--skip-global", action="store_true",
        help="skip the machine-global sync already run earlier in the same wizard",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    profile = tool_profile.resolve(args.tool)

    if not getattr(args, "skip_global", False):
        sync.run(args)
    setup_context.run(args)

    if profile.has_rtk_hook:
        _ensure_rtk_hook(profile)
    if profile.has_agent_hooks:
        _migrate_legacy_hooks(profile)
        _register_cache_hooks(profile)
        _ensure_cache_read_permission(profile)
    if profile.has_slash_commands:
        _install_slash_commands(profile)
    if profile.has_plugins:
        setup_plugins.run(argparse.Namespace(tool=profile.name))
    setup_headroom.run(
        argparse.Namespace(tool=profile.name, ensure=True, remove=False)
    )

    log.print_ok(f"{profile.name} environment ready.")
    return 0


def _install_slash_commands(profile: ToolProfile) -> None:
    """The commands directory is symlinked into every provider config home, so
    installing once here covers `claude`, `claude -glm` and `claude -copilot`."""
    written = slash_commands.install(profile.home)
    names = ", ".join(f"/{path.stem}" for path in written)
    log.print_ok(f"Slash commands ({names}) written to {profile.home / 'commands'}")


def _ensure_rtk_hook(profile: ToolProfile) -> None:
    """Reinstalls the RTK binary/hook when either went missing."""
    hook_present = settings_editor.contains(
        profile.settings_json, f"rtk hook {profile.name}"
    ) or settings_editor.contains(profile.settings_json, f"hook {profile.name}")
    if shutil.which("rtk") and hook_present:
        return
    setup_rtk.run(argparse.Namespace(remove=False))


def _register_cache_hooks(profile: ToolProfile) -> None:
    for matcher, hook_name in _CACHE_HOOKS:
        entry = platforms.current().hook_command("hook", hook_name)
        # json.dumps matches the command as it is escaped inside settings.json.
        if settings_editor.contains(profile.settings_json, json.dumps(entry["command"])):
            log.print_ok(f"PostToolUse {matcher} hook ({hook_name}) already registered.")
            continue
        # A same-name entry with a different command is stale (old command
        # format or moved interpreter) — replace it, never stack a second one.
        if settings_editor.remove_hooks(
            profile.settings_json, "PostToolUse", f"hook {hook_name}"
        ):
            log.print_ok(f"Stale PostToolUse {matcher} hook ({hook_name}) removed.")
        settings_editor.register_hook(profile.settings_json, "PostToolUse", matcher, entry)
        log.print_ok(
            f"PostToolUse {matcher} hook ({hook_name}) registered in {profile.settings_json}"
        )


def _migrate_legacy_hooks(profile: ToolProfile) -> None:
    for needle in _LEGACY_HOOK_NEEDLES:
        if settings_editor.remove_hooks(profile.settings_json, "PostToolUse", needle):
            log.print_ok(f"Legacy PostToolUse hook ({needle}) removed.")


def _ensure_cache_read_permission(profile: ToolProfile) -> None:
    """Allows reading the context cache without a permission prompt: the cache
    lives outside the project (~/.claude/projects/), which Claude Code treats
    as out-of-workspace and would otherwise prompt for on every session."""
    rule = f"Read(~/.{profile.name}/projects/**)"
    if settings_editor.ensure_permission_rule(profile.settings_json, rule):
        log.print_ok(f"Cache read permission ({rule}) registered in {profile.settings_json}")
