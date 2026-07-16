#!/usr/bin/env python3
"""install.py — one-command, cross-platform installer for llm_cli.

Replaces the retired bootstrap.sh / bootstrap.ps1 shims. Pure Python, so the
exact same entry point works on Linux, macOS and Windows:

    python install.py            # full install + interactive setup wizard
    python install.py --no-wizard  # install the package only

Steps:
  1. `pip install --user .` — installs the package and the `claude`/`copilot`
     console executables onto PATH (a real binary on Windows, an executable
     script on Unix — no shell shim needed).
  2. writes the PATH activation block into the shell profiles so the entry
     points resolve in new terminals.
  3. runs the interactive bootstrap wizard (dependencies, tool activation,
     Atlassian/MCP, diagnostics) unless --no-wizard is given.

The current terminal keeps its old PATH — open a new terminal (or restart the
shell) afterwards, exactly like any freshly installed CLI tool.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent


def _pip_install() -> int:
    print("[1/3] Installing the llm_cli package and entry points (pip --user)...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--user", "--upgrade", str(_REPO_ROOT)]
    )
    return result.returncode


def _run_core(*cli_args: str) -> int:
    """Invokes the freshly installed core via run.py so PATH is irrelevant."""
    return subprocess.run([sys.executable, str(_REPO_ROOT / "run.py"), *cli_args]).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Install llm_cli (cross-platform).")
    parser.add_argument(
        "--no-wizard", action="store_true", help="install the package only, skip the wizard"
    )
    args = parser.parse_args()

    if _pip_install() != 0:
        print("Error: pip install failed — see the output above.", file=sys.stderr)
        return 1

    print("[2/3] Registering the PATH activation block in your shell profiles...")
    _run_core("setup-shell-wrapper")

    if args.no_wizard:
        print("[3/3] Skipped the wizard (--no-wizard).")
    else:
        print("[3/3] Launching the setup wizard...")
        _run_core("bootstrap")

    print(
        "\nDone. Open a NEW terminal (or restart your shell) so `claude` and "
        "`copilot` are on PATH, then run them from any project directory."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
