"""z.ai account API — the model catalog and the Coding Plan quota.

Two separate surfaces, both keyed by GLM_API_KEY:

  * the Anthropic-compatible inference host serves `/v1/models`, the only
    authoritative list of what the plan can address;
  * `api.z.ai/api/monitor/usage/*` reports the Coding Plan quota. It is an
    account API, undocumented by z.ai, and it takes the key as a bare
    `Authorization` value — no `Bearer` prefix, unlike every other z.ai route.

The key is read from the environment, sent once and never logged.
"""

from __future__ import annotations

import datetime
import json
import os
import urllib.error
import urllib.request
from typing import NamedTuple

from llm_cli.services import glm

_MODELS_URL = f"{glm.GLM_BASE_URL}/v1/models"
_QUOTA_URL = "https://api.z.ai/api/monitor/usage/quota/limit"
_TIMEOUT_S = 10
_ANTHROPIC_VERSION = "2023-06-01"

# z.ai encodes each quota window as a (unit, number) pair instead of naming it.
_TOKEN_LIMIT = "TOKENS_LIMIT"
_TOOL_LIMIT = "TIME_LIMIT"
_WINDOW_LABELS = {(3, 5): "Tokens (5 hours)", (6, 1): "Tokens (weekly)"}
_TOOL_LABEL = "MCP tools"
_MILLISECONDS_PER_SECOND = 1000
_RESET_FORMAT = "%Y-%m-%d %H:%M"


class GlmApiError(RuntimeError):
    """Actionable failure — the message is meant for the user, no traceback."""


class QuotaLine(NamedTuple):
    """One quota window, normalized for display."""

    label: str
    percent_used: float
    reset_at: str


class Quota(NamedTuple):
    """The Coding Plan quota as a whole."""

    level: str
    lines: list[QuotaLine]


def list_models() -> list[tuple[str, str]]:
    """(id, display name) of every model the plan can address."""
    payload = _get_json(_MODELS_URL, {"x-api-key": _api_key()})
    models: list[tuple[str, str]] = []
    for entry in payload.get("data", []):
        if not isinstance(entry, dict):
            continue
        model_id = str(entry.get("id") or "").strip()
        if model_id:
            models.append((model_id, str(entry.get("display_name") or "").strip()))
    return models


def quota() -> Quota:
    """The plan level and every quota window z.ai reports."""
    payload = _get_json(_QUOTA_URL, {"Authorization": _api_key()})
    data = payload.get("data")
    if not isinstance(data, dict):
        raise GlmApiError(f"{_QUOTA_URL} returned no quota data.")
    lines = [
        line
        for entry in data.get("limits", [])
        if isinstance(entry, dict)
        for line in (_quota_line(entry),)
        if line is not None
    ]
    return Quota(level=str(data.get("level") or "unknown"), lines=lines)


def _quota_line(entry: dict) -> QuotaLine | None:
    """Normalizes one raw limit entry; None when the shape is unknown.

    `percentage` is the consumed share, not the remaining one — confirmed
    against a tool window reporting 76 of 1000 calls as 7 percent, and against
    a token window at 100 which the inference endpoint rejects with 429.
    """
    percent = float(entry.get("percentage") or 0)
    reset = _format_reset(entry.get("nextResetTime"))
    kind = entry.get("type")
    if kind == _TOOL_LIMIT:
        return QuotaLine(_tool_label(entry), percent, reset)
    if kind != _TOKEN_LIMIT:
        return None
    window = (entry.get("unit"), entry.get("number"))
    label = _WINDOW_LABELS.get(window, f"Tokens (unit={window[0]}, n={window[1]})")
    return QuotaLine(label, percent, reset)


def _tool_label(entry: dict) -> str:
    """The MCP window reports raw call counts; show them when present."""
    used, total = entry.get("currentValue"), entry.get("usage")
    if isinstance(used, int) and isinstance(total, int):
        return f"{_TOOL_LABEL} ({used}/{total} calls)"
    return _TOOL_LABEL


def _format_reset(raw: object) -> str:
    """z.ai timestamps are epoch milliseconds; renders them in local time."""
    if not isinstance(raw, int) or raw <= 0:
        return ""
    moment = datetime.datetime.fromtimestamp(raw / _MILLISECONDS_PER_SECOND)
    return moment.strftime(_RESET_FORMAT)


def _api_key() -> str:
    key = os.environ.get(glm.API_KEY_ENV, "")
    if not key:
        raise GlmApiError(
            f"{glm.API_KEY_ENV} is not set — the z.ai account API cannot be queried."
        )
    return key


def _get_json(url: str, auth_headers: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "anthropic-version": _ANTHROPIC_VERSION,
            **auth_headers,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise GlmApiError(
            f"z.ai refused {url} (HTTP {error.code}) — the key may be invalid "
            "or the plan expired."
        )
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise GlmApiError(f"Could not reach {url}: {error}")
    return payload if isinstance(payload, dict) else {}
