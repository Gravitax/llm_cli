"""tool_binary — locates the real tool executable, never our own wrapper.

pip installs `claude`/`copilot` console entry points that share the tool's name
(see llm_cli.entry). A plain `shutil.which(name)` therefore resolves to the
wrapper whenever a directory holding one comes first on PATH, and every call
made through it replays the whole pre-launch pipeline (context re-index, proxy
start, hook repair) instead of reaching the tool — an expensive, effectively
infinite recursion when it happens during our own launch.

Resolution here drops the directories known to hold our wrappers, and — as a
self-correcting fallback — keeps skipping any resolved candidate that still
turns out to be one of ours, so a duplicate install under another interpreter
(a stray `pip install` beside the managed venv) can never send us into that
loop. Only a binary whose directory carries no `llm_cli` marker is returned;
when every candidate is a wrapper the result is None and callers degrade
cleanly instead of recursing.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from llm_cli import platforms

# Our pip distribution installs `claude`, `copilot` AND `llm_cli` side by side.
# The real Claude Code / Copilot CLIs never ship an `llm_cli` executable, so a
# directory that holds one is unmistakably ours — the reliable marker for
# recognising every copy of our wrapper, wherever it was installed.
_MARKER_NAMES = ("llm_cli", "llm_cli.exe")


def resolve(name: str) -> str | None:
    """Path to the real `name` binary, or None when it is not installed.

    Directories known to hold our wrapper are excluded up front; on top of that,
    any candidate that still resolves into one of our directories is skipped and
    the search retried. The loop only ever returns a binary whose directory
    carries no `llm_cli` marker, or None when every candidate is a wrapper.
    """
    excluded = _wrapper_dirs()
    while True:
        kept = [
            directory
            for directory in os.environ.get("PATH", "").split(os.pathsep)
            if directory and _resolve_dir(directory) not in excluded
        ]
        found = shutil.which(name, path=os.pathsep.join(kept))
        if found is None:
            return None
        found_dir = _resolve_dir(str(Path(found).parent))
        if found_dir is not None and _has_marker(found_dir):
            # A wrapper slipped past the up-front exclusion — drop its directory
            # and try again rather than hand back a self-referential binary.
            excluded.add(found_dir)
            continue
        return found


def _has_marker(directory: Path) -> bool:
    """True when the directory carries our `llm_cli` console script."""
    return any((directory / marker).exists() for marker in _MARKER_NAMES)


def _wrapper_dirs() -> set[Path]:
    """Directories that may hold a same-named wrapper of ours.

    The managed venv (entry_points_dir) and the directory we were started from
    (sys.argv[0]) are the obvious two; every PATH directory carrying our
    `llm_cli` marker is added so a second install under another interpreter is
    excluded from the first pass as well.
    """
    candidates = {
        _resolve_dir(str(platforms.current().entry_points_dir())),
        _own_executable_dir(),
    }
    candidates |= _marker_dirs()
    return {directory for directory in candidates if directory is not None}


def _marker_dirs() -> set[Path]:
    """PATH directories that contain our `llm_cli` console script."""
    found: set[Path] = set()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        resolved = _resolve_dir(directory) if directory else None
        if resolved is not None and _has_marker(resolved):
            found.add(resolved)
    return found


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
