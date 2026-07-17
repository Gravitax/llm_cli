"""Top-level crash guard shared by every llm_cli entry point.

On Windows a crash can close the console before anyone reads the traceback
(cmd.exe windows opened for `python install.py` disappear on exit). Funneling
every entry point through guarded_main guarantees the traceback also lands in
a persistent log file, and pauses an interactive Windows console so the window
survives long enough to be read. install.py carries a standalone copy of this
guard because it runs before the package is installed.
"""

from __future__ import annotations

import datetime
import os
import sys
import traceback
from pathlib import Path
from typing import Callable

from llm_cli import paths

ERROR_LOG_NAME = "llm_cli-error.log"


def error_log_path() -> Path:
    return paths.logs_dir() / ERROR_LOG_NAME


def guarded_main(entry: Callable[[], int]) -> int:
    """Runs an entry point; no exception ever escapes without a readable trace."""
    try:
        return entry()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except EOFError:
        print(
            "Interactive input unavailable — run this command from a real terminal.",
            file=sys.stderr,
        )
        return 1
    except Exception:  # noqa: BLE001 — last-resort guard, must catch everything.
        return _report_crash()


def _report_crash() -> int:
    details = traceback.format_exc()
    print(details, file=sys.stderr)
    log_file = _persist(details)
    if log_file:
        print(f"Crash details saved to {log_file}", file=sys.stderr)
    _pause_interactive_windows_console()
    return 1


def _persist(details: str) -> Path | None:
    log_file = error_log_path()
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(f"\n--- {stamp} · argv: {sys.argv} ---\n{details}")
    except OSError:
        return None  # Logging must never mask the original crash.
    return log_file


def _pause_interactive_windows_console() -> None:
    """cmd.exe/PowerShell windows opened for a script close on exit — hold the
    window open so the error above stays readable."""
    if os.name != "nt" or not sys.stdin.isatty():
        return
    try:
        input("Press Enter to exit...")
    except (EOFError, OSError):
        pass
