"""Anthropic model catalog.

`GET /v1/models` on the Anthropic API needs an API key. A claude.ai
subscription login has none — the OAuth session lives inside Claude Code and is
deliberately not read here — so the catalog is only listable when the user
brings their own key. Everything else falls back to the aliases Claude Code
resolves on its own, which is what its /model picker shows.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_DEFAULT_BASE_URL = "https://api.anthropic.com"
_KEY_ENVS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_BASE_URL_ENV = "ANTHROPIC_BASE_URL"
_ANTHROPIC_VERSION = "2023-06-01"
_TIMEOUT_S = 10
_PAGE_LIMIT = 1000

# Claude Code resolves these itself; they need no API call and stay valid on a
# subscription login. Descriptions match what the /model picker shows.
ALIASES = (
    ("default", "Recommended model for daily use"),
    ("opus", "Most capable model"),
    ("sonnet", "Balanced capability and speed"),
    ("haiku", "Fastest model, background tasks"),
    ("opusplan", "Opus while planning, Sonnet to execute"),
)


class AnthropicApiError(RuntimeError):
    """Actionable failure — the message is meant for the user, no traceback."""


def has_api_key() -> bool:
    """True when a key is available to list the catalog for real."""
    return bool(_api_key())


def list_models() -> list[tuple[str, str]]:
    """(id, display name) of every model the configured key can address."""
    key = _api_key()
    if not key:
        raise AnthropicApiError(
            "No API key in the environment — the claude.ai subscription login "
            "cannot list the catalog."
        )
    base = os.environ.get(_BASE_URL_ENV, "").rstrip("/") or _DEFAULT_BASE_URL
    payload = _get_json(f"{base}/v1/models?limit={_PAGE_LIMIT}", key)
    models: list[tuple[str, str]] = []
    for entry in payload.get("data", []):
        if not isinstance(entry, dict):
            continue
        model_id = str(entry.get("id") or "").strip()
        if model_id:
            models.append((model_id, str(entry.get("display_name") or "").strip()))
    return models


def _api_key() -> str:
    for name in _KEY_ENVS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _get_json(url: str, key: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "x-api-key": key,
            "anthropic-version": _ANTHROPIC_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise AnthropicApiError(
            f"Anthropic refused {url} (HTTP {error.code}) — the key may be "
            "invalid or lack model access."
        )
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise AnthropicApiError(f"Could not reach {url}: {error}")
    return payload if isinstance(payload, dict) else {}
