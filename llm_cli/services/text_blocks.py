"""Marker-delimited block editing in text files (shell profiles, git hooks,
instructions files) — replaces the python heredocs of setup_shell_wrapper.sh,
setup_git_hooks.sh and setup_context_cache.sh plus their PowerShell regex twins.
"""

from __future__ import annotations

import re
from pathlib import Path

from llm_cli.services import fs


def contains(path: Path, marker: str) -> bool:
    """True when the file exists and already carries the marker."""
    return path.is_file() and marker in fs.read_text(path)


def upsert_block(
    path: Path,
    begin_marker: str,
    end_marker: str,
    body: str,
    *,
    newline: str = "\n",
    bom: bool = False,
) -> None:
    """Inserts or replaces the begin..end block, preserving surrounding content."""
    block = f"{begin_marker}\n{body.rstrip()}\n{end_marker}"
    content = fs.read_text(path) if path.is_file() else ""

    pattern = re.compile(
        re.escape(begin_marker) + r".*?" + re.escape(end_marker), re.DOTALL
    )
    if pattern.search(content):
        content = pattern.sub(lambda _: block, content)
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"\n{block}\n"

    fs.write_text_atomic(path, content, newline=newline, bom=bom)


def remove_pattern(path: Path, pattern: re.Pattern, *, newline: str = "\n") -> bool:
    """Deletes every match of a compiled pattern; returns True when something changed."""
    if not path.is_file():
        return False
    content = fs.read_text(path)
    stripped = pattern.sub("", content)
    if stripped == content:
        return False
    fs.write_text_atomic(path, stripped, newline=newline)
    return True


def remove_block(path: Path, begin_marker: str, end_marker: str) -> bool:
    """Deletes a begin..end block (and its leading blank line) if present."""
    pattern = re.compile(
        r"\n?" + re.escape(begin_marker) + r".*?" + re.escape(end_marker) + r"\n?",
        re.DOTALL,
    )
    return remove_pattern(path, pattern)


def strip_markdown_section(path: Path, heading: str) -> bool:
    """Removes a `# heading` markdown section up to the next `# ` heading or EOF
    (contract of setup_context_cache.sh strip_entry)."""
    pattern = re.compile(
        r"\n?" + re.escape(heading) + r".*?(?=\n# |\Z)", re.DOTALL
    )
    return remove_pattern(path, pattern)


def append_section(path: Path, text: str) -> None:
    """Appends a section preceded by a blank line (creates the file if needed)."""
    content = fs.read_text(path) if path.is_file() else ""
    if content and not content.endswith("\n"):
        content += "\n"
    fs.write_text_atomic(path, content + "\n" + text.strip() + "\n")
