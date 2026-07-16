"""setup-context — rewrites the global instructions file for a tool."""

from __future__ import annotations

import argparse

from llm_cli import tool_profile
from llm_cli.services import fs, instructions, log
from llm_cli.tool_profile import TOOL_NAMES


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-context",
        help="rewrite the tool's global instructions file (always authoritative)",
    )
    parser.add_argument("--tool", required=True, choices=list(TOOL_NAMES))
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    profile = tool_profile.resolve(args.tool)
    path = instructions.write_global_instructions(profile)
    line_count = fs.read_text(path).count("\n")
    log.print_ok(f"{path} rewritten ({line_count} lines).")
    return 0
