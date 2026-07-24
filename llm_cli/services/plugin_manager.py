"""plugin_manager — drives the official `claude plugin` CLI from plugins.yaml.

The declarative source of truth is llm_cli/templates/plugins.yaml: a list of
marketplaces to register and plugins to install. Everything is idempotent — a
marketplace already in `claude plugin marketplace list` or a plugin already in
`claude plugin list` is skipped, so re-running setup never duplicates work.

Only real marketplace plugins/skills are handled here. Tools that are not
Claude Code plugins (headroom proxy, RTK) keep their own setup commands.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from llm_cli.services import log, settings_editor, templates, tool_binary

_TEMPLATE = "plugins"
_SKILL_MANIFEST = "SKILL.md"
# Every `claude plugin` call is a network operation (marketplace clone, plugin
# fetch). These caps are deliberately short: a CLI stuck on an invisible prompt
# (marketplace trust, git credentials) must fail fast and let the setup move on
# rather than freeze it. Plugins are optional, so a missed one is a warning.
_CLI_TIMEOUT_SECONDS = 30
_QUERY_TIMEOUT_SECONDS = 15


def load_spec() -> dict:
    """Returns the parsed plugins.yaml ({'marketplaces': [...], 'plugins': [...]})."""
    return templates.load(_TEMPLATE)


def declared_plugin_names() -> list[str]:
    """Plugin ids listed in plugins.yaml (with any @marketplace suffix kept)."""
    return [p["name"] for p in load_spec().get("plugins", []) if p.get("name")]


def missing_plugins(claude: str, settings_json: Path) -> list[str]:
    """Declared plugins that are not yet installed and enabled (best-effort).

    Presence comes from `claude plugin list`; the enabled flag lives in
    settings.json under `enabledPlugins` (the CLI's list output does not
    reliably reflect it), so both must agree for a plugin to count as ready.
    """
    installed = _installed_ids(claude)
    enabled = _enabled_ids(settings_json)
    return [
        name
        for name in declared_plugin_names()
        if name not in installed or name not in enabled
    ]


def claude_binary() -> str | None:
    """Path to the real `claude` CLI, or None when it is not installed.

    Resolved through tool_binary: our own `claude` entry point shadows the real
    one on PATH, and going through it would replay the entire pre-launch
    pipeline (context re-index, proxy start, hook repair) on every plugin call.
    """
    return tool_binary.resolve("claude")


def sync_plugins(settings_json: Path) -> bool:
    """Registers every marketplace, installs every plugin, then enables them all.

    Activation is written directly to settings.json in one merged pass because
    `claude plugin enable` rewrites `enabledPlugins` with a single key, losing
    every previously enabled plugin. It targets the main home rather than the
    provider one a `-glm`/`-copilot` session runs in: provider homes are
    re-seeded from the main settings.json at every launch, so anything written
    there alone is wiped on the next switch. Returns True when the CLI was
    available and all steps succeeded, False when `claude` is missing or any
    step failed (degrades to a warning, never raises).
    """
    claude = claude_binary()
    if claude is None:
        log.print_warn("claude CLI not found in PATH — skipping plugin setup.")
        return False

    spec = load_spec()
    ok = True
    log.print_info(
        f"Querying registered marketplaces (up to {_QUERY_TIMEOUT_SECONDS}s)..."
    )
    known = _known_marketplaces(claude)
    for marketplace in spec.get("marketplaces", []):
        ok = _ensure_marketplace(claude, marketplace, known) and ok

    log.print_info(f"Querying installed plugins (up to {_QUERY_TIMEOUT_SECONDS}s)...")
    installed = _installed_ids(claude)
    to_enable: list[str] = []
    for plugin in spec.get("plugins", []):
        name = _ensure_installed(claude, plugin, installed)
        if name is None:
            ok = False
        else:
            to_enable.append(name)

    if to_enable:
        newly = settings_editor.enable_plugins(settings_json, to_enable)
        for name in to_enable:
            if name in newly:
                log.print_ok(f"Plugin enabled: {name}")
            else:
                log.print_ok(f"Plugin already enabled: {name}")
    return ok


def sync_skills(skills_dir: Path) -> bool:
    """Installs every raw SKILL.md skill from plugins.yaml into skills_dir.

    Each skill is git cloned and the folder holding its SKILL.md is copied to
    skills_dir/<name>/. Idempotent: a skill whose SKILL.md already exists is
    skipped. Returns True when all skills are present, False on any failure.
    """
    skills = load_spec().get("skills", [])
    if not skills:
        return True
    if shutil.which("git") is None:
        log.print_warn("git not found in PATH — skipping skill setup.")
        return False

    ok = True
    for skill in skills:
        ok = _ensure_skill(skill, skills_dir) and ok
    return ok


def _ensure_skill(skill: dict, skills_dir: Path) -> bool:
    name = skill.get("name")
    repo = skill.get("repo")
    if not name or not repo:
        log.print_warn(f"skill entry needs name and repo, skipped: {skill}")
        return False

    target = skills_dir / name
    if (target / _SKILL_MANIFEST).is_file():
        log.print_ok(f"Skill already installed: {name}")
        return True

    import tempfile

    url = repo if "://" in repo else f"https://github.com/{repo}.git"
    with tempfile.TemporaryDirectory() as tmp:
        if not _run(["git", "clone", "--depth", "1", url, tmp]):
            log.print_warn(f"Failed to clone skill repo: {url}")
            return False
        source = Path(tmp) / skill.get("path", ".")
        if not (source / _SKILL_MANIFEST).is_file():
            log.print_warn(f"{_SKILL_MANIFEST} not found in {repo}/{skill.get('path', '.')}")
            return False
        target.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            if item.name == ".git":
                continue
            dest = target / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
    log.print_ok(f"Skill installed: {name} -> {target}")
    return True


def _ensure_marketplace(claude: str, marketplace: dict, known: set[str]) -> bool:
    name = marketplace.get("name")
    source = marketplace.get("source")
    if not source:
        log.print_warn(f"marketplace entry without a source, skipped: {marketplace}")
        return False
    if name and name in known:
        log.print_ok(f"Marketplace already registered: {name}")
        return True

    argv = [claude, "plugin", "marketplace", "add", source]
    scope = marketplace.get("scope")
    if scope:
        argv += ["--scope", scope]
    log.print_info(f"Adding marketplace {source} (network, up to {_CLI_TIMEOUT_SECONDS}s)...")
    if _run(argv):
        log.print_ok(f"Marketplace added: {source}")
        return True
    log.print_warn(f"Failed to add marketplace: {source}")
    return False


def _ensure_installed(claude: str, plugin: dict, installed: set[str]) -> str | None:
    """Installs the plugin if absent; returns its full id, or None on failure.

    Activation is handled separately (merged write to settings.json), so this
    only guarantees the plugin is present in a marketplace cache.
    """
    name = plugin.get("name")
    if not name:
        log.print_warn(f"plugin entry without a name, skipped: {plugin}")
        return None

    if name in installed or _plugin_id(name) in installed:
        return name

    argv = [claude, "plugin", "install", name]
    scope = plugin.get("scope")
    if scope:
        argv += ["--scope", scope]
    log.print_info(f"Installing plugin {name} (network, up to {_CLI_TIMEOUT_SECONDS}s)...")
    if _run(argv):
        log.print_ok(f"Plugin installed: {name}")
        return name
    log.print_warn(f"Failed to install plugin: {name}")
    return None


def _known_marketplaces(claude: str) -> set[str]:
    """Marketplace names already registered (best-effort, empty on any failure)."""
    import json

    out = _capture([claude, "plugin", "marketplace", "list", "--json"])
    if not out:
        return set()
    try:
        data = json.loads(out)
    except ValueError:
        return set()
    if isinstance(data, dict):
        return set(data.keys())
    return {item.get("name", "") for item in data if isinstance(item, dict)}


def _installed_ids(claude: str) -> set[str]:
    """Full ids of installed plugins ('<name>@<marketplace>'), empty on failure."""
    import json

    out = _capture([claude, "plugin", "list", "--json"])
    if not out:
        return set()
    try:
        data = json.loads(out)
    except ValueError:
        return set()
    entries = data.values() if isinstance(data, dict) else data
    installed: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        # `claude plugin list --json` uses "id" ("<name>@<marketplace>").
        plugin_id = item.get("id") or item.get("name")
        if plugin_id:
            installed.add(plugin_id)
    return installed


def _enabled_ids(settings_json: Path) -> set[str]:
    """Full ids marked enabled in settings.json `enabledPlugins`.

    `claude plugin enable` persists the enabled flag here (keyed by the full
    '<name>@<marketplace>' id); the CLI list output does not reliably show it.
    """
    import json

    try:
        data = json.loads(settings_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    enabled = data.get("enabledPlugins", {})
    if not isinstance(enabled, dict):
        return set()
    return {name for name, on in enabled.items() if on}


def _plugin_id(name: str) -> str:
    """Bare plugin name without the @marketplace suffix, for install checks."""
    return name.split("@", 1)[0]


def _run(argv: list[str]) -> bool:
    """Runs a CLI command, echoing its output indented; True on exit code 0."""
    try:
        result = _subprocess_run(argv)
    except OSError as error:
        log.print_warn(f"could not run {' '.join(argv)}: {error}")
        return False
    except subprocess.TimeoutExpired:
        log.print_warn(
            f"timed out after {_CLI_TIMEOUT_SECONDS}s: {' '.join(argv)}"
        )
        return False
    for line in (result.stdout + result.stderr).splitlines():
        log.print_info(log.console_safe(line))
    return result.returncode == 0


def _capture(argv: list[str]) -> str:
    """Captures stdout of a read-only query; '' on any failure."""
    try:
        result = _subprocess_run(argv, timeout=_QUERY_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _subprocess_run(
    argv: list[str], timeout: int = _CLI_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    """Captured, non-interactive CLI call whose timeout actually fires.

    Output goes to a temporary file rather than an OS pipe. On Windows a
    `claude`/`git` child that spawns its own children keeps the pipe's write end
    open, so the pipe drain subprocess.run performs on timeout blocks forever and
    the timeout never takes effect — the exact freeze seen on the plugin step. A
    plain file has no such back-pressure, so the child can be killed and
    TimeoutExpired raised on schedule.

    stdin is closed so a CLI that asks for confirmation (marketplace trust, git
    credentials) fails fast instead of waiting on a prompt nobody can see.
    """
    with tempfile.TemporaryFile() as sink:
        try:
            completed = subprocess.run(
                argv,
                stdout=sink,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
            )
        finally:
            sink.seek(0)
            output = sink.read().decode("utf-8", "replace")
    return subprocess.CompletedProcess(argv, completed.returncode, output, "")
