"""Persistent provider selection for the Claude Code wrapper."""

from __future__ import annotations

from llm_cli.services import config

ANTHROPIC = "anthropic"
GLM = "glm"
COPILOT = "copilot"

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
