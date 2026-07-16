"""setup-deps — installs every missing runtime dependency of the layer
(port of setup_dependencies.sh / setup_dependencies.ps1).

Fully automatic (no prompts) — called by bootstrap before tool activation.
Failures are counted, reported and reflected in the exit code, but never
abort the run: independent dependencies still get their chance to install.
"""

from __future__ import annotations

import argparse

from llm_cli.services import deps, log
from llm_cli.tool_profile import TOOL_NAMES

_TOOL_PACKAGES = {
    "claude": ("@anthropic-ai/claude-code", "claude"),
    "copilot": ("@github/copilot", "copilot"),
    # opencode ships as the `opencode-ai` npm package (binary: `opencode`).
    # When already installed system-wide (curl/brew), ensure_npm_cli is a no-op.
    "opencode": ("opencode-ai", "opencode"),
}


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-deps", help="install every missing runtime dependency"
    )
    parser.add_argument(
        "tools", nargs="*", choices=list(TOOL_NAMES),
        help="agent CLIs to install on top of the shared dependencies",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    log.print_step("Checking & installing dependencies")
    installer = deps.installer()

    steps = [
        lambda: installer.ensure_system_tool("curl", "curl"),
        lambda: installer.ensure_system_tool("git", "Git.Git" if _is_windows() else "git"),
        installer.ensure_node,
        installer.ensure_uv,
        installer.ensure_rtk,
        installer.ensure_headroom,
    ]
    for tool in args.tools:
        package, binary = _TOOL_PACKAGES[tool]
        steps.append(lambda pkg=package, exe=binary: installer.ensure_npm_cli(pkg, exe))

    failures = sum(1 for step in steps if not step())
    if failures:
        log.print_err(f"{failures} dependency step(s) failed — see messages above.")
        return 1
    log.print_ok("All dependencies present.")
    return 0


def _is_windows() -> bool:
    from llm_cli import platforms

    return platforms.current().is_windows
