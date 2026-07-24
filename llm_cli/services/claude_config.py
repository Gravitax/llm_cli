"""Isolated Claude Code config homes for non-Anthropic providers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from llm_cli import platforms
from llm_cli.services import claude_provider, log, settings_editor

_MAIN_CONFIG_DIR = ".claude"
_SHARED_ITEMS = ("CLAUDE.md", "agents", "commands", "skills")
# Plugins are shared too, but through their own path: unlike the items above
# they can be reconciled when both homes hold real content, because
# installed_plugins.json makes "nothing would be lost" a checkable property.
_PLUGINS = "plugins"
_INSTALLED_PLUGINS = "installed_plugins.json"
_BACKUP_SUFFIX = ".bak"
_PROJECTS = "projects"
_STATE_FILE = ".claude.json"
# Org entitlement caches read from the main state file. Without them the
# provider config dir hides the "full powers" step (auto/bypass) of the
# Shift+Tab permission-mode cycle, because Claude Code gates it on these flags.
_ENTITLEMENT_KEYS = (
    "penguinModeOrgEnabled",
    "hasSeenAutoModeEntryWarning",
    "cachedGrowthBookFeatures",
    "cachedGrowthBookFeaturesAt",
    "cachedExperimentFeatures",
    "orgModelDefaultCache",
)


def ensure(provider: str, label: str) -> Path:
    """Prepares a provider config without the main Anthropic OAuth session."""
    main = Path.home() / _MAIN_CONFIG_DIR
    provider_dir = Path.home() / f".claude-{provider}"
    provider_dir.mkdir(exist_ok=True)
    _seed_state(provider_dir)
    _sync_entitlements(provider_dir)
    _copy_settings(main, provider_dir)
    _link_shared_items(main, provider_dir)
    _share_plugins(main, provider_dir)
    discard_covered_backups()
    _link_projects_dir(main, provider_dir, label)
    return provider_dir


def _seed_state(provider_dir: Path) -> None:
    state = provider_dir / _STATE_FILE
    if not state.is_file():
        state.write_text(json.dumps({"hasCompletedOnboarding": True}) + "\n")


def _sync_entitlements(provider_dir: Path) -> None:
    """Copies the org entitlement caches from the main state file into the
    provider one, so the provider session keeps the permission modes the org
    unlocked. The main OAuth session, userID, machineID and project history
    stay untouched — only the entitlement keys cross over.

    The main state lives at ~/.claude.json (home root), not inside ~/.claude:
    that directory only holds settings.json and shared assets."""
    main_state = _load_state(Path.home() / _STATE_FILE)
    if not main_state:
        return
    target = provider_dir / _STATE_FILE
    provider_state = _load_state(target)
    changed = False
    for key in _ENTITLEMENT_KEYS:
        if key in main_state and provider_state.get(key) != main_state[key]:
            provider_state[key] = main_state[key]
            changed = True
    if changed:
        target.write_text(json.dumps(provider_state, indent=2) + "\n")


def _load_state(path: Path) -> dict:
    try:
        loaded = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _copy_settings(main: Path, provider_dir: Path) -> None:
    settings = settings_editor.load_json(main / "settings.json")
    settings.pop("env", None)
    settings_editor.save_json(
        provider_dir / "settings.json", settings, backup=False
    )


def _link_shared_items(main: Path, provider_dir: Path) -> None:
    """Points every shared item of a provider home at the main one.

    Plugins are shared this way too: installing from any provider must show up
    in all of them, which a symlink gives for free. When only the provider holds
    the item, it is promoted to the main home first so it ends up shared instead
    of stranded. Real content on both sides is never merged — that would need a
    destructive pick between two copies, so it is reported and left untouched.
    """
    for name in _SHARED_ITEMS:
        source, target = main / name, provider_dir / name
        if target.is_symlink():
            continue
        if not source.exists():
            if not target.exists():
                continue
            target.rename(source)
        elif target.exists():
            log.print_warn(
                f"{target} and {source} both exist — kept separate. "
                f"Merge them by hand to share {name} across providers."
            )
            continue
        try:
            target.symlink_to(source)
        except OSError:
            _copy_item(source, target)


def share_plugins() -> None:
    """Points every existing provider home's plugins dir at the main one.

    Called at install time so all providers are reconciled at once, and again
    from ensure() so a home created later still converges on its first launch.
    """
    main = Path.home() / _MAIN_CONFIG_DIR
    for provider in (claude_provider.GLM, claude_provider.COPILOT):
        provider_dir = Path.home() / f".claude-{provider}"
        if provider_dir.is_dir():
            _share_plugins(main, provider_dir)


def discard_covered_backups() -> None:
    """Drops every set-aside provider copy the main home now covers.

    Runs after the plugins declared in plugins.yaml have been reinstalled, so a
    plugin that only existed in a provider copy is already back in the main home
    and no longer counts as a reason to keep the backup.
    """
    source = Path.home() / _MAIN_CONFIG_DIR / _PLUGINS
    for provider in (claude_provider.GLM, claude_provider.COPILOT):
        backup = Path.home() / f".claude-{provider}" / (_PLUGINS + _BACKUP_SUFFIX)
        if backup.is_dir():
            _discard_covered_backup(backup, source)


def _share_plugins(main: Path, provider_dir: Path) -> None:
    """Makes provider_dir/plugins a symlink to the main home's plugins dir.

    A plugin installed from any provider must be visible from all of them, which
    one shared directory gives for free. The main home wins when both hold real
    content: plugins.yaml reinstalls whatever is missing, so the provider copy is
    set aside rather than merged.
    """
    source, target = main / _PLUGINS, provider_dir / _PLUGINS
    if target.is_symlink():
        return
    if not target.exists():
        if source.exists():
            _link_plugins(source, target)
        return
    if not source.exists():
        # Only the provider holds plugins: promote them instead of stranding
        # them in a home the other providers never read.
        target.rename(source)
        _link_plugins(source, target)
        return

    backup = target.with_name(target.name + _BACKUP_SUFFIX)
    if backup.exists():
        log.print_warn(f"{backup} already exists — left {target} untouched.")
        return
    target.rename(backup)
    _link_plugins(source, target)


def _link_plugins(source: Path, target: Path) -> None:
    try:
        target.symlink_to(source, target_is_directory=True)
    except OSError:
        _copy_item(source, target)


def _discard_covered_backup(backup: Path, source: Path) -> None:
    """Removes the set-aside copy once the main home covers all of its plugins.

    The check is what makes the removal safe: a plugin installed by hand and
    absent from plugins.yaml would not come back, so an uncovered backup is kept.
    """
    extra = _installed_ids(backup) - _installed_ids(source)
    if extra:
        log.print_warn(
            f"{backup} kept — {', '.join(sorted(extra))} missing from {source}."
        )
        return
    shutil.rmtree(backup, ignore_errors=True)


def _installed_ids(plugins_dir: Path) -> set[str]:
    """Plugin ids recorded in a plugins dir (empty when unreadable)."""
    installed = _load_state(plugins_dir / _INSTALLED_PLUGINS).get("plugins", {})
    return set(installed) if isinstance(installed, dict) else set()


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
