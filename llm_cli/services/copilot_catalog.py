"""Copilot model catalog — lists the models the (enterprise) Copilot API serves.

Under the headroom wrap the copilot CLI runs against a custom provider and
cannot enumerate models in-session (`/model` shows nothing), so the pick
happens at launch time. This module answers "which names can I pass to
`copilot --model`?" by querying the catalog directly, replicating headroom's
own token contract:

  1. headroom's saved OAuth token (~/.headroom/copilot_auth.json) is exchanged
     at https://api.<domain>/copilot_internal/v2/token for a short-lived
     Copilot API bearer;
  2. GET <endpoints.api>/models returns the catalog.

Both tokens stay in-process and are never printed or persisted.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from llm_cli.services import headroom

_AUTH_FILE = Path.home() / ".headroom" / "copilot_auth.json"
_CHAT_HEADERS = {
    "Accept": "application/json",
    "Editor-Version": "vscode/1.99",
    "Copilot-Integration-Id": "vscode-chat",
}
_TIMEOUT_S = 15


class CatalogError(RuntimeError):
    """Actionable failure — the message is meant for the user, no traceback."""


def list_models() -> list[tuple[str, str]]:
    """(id, display name) of every model enabled in the Copilot picker."""
    oauth_token, domain = _read_auth()
    bearer, api_url = _exchange_token(oauth_token, domain)
    return _fetch_catalog(bearer, api_url)


def _read_auth() -> tuple[str, str]:
    try:
        auth = json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise CatalogError(
            f"No Copilot OAuth token at {_AUTH_FILE} — run: {headroom.login_hint()}"
        )
    token = str(auth.get("refresh") or "").strip()
    if not token:
        raise CatalogError(
            f"{_AUTH_FILE} holds no reusable token — run: {headroom.login_hint()}"
        )
    domain = str(auth.get("domain") or "").strip() or "github.com"
    return token, domain


def _exchange_token(oauth_token: str, domain: str) -> tuple[str, str]:
    payload = _get_json(f"https://api.{domain}/copilot_internal/v2/token", oauth_token)
    bearer = str(payload.get("token") or "").strip()
    if not bearer:
        raise CatalogError(
            f"Copilot token exchange returned no token — run: {headroom.login_hint()}"
        )
    endpoints = payload.get("endpoints")
    api_url = ""
    if isinstance(endpoints, dict):
        api_url = str(endpoints.get("api") or "").strip().rstrip("/")
    return bearer, api_url or _default_api_url(domain)


def _default_api_url(domain: str) -> str:
    if domain == "github.com":
        return "https://api.githubcopilot.com"
    return f"https://copilot-api.{domain}"


def _fetch_catalog(bearer: str, api_url: str) -> list[tuple[str, str]]:
    payload = _get_json(f"{api_url}/models", bearer)
    models: list[tuple[str, str]] = []
    for entry in payload.get("data", []):
        if not isinstance(entry, dict) or not entry.get("model_picker_enabled"):
            continue
        model_id = str(entry.get("id") or "").strip()
        if model_id:
            models.append((model_id, str(entry.get("name") or "").strip()))
    return models


def _get_json(url: str, bearer: str) -> dict:
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {bearer}", **_CHAT_HEADERS}
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise CatalogError(
            f"Copilot API refused {url} (HTTP {error.code}) — "
            f"token may be stale, run: {headroom.login_hint()}"
        )
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise CatalogError(f"Could not reach {url}: {error}")
    return payload if isinstance(payload, dict) else {}
