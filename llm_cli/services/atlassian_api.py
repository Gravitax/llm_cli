"""Atlassian Data Center REST calls for token validation (replaces the
curl + node heredoc dance of setup_atlassian.sh).

Tokens travel only in the Authorization header — never in argv or logs.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

_TIMEOUT_S = 8


class TokenValidationError(RuntimeError):
    """Raised with a user-facing message when a token cannot be validated."""


def get_json(url: str, token: str) -> dict:
    """Authenticated GET returning the parsed JSON body."""
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    # create_default_context honors SSL_CERT_FILE/SSL_CERT_DIR — the escape
    # hatch for corporate CA bundles.
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise TokenValidationError(_http_message(error.code, url)) from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, ssl.SSLError):
            raise TokenValidationError(
                f"TLS failure reaching {url} — behind a corporate CA? "
                "Point SSL_CERT_FILE at your CA bundle."
            ) from error
        raise TokenValidationError(
            f"Cannot reach {url}. Check your network connection."
        ) from error


def validate_confluence(base_url: str, token: str) -> str:
    data = get_json(f"{base_url}/rest/api/user/current", token)
    return data.get("displayName", "unknown")


def validate_jira(base_url: str, token: str) -> str:
    data = get_json(f"{base_url}/rest/api/2/myself", token)
    return data.get("displayName", "unknown")


def validate_bitbucket(base_url: str, token: str) -> str:
    data = get_json(f"{base_url}/rest/api/1.0/projects?limit=1", token)
    if data.get("values"):
        return "token OK"
    return "token OK (no projects visible)"


def _http_message(code: int, url: str) -> str:
    if code == 401:
        return "Token rejected (401). It may have expired or been revoked."
    if code == 403:
        return "Access forbidden (403). Insufficient permissions."
    return f"Unexpected HTTP {code} from {url}."
