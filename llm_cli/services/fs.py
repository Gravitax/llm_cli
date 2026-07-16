"""Atomic file writes with explicit encoding contracts.

The single place allowed to write text files that other programs parse
(settings.json, shell profiles, git hooks) — callers pick newline/BOM and this
module guarantees tmp+replace atomicity and optional .bak backups
(port of lib_settings.ps1 Save-SettingsObject and the mktemp && mv idiom).
"""

from __future__ import annotations

import codecs
import shutil
from pathlib import Path


def read_text(path: Path) -> str:
    """Reads UTF-8 text, transparently accepting a BOM."""
    return path.read_text(encoding="utf-8-sig")


def write_text_atomic(
    path: Path,
    text: str,
    *,
    newline: str = "\n",
    bom: bool = False,
    backup: bool = False,
) -> None:
    """Writes text atomically (tmp + replace in the same directory)."""
    normalized = text.replace("\r\n", "\n")
    data = normalized.replace("\n", newline).encode("utf-8")
    if bom:
        data = codecs.BOM_UTF8 + data

    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        shutil.copy2(path, Path(str(path) + ".bak"))

    tmp = Path(str(path) + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
