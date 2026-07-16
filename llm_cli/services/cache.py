"""Project context-cache location and staleness (port of lib_cache.sh / lib_cache.ps1).

Hash contract: first 8 hex chars of md5(str(Path(project).resolve())). This is
THE only hash implementation — wrapper, hooks and indexer all agree on the key.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from llm_cli.tool_profile import ToolProfile

# The mtime scan catches real changes; the TTL is only a safety net, so a long
# default avoids useless rebuilds. Override with: export CACHE_MAX_AGE_MIN=10
DEFAULT_MAX_AGE_MIN = 60
# Mirrors the bash `find -maxdepth 6` scan depth.
_SCAN_MAX_DEPTH = 6
_SCAN_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}


def max_age_minutes() -> int:
    return int(os.environ.get("CACHE_MAX_AGE_MIN", DEFAULT_MAX_AGE_MIN))


def project_hash(project_path: Path) -> str:
    return hashlib.md5(
        str(Path(project_path).resolve()).encode()
    ).hexdigest()[:8]


def cache_file_for(profile: ToolProfile, project_path: Path) -> Path:
    return profile.projects_dir / project_hash(project_path) / "context_cache.md"


def is_stale(cache_file: Path, project_dir: Path) -> bool:
    """True when the cache is missing, past its TTL, or older than any source file."""
    if not cache_file.is_file():
        return True

    cache_mtime = cache_file.stat().st_mtime
    age_min = (time.time() - cache_mtime) / 60
    if age_min >= max_age_minutes():
        return True

    return _has_newer_file(project_dir, cache_mtime)


def _has_newer_file(project_dir: Path, reference_mtime: float) -> bool:
    """Bounded walk looking for one source file newer than the cache.

    Files only: directory mtimes bump on any child creation/removal (even
    ignored files like .claudeignore), which would flag the cache stale on
    every launch.
    """
    root_depth = len(Path(project_dir).parts)
    for current, dirnames, filenames in os.walk(project_dir):
        depth = len(Path(current).parts) - root_depth
        if depth >= _SCAN_MAX_DEPTH:
            dirnames.clear()
            continue
        dirnames[:] = [
            d for d in dirnames if d not in _SCAN_SKIP_DIRS and not d.startswith(".")
        ]
        for name in filenames:
            if name.startswith("."):
                continue
            try:
                if os.stat(os.path.join(current, name)).st_mtime > reference_mtime:
                    return True
            except OSError:
                continue  # Vanished or unreadable file — irrelevant to staleness.
    return False
