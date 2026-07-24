"""Tool settings.json editing (replaces the jq edits of setup_env.sh, the node
heredoc of setup_atlassian.sh and lib_settings.ps1).

The whole file is round-tripped through json so unknown fields (env, model,
enabledPlugins, existing hooks...) are preserved automatically.
"""

from __future__ import annotations

import json
from pathlib import Path

from llm_cli.services import fs


def load_json(path: Path) -> dict:
    """Loads a JSON object file (empty object when absent or blank)."""
    if not path.is_file():
        return {}
    raw = fs.read_text(path).strip()
    return json.loads(raw) if raw else {}


def save_json(path: Path, obj: dict, *, backup: bool = True) -> None:
    """Saves atomically with a .bak of the previous version.

    Pass backup=False for credential-bearing files: a stray .bak would escape
    the make_private() applied to the main file.
    """
    fs.write_text_atomic(path, json.dumps(obj, indent=2) + "\n", backup=backup)


def contains(path: Path, needle: str) -> bool:
    """Cheap idempotence probe on the raw file (mirrors the grep -qF checks)."""
    return path.is_file() and needle in fs.read_text(path)


def register_hook(path: Path, event: str, matcher: str, entry: dict) -> None:
    """Appends a {matcher, hooks:[entry]} item under hooks.<event>."""
    settings = load_json(path)
    hooks = settings.setdefault("hooks", {})
    hooks.setdefault(event, []).append({"matcher": matcher, "hooks": [entry]})
    save_json(path, settings)


def remove_hooks(path: Path, event: str, needle: str) -> bool:
    """Drops every hooks.<event> item whose command contains the needle."""
    settings = load_json(path)
    items = settings.get("hooks", {}).get(event, [])
    kept = [item for item in items if needle not in json.dumps(item)]
    if len(kept) == len(items):
        return False
    settings["hooks"][event] = kept
    save_json(path, settings)
    return True


def ensure_permission_rule(path: Path, rule: str) -> bool:
    """Adds a permissions.allow rule once; returns True when it was added."""
    if contains(path, rule):
        return False
    settings = load_json(path)
    permissions = settings.setdefault("permissions", {})
    allow = permissions.setdefault("allow", [])
    allow.append(rule)
    save_json(path, settings)
    return True


def enable_plugins(path: Path, plugin_ids: list[str]) -> list[str]:
    """Marks each plugin id enabled in settings.json, merging (never replacing).

    `claude plugin enable` rewrites the whole `enabledPlugins` map with a single
    key, so activating several plugins in a row keeps only the last. Writing the
    merged map ourselves makes multi-plugin activation deterministic. Returns the
    ids that were newly enabled.
    """
    settings = load_json(path)
    enabled = settings.setdefault("enabledPlugins", {})
    newly = [pid for pid in plugin_ids if not enabled.get(pid, False)]
    if not newly:
        return []
    for pid in newly:
        enabled[pid] = True
    save_json(path, settings)
    return newly

