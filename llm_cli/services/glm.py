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
import os
import sys
from pathlib import Path

from llm_cli import platforms
from llm_cli.platforms.base import ProfileTarget
from llm_cli.services import (
    claude_config,
    claude_provider,
    config,
    log,
    model_picker,
    text_blocks,
)

GLM_BASE_URL = "https://api.z.ai/api/anthropic"
# One model per Claude Code slot, so /model offers three real choices instead
# of the same id twice. The [1m] suffix is documented for glm-5.2 only —
# without it z.ai silently serves a reduced context window instead of the
# model's full 1M tokens — so the other slots stay on the plain ids.
GLM_DEFAULT_MODEL = "glm-5-turbo"
GLM_OPUS_MODEL = "glm-5.2[1m]"
GLM_SMALL_MODEL = "glm-4.6"

API_KEY_ENV = "GLM_API_KEY"
_EXTRA_MODEL_KEY = "CLAUDE_GLM_EXTRA_MODEL"
_API_TIMEOUT_MS = "3000000"  # Long agentic turns need it (value from z.ai docs).
_KEY_BLOCK_BEGIN = "# >>> llm_cli glm >>>"
_KEY_BLOCK_END = "# <<< llm_cli glm <<<"


def is_active() -> bool:
    """True when the persisted provider toggle points at GLM."""
    return claude_provider.is_active(claude_provider.GLM)


def toggle() -> bool:
    """Flips the persisted provider (Anthropic <-> GLM); returns the new state."""
    return claude_provider.toggle(claude_provider.GLM)


def require_api_key() -> bool:
    """True when GLM_API_KEY is available — prompting for it (and offering to
    persist it to the shell profile) on interactive terminals. Never falls
    back to the Anthropic API silently — that would bill the wrong
    subscription."""
    if os.environ.get(API_KEY_ENV):
        return True
    log.red_banner([
        f"GLM provider is ACTIVE but {API_KEY_ENV} is not set.",
        "Set it in the current shell:",
        f'  PowerShell: $env:{API_KEY_ENV} = "<your z.ai key>"',
        f"  bash/zsh:   export {API_KEY_ENV}=<your z.ai key>",
        "or switch back to Anthropic with: claude -glm",
    ])
    if not sys.stdin.isatty():
        return False
    key = _prompt_for_key()
    if not key:
        return False
    os.environ[API_KEY_ENV] = key
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
    reply = input(f"  Save {API_KEY_ENV} to {target.path}? [Y/n] ").strip() or "y"
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
        body = f'$env:{API_KEY_ENV} = "{key}"'
    else:
        body = f'export {API_KEY_ENV}="{key}"'
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
    z.ai rejects it with 401.

    z.ai does serve /v1/models, but every id starts with `glm-` and Claude
    Code's gateway discovery drops ids that do not start with `claude` or
    `anthropic` — so the picker is the three slots plus the one custom entry,
    and `claude --model <id>` is the way to any other GLM model."""
    os.environ.update({
        "ANTHROPIC_BASE_URL": GLM_BASE_URL,
        "ANTHROPIC_AUTH_TOKEN": os.environ[API_KEY_ENV],
        "ANTHROPIC_DEFAULT_OPUS_MODEL": GLM_OPUS_MODEL,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": GLM_DEFAULT_MODEL,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": GLM_SMALL_MODEL,
        "API_TIMEOUT_MS": _API_TIMEOUT_MS,
        **model_picker.custom_option_env(
            config.load().get(_EXTRA_MODEL_KEY, ""), "GLM"
        ),
        "CLAUDE_CONFIG_DIR": str(ensure_config_dir()),
    })
    # A leftover Anthropic key would take precedence over AUTH_TOKEN.
    os.environ.pop("ANTHROPIC_API_KEY", None)


def ensure_config_dir() -> Path:
    """Prepares the isolated Claude config home used by GLM sessions."""
    return claude_config.ensure("glm", "GLM")


def with_default_model(arguments: list[str]) -> list[str]:
    """Prepends `--model <GLM default>` unless the caller already set one —
    otherwise a `model` pinned in settings.json (a claude-* id unknown to
    z.ai) would win over the environment remapping."""
    if any(arg == "--model" or arg.startswith("--model=") for arg in arguments):
        return arguments
    return ["--model", GLM_DEFAULT_MODEL, *arguments]
