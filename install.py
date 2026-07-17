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
  2. runs the interactive bootstrap wizard (dependencies, PATH activation
     block, tool activation, Atlassian/MCP, diagnostics); with --no-wizard
     only the PATH block is written.

The current terminal keeps its old PATH — open a new terminal (or restart the
shell) afterwards, exactly like any freshly installed CLI tool.

This file runs BEFORE the package is installed, so it cannot import llm_cli:
it carries a standalone copy of the crash guard (services/crash_guard.py).
"""

from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
import traceback
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_ERROR_LOG = Path.home() / ".llm_cli" / "logs" / "llm_cli-error.log"


def _pip_install() -> int:
    print("[1/2] Installing the llm_cli package and entry points (pip --user)...")
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

    if args.no_wizard:
        print("[2/2] Registering the PATH activation block (wizard skipped)...")
        if _run_core("setup-shell-wrapper") != 0:
            return 1
    else:
        print("[2/2] Launching the setup wizard...")
        if _run_core("bootstrap") != 0:
            print(
                "Setup wizard failed — fix the issue above, then re-run: "
                "python install.py",
                file=sys.stderr,
            )
            return 1

    print(
        "\nDone. Open a NEW terminal (or restart your shell) so `claude` and "
        "`copilot` are on PATH, then run them from any project directory."
    )
    return 0


def _guarded(entry) -> int:
    """Standalone crash guard (llm_cli is not importable yet): the traceback
    always lands on screen AND in a log file, and an interactive Windows
    console pauses instead of closing on the error."""
    try:
        return entry()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception:  # noqa: BLE001 — last-resort guard, must catch everything.
        details = traceback.format_exc()
        print(details, file=sys.stderr)
        log_file = _persist_crash(details)
        if log_file:
            print(f"Crash details saved to {log_file}", file=sys.stderr)
        _pause_interactive_windows_console()
        return 1


def _persist_crash(details: str) -> Path | None:
    try:
        _ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(_ERROR_LOG, "a", encoding="utf-8") as handle:
            handle.write(f"\n--- {stamp} · argv: {sys.argv} ---\n{details}")
    except OSError:
        return None  # Logging must never mask the original crash.
    return _ERROR_LOG


def _pause_interactive_windows_console() -> None:
    if os.name != "nt" or not sys.stdin.isatty():
        return
    try:
        input("Press Enter to exit...")
    except (EOFError, OSError):
        pass


if __name__ == "__main__":
    sys.exit(_guarded(main))
