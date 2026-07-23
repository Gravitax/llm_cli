#!/usr/bin/env python3
"""install.py — one-command, cross-platform installer for llm_cli.

Replaces the retired bootstrap.sh / bootstrap.ps1 shims. Pure Python, so the
exact same entry point works on Linux, macOS and Windows:

    python install.py            # full install + interactive setup wizard
    python install.py --no-wizard  # install the package only

Steps:
  1. creates (once) the managed virtualenv in ~/.llm_cli/.venv, built from an
     interpreter recent enough for the package — the system `python3` is often
     older than the required version.
  2. `pip install .` inside that venv — installs the package and the
     `claude`/`copilot` console executables in the venv bin/Scripts directory
     (a real binary on Windows, an executable script on Unix).
  3. runs the interactive bootstrap wizard with the venv interpreter
     (dependencies, PATH activation block, tool activation, Atlassian/MCP,
     diagnostics); with --no-wizard only the PATH block is written.

The current terminal keeps its old PATH — open a new terminal (or restart the
shell) afterwards, exactly like any freshly installed CLI tool.

This file runs BEFORE the package is installed, so it cannot import llm_cli:
it carries a standalone copy of the crash guard (services/crash_guard.py) and
of the venv location (paths.venv_dir()).
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_INSTALL_ROOT = Path.home() / ".llm_cli"
_ERROR_LOG = _INSTALL_ROOT / "logs" / "llm_cli-error.log"

_VENV_DIR = _INSTALL_ROOT / ".venv"
_VENV_BIN = _VENV_DIR / ("Scripts" if os.name == "nt" else "bin")
_VENV_PYTHON = _VENV_BIN / ("python.exe" if os.name == "nt" else "python")

# Must stay in sync with requires-python in pyproject.toml.
_MIN_PYTHON = (3, 9)
# Newest first: the venv is built with the most recent interpreter available.
_PYTHON_CANDIDATES = (
    "python3.13", "python3.12", "python3.11", "python3.10", "python3.9", "python3", "python",
)


def _version_of(python: str | Path) -> tuple[int, int] | None:
    """Major/minor of an interpreter, or None when it cannot be queried."""
    code = "import sys; print(sys.version_info[0], sys.version_info[1])"
    try:
        out = subprocess.run(
            [str(python), "-c", code], capture_output=True, text=True, check=True
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return (int(out[0]), int(out[1])) if len(out) == 2 else None


def _base_pythons() -> list[str]:
    """Interpreters able to build the venv, newest first — this one when recent
    enough, then the suitable `pythonX.Y` on PATH (duplicates dropped)."""
    found: list[str] = []
    seen: set[str] = set()
    candidates = [shutil.which(name) for name in _PYTHON_CANDIDATES]
    if sys.version_info[:2] >= _MIN_PYTHON:
        candidates.insert(0, sys.executable)
    for candidate in candidates:
        if candidate is None:
            continue
        real = str(Path(candidate).resolve())
        if real in seen:
            continue
        seen.add(real)
        version = _version_of(candidate)
        if version and version >= _MIN_PYTHON:
            found.append(candidate)
    return found


def _create_venv() -> bool:
    """Builds the venv, falling back to the next interpreter when one is
    incomplete (a `pythonX.Y` without its matching venv/ensurepip module)."""
    _VENV_DIR.parent.mkdir(parents=True, exist_ok=True)
    for base in _base_pythons():
        print(f"[1/3] Creating the virtualenv in {_VENV_DIR} (from {base})...")
        if subprocess.run([base, "-m", "venv", str(_VENV_DIR)]).returncode == 0:
            return True
        shutil.rmtree(_VENV_DIR, ignore_errors=True)  # Half-built tree, never reused.
        print(f"Warning: {base} cannot build a virtualenv — trying another one.")
    print(
        "Error: virtualenv creation failed with every candidate interpreter — "
        "see the output above (on Debian/Ubuntu the `python3-venv` package may "
        "be missing).",
        file=sys.stderr,
    )
    return False


def _ensure_venv() -> bool:
    """Creates ~/.llm_cli/.venv when missing; keeps a usable existing one."""
    existing = _version_of(_VENV_PYTHON) if _VENV_PYTHON.exists() else None
    if existing and existing >= _MIN_PYTHON:
        print(f"[1/3] Using the existing virtualenv in {_VENV_DIR}...")
        return True
    if existing:
        required = ".".join(str(part) for part in _MIN_PYTHON)
        print(
            f"Error: {_VENV_DIR} runs Python {existing[0]}.{existing[1]}, "
            f"but {required}+ is required. Delete that directory and re-run "
            "this installer.",
            file=sys.stderr,
        )
        return False
    return _create_venv()


def _pip_install() -> int:
    print("[2/3] Installing the llm_cli package and entry points (venv)...")
    cmd = [str(_VENV_PYTHON), "-m", "pip", "install", "--upgrade", str(_REPO_ROOT)]
    return subprocess.run(cmd).returncode


def _run_core(*cli_args: str) -> int:
    """Invokes the freshly installed core via run.py so PATH is irrelevant."""
    cmd = [str(_VENV_PYTHON), str(_REPO_ROOT / "run.py"), *cli_args]
    return subprocess.run(cmd).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Install llm_cli (cross-platform).")
    parser.add_argument(
        "--no-wizard", action="store_true", help="install the package only, skip the wizard"
    )
    args = parser.parse_args()

    if not _ensure_venv():
        return 1

    if _pip_install() != 0:
        print("Error: pip install failed — see the output above.", file=sys.stderr)
        return 1

    if args.no_wizard:
        print("[3/3] Registering the PATH activation block (wizard skipped)...")
        if _run_core("setup-shell-wrapper") != 0:
            return 1
    else:
        print("[3/3] Launching the setup wizard...")
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
