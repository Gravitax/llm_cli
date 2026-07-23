"""Persistent provider selection for the Claude Code wrapper."""

from __future__ import annotations

import os
from pathlib import Path

from llm_cli.services import config

ANTHROPIC = "anthropic"
GLM = "glm"
COPILOT = "copilot"

# Everything a GLM or Copilot launch exports to redirect Claude Code. Declared
# once here because the Anthropic path has to undo it: these are read from the
# process environment, so a session started from inside (or after) a redirected
# one inherits the previous provider's endpoint, credential and config home,
# and fails against Anthropic instead of falling back to it.
ROUTING_ENV_VARS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_CUSTOM_MODEL_OPTION",
    "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME",
    "ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
)
_CONFIG_DIR_VAR = "CLAUDE_CONFIG_DIR"
_PROVIDER_KEY = "CLAUDE_PROVIDER"
_KNOWN_PROVIDERS = {ANTHROPIC, GLM, COPILOT}
_LABELS = {
    ANTHROPIC: "Anthropic",
    GLM: "GLM (z.ai)",
    COPILOT: "GitHub Copilot",
}


def active() -> str:
    """Returns the configured provider, defaulting safely to Anthropic."""
    provider = config.load().get(_PROVIDER_KEY, ANTHROPIC)
    return provider if provider in _KNOWN_PROVIDERS else ANTHROPIC


def is_active(provider: str) -> bool:
    return active() == provider


def reset_env() -> None:
    """Clears the routing an alternate provider may have left in the
    environment, so an Anthropic launch always reaches api.anthropic.com with
    the Anthropic credentials — inheriting them is silent, and the session only
    fails once it calls the API."""
    for name in ROUTING_ENV_VARS:
        os.environ.pop(name, None)
    if _config_dir_is_ours():
        os.environ.pop(_CONFIG_DIR_VAR, None)


def _config_dir_is_ours() -> bool:
    """True when CLAUDE_CONFIG_DIR points at a home this tool generates. A
    config dir set by the user for their own reasons is left untouched."""
    current = os.environ.get(_CONFIG_DIR_VAR, "")
    if not current:
        return False
    ours = {Path.home() / f".claude-{name}" for name in (GLM, COPILOT)}
    try:
        return Path(current).resolve() in {path.resolve() for path in ours}
    except OSError:
        return False


def toggle(provider: str) -> bool:
    """Toggles one alternate provider against Anthropic."""
    if provider not in (GLM, COPILOT):
        raise ValueError(f"unsupported Claude provider: {provider}")
    activated = active() != provider
    selected = provider if activated else ANTHROPIC
    values = config.load()
    values[_PROVIDER_KEY] = selected
    config.store(values)
    print(f"Provider switched to {_LABELS[selected]}.")
    return activated
