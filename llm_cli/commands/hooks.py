"""hook — entry points invoked by Claude Code (PostToolUse) and by git hooks
(port of cache_refresh_on_git.sh, cache_refresh_on_write.sh, git_hook_refresh.ps1).

Contract: drain stdin fully before any work (Claude Code pipes the full tool
JSON; not reading it can break the pipe and abort the hook on its side), never
let an error surface — a hook failure must not disturb the agent session.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from llm_cli import tool_profile
from llm_cli.commands import setup_context_cache
from llm_cli.services import git
from llm_cli.tool_profile import TOOL_NAMES

_STRUCTURAL_GIT = re.compile(r"\bgit (clone|checkout|switch|merge|pull|rebase)\b")


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "hook", help="agent/git hook entry points (never fail)"
    )
    actions = parser.add_subparsers(dest="hook_action", required=True)

    git_hook = actions.add_parser(
        "cache-refresh-git", help="PostToolUse Bash: refresh after structural git"
    )
    git_hook.add_argument("--tool", default="claude", choices=list(TOOL_NAMES))
    git_hook.set_defaults(func=_run_cache_refresh_git)

    write_hook = actions.add_parser(
        "cache-refresh-write", help="PostToolUse Write: refresh after file creation"
    )
    write_hook.add_argument("--tool", default="claude", choices=list(TOOL_NAMES))
    write_hook.set_defaults(func=_run_cache_refresh_write)

    git_refresh = actions.add_parser(
        "git-refresh", help="git post-merge/post-checkout: refresh every tool cache"
    )
    git_refresh.add_argument("project_dir", nargs="?", default=".")
    git_refresh.set_defaults(func=_run_git_refresh)


def _run_cache_refresh_git(args: argparse.Namespace) -> int:
    try:
        command = _read_stdin_tool_command()
        if not _STRUCTURAL_GIT.search(command):
            return 0
        profile = tool_profile.resolve(args.tool)
        setup_context_cache.refresh_if_indexed(profile, git.toplevel())
    except Exception:  # noqa: BLE001 — hooks must never surface failures.
        pass
    return 0


def _run_cache_refresh_write(args: argparse.Namespace) -> int:
    try:
        _drain_stdin()
        # Any new file is a structural change worth indexing — no filter applied.
        profile = tool_profile.resolve(args.tool)
        setup_context_cache.refresh_if_indexed(profile, git.toplevel())
    except Exception:  # noqa: BLE001 — hooks must never surface failures.
        pass
    return 0


def _run_git_refresh(args: argparse.Namespace) -> int:
    try:
        project = git.toplevel(Path(args.project_dir))
        for profile in tool_profile.ALL_PROFILES:
            setup_context_cache.refresh_if_indexed(profile, project)
    except Exception:  # noqa: BLE001 — hooks must never surface failures.
        pass
    return 0


def _drain_stdin() -> bytes:
    if sys.stdin is None or sys.stdin.closed:
        return b""
    return sys.stdin.buffer.read()


def _read_stdin_tool_command() -> str:
    raw = _drain_stdin()
    try:
        payload = json.loads(raw.decode("utf-8", errors="ignore") or "{}")
    except json.JSONDecodeError:
        return ""
    return payload.get("tool_input", {}).get("command", "")
