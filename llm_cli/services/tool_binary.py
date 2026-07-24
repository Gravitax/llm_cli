"""tool_binary — locates the real tool executable, never our own wrapper.

pip installs `claude`/`copilot` console entry points that share the tool's name
(see llm_cli.entry). A plain `shutil.which(name)` therefore resolves to the
wrapper whenever the managed venv comes first on PATH, and every call made
through it replays the whole pre-launch pipeline (context re-index, proxy start,
hook repair) instead of reaching the tool. Resolution here drops the directories
that hold our wrappers so callers always get the genuine binary.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from llm_cli import platforms


def resolve(name: str) -> str | None:
    """Path to the real `name` binary, or None when it is not installed."""
    excluded = _wrapper_dirs()
    kept = [
        directory
        for directory in os.environ.get("PATH", "").split(os.pathsep)
        if directory and _resolve_dir(directory) not in excluded
    ]
    return shutil.which(name, path=os.pathsep.join(kept))


def _wrapper_dirs() -> set[Path]:
    """Directories that may hold a same-named wrapper of ours.

    The managed venv is the authoritative one and holds whatever the caller was
    started from (`run.py`, a console entry point, an import). sys.argv[0] adds
    the case of a copy installed into another environment.
    """
    candidates = (
        _resolve_dir(str(platforms.current().entry_points_dir())),
        _own_executable_dir(),
    )
    return {directory for directory in candidates if directory is not None}


def _own_executable_dir() -> Path | None:
    try:
        return Path(sys.argv[0]).resolve().parent
    except (OSError, IndexError, ValueError):
        return None


def _resolve_dir(directory: str) -> Path | None:
    try:
        return Path(directory).resolve()
    except (OSError, ValueError):
        return None
