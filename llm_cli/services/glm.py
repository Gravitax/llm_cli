"""GLM (z.ai) provider routing for Claude Code — backs the `claude -glm` toggle.

z.ai exposes an Anthropic-compatible endpoint, so switching provider is only a
matter of exporting ANTHROPIC_* overrides before the launch. The active
provider persists in the llm_cli config (CLAUDE_PROVIDER key). The API key is
NEVER persisted: it is read from the GLM_API_KEY environment variable only
(user decision), so the credential never touches a file managed by this tool.
"""

from __future__ import annotations

import os

from llm_cli.services import config, log

GLM_BASE_URL = "https://api.z.ai/api/anthropic"
# The [1m] suffix is required — without it z.ai silently serves a reduced
# context window instead of the model's full 1M tokens.
GLM_DEFAULT_MODEL = "glm-5.2[1m]"
GLM_HAIKU_MODEL = "glm-4.7"

_PROVIDER_KEY = "CLAUDE_PROVIDER"
_API_KEY_ENV = "GLM_API_KEY"
_API_TIMEOUT_MS = "3000000"  # Long agentic turns need it (value from z.ai docs).


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
    """Fails loudly when GLM_API_KEY is missing. Never falls back to the
    Anthropic API silently — that would bill the wrong subscription."""
    if os.environ.get(_API_KEY_ENV):
        return True
    log.red_banner([
        f"GLM provider is ACTIVE but {_API_KEY_ENV} is not set.",
        "Set it in the current shell:",
        f'  PowerShell: $env:{_API_KEY_ENV} = "<your z.ai key>"',
        f"  bash/zsh:   export {_API_KEY_ENV}=<your z.ai key>",
        "(add it to $PROFILE / .bashrc to make it permanent)",
        "or switch back to Anthropic with: claude -glm",
    ])
    return False


def export_env() -> None:
    """Exports the Anthropic-compatible overrides that route Claude Code to
    z.ai. The DEFAULT_*_MODEL variables remap the Opus/Sonnet/Haiku slots so
    the in-session /model picker shows the GLM models."""
    os.environ.update({
        "ANTHROPIC_BASE_URL": GLM_BASE_URL,
        "ANTHROPIC_AUTH_TOKEN": os.environ[_API_KEY_ENV],
        "ANTHROPIC_DEFAULT_OPUS_MODEL": GLM_DEFAULT_MODEL,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": GLM_DEFAULT_MODEL,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": GLM_HAIKU_MODEL,
        "API_TIMEOUT_MS": _API_TIMEOUT_MS,
    })
    # A leftover Anthropic key would take precedence over AUTH_TOKEN.
    os.environ.pop("ANTHROPIC_API_KEY", None)


def with_default_model(arguments: list[str]) -> list[str]:
    """Prepends `--model <GLM default>` unless the caller already set one —
    otherwise a `model` pinned in settings.json (a claude-* id unknown to
    z.ai) would win over the environment remapping."""
    if any(arg == "--model" or arg.startswith("--model=") for arg in arguments):
        return arguments
    return ["--model", GLM_DEFAULT_MODEL, *arguments]
