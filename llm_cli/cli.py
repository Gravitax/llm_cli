"""Argument parsing and dispatch — no business logic lives here."""

from __future__ import annotations

import argparse

from llm_cli import __version__
from llm_cli.commands import (
    activate,
    bootstrap,
    check,
    git_clone,
    hooks,
    launch,
    prelaunch,
    setup_atlassian,
    setup_context,
    setup_context_cache,
    setup_deps,
    setup_env,
    setup_git_hooks,
    setup_headroom,
    setup_mcp,
    setup_rtk,
    setup_shell_wrapper,
    sync,
)

_COMMAND_MODULES = (
    activate,
    bootstrap,
    check,
    git_clone,
    hooks,
    launch,
    prelaunch,
    setup_atlassian,
    setup_context,
    setup_context_cache,
    setup_deps,
    setup_env,
    setup_git_hooks,
    setup_headroom,
    setup_mcp,
    setup_rtk,
    setup_shell_wrapper,
    sync,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm_cli",
        description="Token-optimization layer for Claude Code and Copilot CLI.",
    )
    parser.add_argument("--version", action="version", version=f"llm_cli {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in _COMMAND_MODULES:
        module.configure(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
