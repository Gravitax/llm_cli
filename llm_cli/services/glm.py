"""GLM (z.ai) provider routing for Claude Code — backs the `claude -glm` toggle.

z.ai exposes an Anthropic-compatible endpoint, so switching provider is a
matter of exporting ANTHROPIC_* overrides before the launch — plus an isolated
CLAUDE_CONFIG_DIR: the main ~/.claude holds the claude.ai OAuth login, and
claude sends that OAuth bearer instead of ANTHROPIC_AUTH_TOKEN whenever the
login is present (z.ai then answers 401). The active provider persists in the
llm_cli config (CLAUDE_PROVIDER key). The API key is read from the GLM_API_KEY
environment variable; when it is missing on an interactive terminal, the
launch prompts for it and offers to persist it into the user's own shell
profile (explicit opt-in) — it never touches any other file managed by this
tool.
"""

from __future__ import annotations

import getpass
import json
import os
import shutil
import sys
from pathlib import Path

from llm_cli import platforms
from llm_cli.platforms.base import ProfileTarget
from llm_cli.services import config, log, settings_editor, text_blocks

GLM_BASE_URL = "https://api.z.ai/api/anthropic"
# The [1m] suffix is required — without it z.ai silently serves a reduced
# context window instead of the model's full 1M tokens.
GLM_DEFAULT_MODEL = "glm-5.2[1m]"
GLM_HAIKU_MODEL = "glm-4.7"

_PROVIDER_KEY = "CLAUDE_PROVIDER"
_API_KEY_ENV = "GLM_API_KEY"
_API_TIMEOUT_MS = "3000000"  # Long agentic turns need it (value from z.ai docs).
_KEY_BLOCK_BEGIN = "# >>> llm_cli glm >>>"
_KEY_BLOCK_END = "# <<< llm_cli glm <<<"

_MAIN_CONFIG_DIR = ".claude"
_GLM_CONFIG_DIR = ".claude-glm"
# Read by claude from the config dir itself; kept pointing at the main one.
_SHARED_ITEMS = ("CLAUDE.md", "agents", "commands", "skills")


def is_active() -> bool:
    """True when the persisted provider toggle points at GLM."""
    return config.load().get(_PROVIDER_KEY, "") == "glm"


def toggle() -> bool:
    """Flips the persisted provider (Anthropic <-> GLM); returns the new state."""
    values = config.load()
    activated = values.get(_PROVIDER_KEY, "") != "glm"
    values[_PROVIDER_KEY] = "glm" if activated else "anthropic"
    config.store(values)
    print(f"Provider switched to {'GLM (z.ai)' if activated else 'Anthropic'}.")
    return activated


def require_api_key() -> bool:
    """True when GLM_API_KEY is available — prompting for it (and offering to
    persist it to the shell profile) on interactive terminals. Never falls
    back to the Anthropic API silently — that would bill the wrong
    subscription."""
    if os.environ.get(_API_KEY_ENV):
        return True
    log.red_banner([
        f"GLM provider is ACTIVE but {_API_KEY_ENV} is not set.",
        "Set it in the current shell:",
        f'  PowerShell: $env:{_API_KEY_ENV} = "<your z.ai key>"',
        f"  bash/zsh:   export {_API_KEY_ENV}=<your z.ai key>",
        "or switch back to Anthropic with: claude -glm",
    ])
    if not sys.stdin.isatty():
        return False
    key = _prompt_for_key()
    if not key:
        return False
    os.environ[_API_KEY_ENV] = key
    _offer_persist(key)
    return True


def _prompt_for_key() -> str:
    try:
        return getpass.getpass(
            "  Enter your z.ai API key now (leave empty to abort): "
        ).strip()
    except EOFError:
        return ""


def _offer_persist(key: str) -> None:
    target = _current_shell_profile()
    if target is None:
        return
    reply = input(f"  Save {_API_KEY_ENV} to {target.path}? [Y/n] ").strip() or "y"
    if not reply.lower().startswith("y"):
        print("  Not saved — you will be asked again next GLM session.")
        return
    _write_key_block(target, key)
    print(f"  Saved to {target.path} (takes effect in new terminals).")


def _current_shell_profile() -> ProfileTarget | None:
    """The profile of the CURRENT shell: $SHELL picks between the POSIX
    candidates (zsh -> .zshrc, bash -> .bashrc); Windows has a single
    PowerShell $PROFILE target."""
    targets = platforms.current().shell_profile_targets()
    if not targets:
        return None
    shell_name = Path(os.environ.get("SHELL", "")).name
    for target in targets:
        if shell_name and target.path.name == f".{shell_name}rc":
            return target
    return targets[0]


def _write_key_block(target: ProfileTarget, key: str) -> None:
    encoding = platforms.current().profile_encoding()
    if target.kind == "powershell":
        body = f'$env:{_API_KEY_ENV} = "{key}"'
    else:
        body = f'export {_API_KEY_ENV}="{key}"'
    text_blocks.upsert_block(
        target.path, _KEY_BLOCK_BEGIN, _KEY_BLOCK_END, body,
        newline=encoding.newline, bom=encoding.bom,
    )


def export_env() -> None:
    """Exports the Anthropic-compatible overrides that route Claude Code to
    z.ai. The DEFAULT_*_MODEL variables remap the Opus/Sonnet/Haiku slots so
    the in-session /model picker shows the GLM models. CLAUDE_CONFIG_DIR
    points at a config home without the claude.ai OAuth login — with the login
    visible, claude sends the OAuth bearer instead of ANTHROPIC_AUTH_TOKEN and
    z.ai rejects it with 401."""
    os.environ.update({
        "ANTHROPIC_BASE_URL": GLM_BASE_URL,
        "ANTHROPIC_AUTH_TOKEN": os.environ[_API_KEY_ENV],
        "ANTHROPIC_DEFAULT_OPUS_MODEL": GLM_DEFAULT_MODEL,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": GLM_DEFAULT_MODEL,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": GLM_HAIKU_MODEL,
        "API_TIMEOUT_MS": _API_TIMEOUT_MS,
        "CLAUDE_CONFIG_DIR": str(ensure_config_dir()),
    })
    # A leftover Anthropic key would take precedence over AUTH_TOKEN.
    os.environ.pop("ANTHROPIC_API_KEY", None)


def ensure_config_dir() -> Path:
    """Prepares the isolated Claude config home for GLM sessions: onboarding
    state pre-seeded, the main settings minus their env block (proxy routing
    and the first-party flag must not leak into a z.ai session), and the
    shared instruction files linked in."""
    main = Path.home() / _MAIN_CONFIG_DIR
    glm_dir = Path.home() / _GLM_CONFIG_DIR
    glm_dir.mkdir(exist_ok=True)
    _seed_state(glm_dir)
    _copy_settings(main, glm_dir)
    _link_shared_items(main, glm_dir)
    return glm_dir


def _seed_state(glm_dir: Path) -> None:
    """Skips the first-run wizard; never overwrites the evolving state."""
    state = glm_dir / ".claude.json"
    if not state.is_file():
        state.write_text(json.dumps({"hasCompletedOnboarding": True}) + "\n")


def _copy_settings(main: Path, glm_dir: Path) -> None:
    """Hooks, permissions and theme follow the main profile on every launch."""
    settings = settings_editor.load_json(main / "settings.json")
    settings.pop("env", None)
    settings_editor.save_json(glm_dir / "settings.json", settings, backup=False)


def _link_shared_items(main: Path, glm_dir: Path) -> None:
    for name in _SHARED_ITEMS:
        source, target = main / name, glm_dir / name
        if not source.exists() or target.is_symlink():
            continue
        try:
            target.symlink_to(source)
        except OSError:
            # No symlink privilege (e.g. Windows): refresh a copy instead.
            _copy_item(source, target)


def _copy_item(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def with_default_model(arguments: list[str]) -> list[str]:
    """Prepends `--model <GLM default>` unless the caller already set one —
    otherwise a `model` pinned in settings.json (a claude-* id unknown to
    z.ai) would win over the environment remapping."""
    if any(arg == "--model" or arg.startswith("--model=") for arg in arguments):
        return arguments
    return ["--model", GLM_DEFAULT_MODEL, *arguments]
