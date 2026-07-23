"""Isolated Claude Code config homes for non-Anthropic providers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from llm_cli import platforms
from llm_cli.services import log, settings_editor

_MAIN_CONFIG_DIR = ".claude"
_SHARED_ITEMS = ("CLAUDE.md", "agents", "commands", "skills")
_PROJECTS = "projects"


def ensure(provider: str, label: str) -> Path:
    """Prepares a provider config without the main Anthropic OAuth session."""
    main = Path.home() / _MAIN_CONFIG_DIR
    provider_dir = Path.home() / f".claude-{provider}"
    provider_dir.mkdir(exist_ok=True)
    _seed_state(provider_dir)
    _copy_settings(main, provider_dir)
    _link_shared_items(main, provider_dir)
    _link_projects_dir(main, provider_dir, label)
    return provider_dir


def _seed_state(provider_dir: Path) -> None:
    state = provider_dir / ".claude.json"
    if not state.is_file():
        state.write_text(json.dumps({"hasCompletedOnboarding": True}) + "\n")


def _copy_settings(main: Path, provider_dir: Path) -> None:
    settings = settings_editor.load_json(main / "settings.json")
    settings.pop("env", None)
    settings_editor.save_json(
        provider_dir / "settings.json", settings, backup=False
    )


def _link_shared_items(main: Path, provider_dir: Path) -> None:
    for name in _SHARED_ITEMS:
        source, target = main / name, provider_dir / name
        if not source.exists() or target.is_symlink():
            continue
        try:
            target.symlink_to(source)
        except OSError:
            _copy_item(source, target)


def _copy_item(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def _link_projects_dir(main: Path, provider_dir: Path, label: str) -> None:
    source = main / _PROJECTS
    target = provider_dir / _PROJECTS
    try:
        source.mkdir(parents=True, exist_ok=True)
        if _points_at(target, source):
            return
        _merge_projects(target, source)
        _link_directory(source, target)
    except OSError as exc:
        log.red_banner([
            f"Could not share conversation history with the {label} config dir.",
            f"  {exc}",
            f"Claude and {label} histories stay separate this session.",
        ])


def _points_at(target: Path, source: Path) -> bool:
    try:
        return target.is_dir() and target.resolve() == source.resolve()
    except OSError:
        return False


def _merge_projects(target: Path, source: Path) -> None:
    if not target.exists() or _points_at(target, source):
        return
    for project_dir in [path for path in target.iterdir() if path.is_dir()]:
        dest_project = source / project_dir.name
        dest_project.mkdir(parents=True, exist_ok=True)
        for child in list(project_dir.iterdir()):
            _move_session_child(child, dest_project / child.name)
    shutil.rmtree(target, ignore_errors=True)


def _move_session_child(child: Path, dest: Path) -> None:
    if not dest.exists():
        shutil.move(str(child), str(dest))
        return
    child_newer = child.stat().st_mtime > dest.stat().st_mtime
    if child.is_dir() and dest.is_dir():
        shutil.copytree(child, dest, dirs_exist_ok=True)
        shutil.rmtree(child)
    elif child.is_file() and dest.is_file():
        if child_newer:
            shutil.move(str(child), str(dest))
        else:
            child.unlink()
    else:
        shutil.rmtree(child) if child.is_dir() else child.unlink()


def _link_directory(source: Path, target: Path) -> None:
    try:
        target.symlink_to(source, target_is_directory=True)
        return
    except OSError:
        pass
    if platforms.current().is_windows:
        _create_windows_junction(source, target)
        return
    raise OSError(f"Cannot create directory link {target} -> {source}")


def _create_windows_junction(source: Path, target: Path) -> None:
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(target), str(source)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise OSError(
            f"mklink /J {target} -> {source} failed: {result.stderr.strip()}"
        )
