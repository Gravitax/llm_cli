"""Thin git helpers shared by cache, hooks and credential commands."""

from __future__ import annotations

import subprocess
from pathlib import Path


def toplevel(directory: Path | None = None) -> Path:
    """Git root of the directory, or the directory itself outside any repo."""
    base = directory or Path.cwd()
    result = subprocess.run(
        ["git", "-C", str(base), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return base
    return Path(result.stdout.strip())


def git_dir(project: Path) -> Path | None:
    """The repository's .git directory, or None outside any repo."""
    result = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    found = Path(result.stdout.strip())
    return found if found.is_absolute() else project / found


def get_global_config(key: str) -> str:
    result = subprocess.run(
        ["git", "config", "--global", "--get", key],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def set_global_config(key: str, value: str) -> None:
    subprocess.run(["git", "config", "--global", key, value], check=True)
