"""Console output helpers (port of lib_log.sh / lib_log.ps1).

print_* for setup commands, Checker for diagnostics (with pass/fail counters).
"""

from __future__ import annotations

import os
import sys

_GREEN = "\033[0;32m"
_RED = "\033[0;31m"
_YELLOW = "\033[0;33m"
_BLUE = "\033[0;34m"
_RED_BOLD = "\033[1;31m"
_RESET = "\033[0m"

_ansi_ready = False


def _ansi(code: str) -> str:
    """Returns the ANSI sequence when the terminal can render it, else ''."""
    global _ansi_ready
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return ""
    if os.name == "nt" and not _ansi_ready:
        os.system("")  # Enables VT processing on the legacy Windows console.
        _ansi_ready = True
    return code


def print_step(message: str) -> None:
    """Prints a section header."""
    print(f"\n==> {message}")


def print_ok(message: str) -> None:
    print(f"    [OK] {message}")


def print_err(message: str) -> None:
    print(f"    [ERROR] {message}")


def print_warn(message: str) -> None:
    print(f"    [WARN] {message}")


def print_info(message: str) -> None:
    print(f"    {message}")


def red_banner(lines: list[str]) -> None:
    """Highly visible warning block (login hints, broken wrap...)."""
    top, bottom = _banner_borders()
    print(_ansi(_RED_BOLD), end="")
    print(top)
    for line in lines:
        print(f"    {line}")
    print(bottom)
    print(_ansi(_RESET), end="")


def _banner_borders() -> tuple[str, str]:
    """Box-drawing borders, degraded to ASCII when the console encoding
    (e.g. cp1252 on legacy Windows) cannot render them."""
    top = "  ╔" + "═" * 68 + "╗"
    bottom = "  ╚" + "═" * 68 + "╝"
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        top.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        ascii_border = "  " + "=" * 70
        return ascii_border, ascii_border
    return top, bottom


class Checker:
    """Diagnostic reporter with pass/fail counters (port of check_* helpers)."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def ok(self, message: str) -> None:
        self._tagged(_GREEN, "[OK]  ", message)
        self.passed += 1

    def fail(self, message: str) -> None:
        self._tagged(_RED, "[FAIL]", message)
        self.failed += 1

    def warn(self, message: str) -> None:
        self._tagged(_YELLOW, "[WARN]", message)

    def info(self, message: str) -> None:
        self._tagged(_BLUE, "[INFO]", message)

    @staticmethod
    def _tagged(color: str, tag: str, message: str) -> None:
        print(f"  {_ansi(color)}{tag}{_ansi(_RESET)} {message}")
