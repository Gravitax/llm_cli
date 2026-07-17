"""sync — installs the llm_cli package and run.py into ~/.llm_cli so the
settings.json hooks can invoke them at a fixed absolute path during sessions.

The `claude`/`copilot` wrapper commands themselves ship as pip console entry
points (see install.py), so no shell shims are copied. This command also cleans
up the retired per-tool script copies in ~/.claude/scripts and ~/.copilot/scripts,
leaving no-op tombstones for shell functions still loaded in long-lived terminals.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from llm_cli import paths, platforms
from llm_cli.services import fs, log
from llm_cli.tool_profile import ALL_PROFILES, ToolProfile

_LEGACY_SCRIPT_GLOBS = ("*.sh", "*.ps1", "gen_context_cache.py", "profile.env")
# Our own migration tombstones (written below) also match *.sh — they must
# survive the cleanup or every run deletes and rewrites them, reporting
# "2 legacy scripts removed" forever.
_TOMBSTONE_NAMES = ("lib_cache.sh", "lib_headroom.sh")

# Old profile wrappers still loaded in open terminals source these files by
# name; the tombstones keep those wrappers working (delegating to run.py)
# until every shell has been restarted. Removed one release later.
_TOMBSTONE_LIB_CACHE = """\
#!/bin/bash
# llm_cli migration tombstone — the logic moved to ~/.llm_cli (python core).
_run_tool_pre_launch() { :; }
_check_and_build_cache() {
    "${PYTHON_BIN:-python3}" "$HOME/.llm_cli/run.py" prelaunch __TOOL__ || :
}
"""
_TOMBSTONE_LIB_HEADROOM = """\
#!/bin/bash
# llm_cli migration tombstone — the logic moved to ~/.llm_cli (python core).
_headroom_export_ghe_env() { :; }
_ensure_headroom_proxy() { :; }
_launch_with_headroom() {
    local tool="$1"; shift
    "${PYTHON_BIN:-python3}" "$HOME/.llm_cli/run.py" launch "$tool" -- "$@"
}
"""


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "sync", help="install the package + run.py into ~/.llm_cli"
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    source_root = paths.package_root()
    target_root = paths.install_root()
    if source_root == target_root:
        log.print_info("[SKIP] Already running from the installed copy — nothing to sync.")
        return 0
    if not (source_root / "run.py").is_file():
        log.print_info("[SKIP] Scripts sync requires the source repository layout.")
        return 0

    _copy_tree(source_root / "llm_cli", target_root / "llm_cli")
    _copy_file(source_root / "run.py", target_root / "run.py")
    _cleanup_legacy_scripts()
    log.print_ok(f"llm_cli installed to {target_root}")
    return 0


def _copy_tree(source: Path, target: Path) -> None:
    # A fresh tree (not merge-copy) so renamed/deleted modules never linger.
    if target.is_dir():
        shutil.rmtree(target)
    shutil.copytree(
        source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    ops = platforms.current()
    for item in target.rglob("*"):
        if item.is_file():
            ops.unblock(item)
            ops.make_executable(item)


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    ops = platforms.current()
    ops.unblock(target)
    ops.make_executable(target)


def _cleanup_legacy_scripts() -> None:
    """Empties the retired ~/.<tool>/scripts copies (fully managed by the old
    sync) and drops the shell tombstones for still-open terminals."""
    for profile in ALL_PROFILES:
        scripts_dir = profile.home / "scripts"
        if not scripts_dir.is_dir():
            continue
        removed = 0
        for pattern in _LEGACY_SCRIPT_GLOBS:
            for legacy in scripts_dir.glob(pattern):
                if legacy.name in _TOMBSTONE_NAMES:
                    continue
                legacy.unlink()
                removed += 1
        _write_tombstones(profile, scripts_dir)
        if removed:
            log.print_ok(f"{removed} legacy scripts removed from {scripts_dir}")


def _write_tombstones(profile: ToolProfile, scripts_dir: Path) -> None:
    fs.write_text_atomic(
        scripts_dir / "lib_cache.sh",
        _TOMBSTONE_LIB_CACHE.replace("__TOOL__", profile.name),
    )
    fs.write_text_atomic(scripts_dir / "lib_headroom.sh", _TOMBSTONE_LIB_HEADROOM)
