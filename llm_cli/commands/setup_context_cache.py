"""setup-context-cache — generates or removes the project context index
(port of setup_context_cache.sh / setup_context_cache.ps1).

project — git root (or explicit path): indexing scope and cache hash key.
launch_dir — directory where the tool was invoked: receives the local
instructions entry and the ignore file. Defaults to project.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from llm_cli import tool_profile
from llm_cli.commands import setup_git_hooks
from llm_cli.services import cache, instructions, log
from llm_cli.tool_profile import TOOL_NAMES, ToolProfile


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-context-cache",
        help="generate the project symbol index (-u to remove it)",
    )
    parser.add_argument("--tool", required=True, choices=list(TOOL_NAMES))
    parser.add_argument("project", nargs="?", default=".", help="project path")
    parser.add_argument("launch_dir", nargs="?", help="tool launch directory")
    parser.add_argument(
        "-u", "--remove", action="store_true", help="remove index + entry instead"
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    profile = tool_profile.resolve(args.tool)
    project = Path(args.project).resolve()
    if args.remove:
        print("Removing context cache...")
        remove_index(profile, project)
        return 0
    print("Generating project context index...")
    launch_dir = Path(args.launch_dir).resolve() if args.launch_dir else project
    return generate_index(profile, project, launch_dir)


def generate_index(profile: ToolProfile, project: Path, launch_dir: Path) -> int:
    cache_file = cache.cache_file_for(profile, project)
    if not _build_with_rollback(project, cache_file):
        return 1
    if cache_file.is_file():
        entry_file = instructions.inject_index_entry(
            profile, cache_file, project, launch_dir
        )
        log.print_ok(f"{entry_file} entry updated")
    if instructions.write_ignore_file(profile, launch_dir):
        log.print_ok(f"{profile.ignore_file} created in {launch_dir}")

    # Install git hooks so mid-session structural changes also trigger a refresh.
    setup_git_hooks.install_global_template()
    setup_git_hooks.install_repo_hooks(project)

    # The steps above rewrite files inside the project (instructions entry,
    # ignore file), which would make the cache look stale on the next launch
    # and force a rebuild every time. Touch it last so it stays the newest.
    if cache_file.is_file():
        cache_file.touch()
    return 0


def refresh_if_indexed(profile: ToolProfile, project: Path) -> None:
    """Refreshes the cache only when the project was already indexed by a
    previous session — shared by the PostToolUse hooks and the git hooks."""
    cache_file = cache.cache_file_for(profile, project)
    if not cache_file.is_file():
        return
    generate_index(profile, project, project)


def remove_index(profile: ToolProfile, project: Path) -> None:
    if instructions.strip_index_entry(profile, project):
        log.print_ok(
            f"Context index entry removed from {project / profile.instructions_local}"
        )
    else:
        log.print_ok(
            f"No context index entry found in {project / profile.instructions_local}"
        )
    cache_file = cache.cache_file_for(profile, project)
    if cache_file.is_file():
        cache_file.unlink()
        log.print_ok(f"Cache file removed: {cache_file}")


def _build_with_rollback(project: Path, cache_file: Path) -> bool:
    """Runs the indexer, restoring the previous cache on failure."""
    from llm_cli.services import indexer  # Deferred: heaviest import of the package.

    backup = Path(str(cache_file) + ".bak")
    if cache_file.is_file():
        shutil.copy2(cache_file, backup)
    try:
        indexer.build_index(project, cache_file)
    except Exception as error:  # noqa: BLE001 — any indexer failure rolls back.
        if backup.is_file():
            backup.replace(cache_file)
            log.print_warn(f"Index generation failed — previous cache restored ({error}).")
        else:
            log.print_err(f"Index generation failed: {error}")
        return False
    if backup.is_file():
        backup.unlink()
    return True
