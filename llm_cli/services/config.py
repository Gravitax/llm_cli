"""Shared llm_cli configuration — enterprise URLs + Atlassian tokens
(port of lib_config.sh / lib_config.ps1).

Single source of truth, written by `setup-atlassian` and read by every consumer:
    CONFLUENCE_URL, JIRA_URL, BITBUCKET_URL, BITBUCKET_USERNAME,
    CONFLUENCE_TOKEN, JIRA_TOKEN, BITBUCKET_TOKEN,
    MCP_REGISTRY_URL (optional), GITHUB_COPILOT_ENTERPRISE_DOMAIN (optional),
    CLAUDE_PROVIDER (optional, "anthropic"|"glm"|"copilot"),
    COPILOT_API_PORT, COPILOT_API_ACCOUNT_TYPE,
    CLAUDE_COPILOT_MODEL, CLAUDE_COPILOT_SMALL_MODEL (optional).
"""

from __future__ import annotations

from pathlib import Path

from llm_cli import paths, platforms
from llm_cli.services import fs


class ConfigMissingError(RuntimeError):
    """Raised when a command cannot run without the Atlassian configuration."""


def load(path: Path | None = None) -> dict[str, str]:
    """Parses the KEY=value config; returns {} when not configured yet."""
    config_file = path or paths.atlassian_env()
    if not config_file.is_file():
        return {}

    values: dict[str, str] = {}
    for line in fs.read_text(config_file).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"')
    return values


def require(path: Path | None = None) -> dict[str, str]:
    """Loads the config or fails loudly — for commands that cannot run without it."""
    values = load(path)
    if not values:
        config_file = path or paths.atlassian_env()
        raise ConfigMissingError(
            f"no config at {config_file} — run `setup-atlassian` first"
        )
    return values


def store(values: dict[str, str], path: Path | None = None) -> Path:
    """Writes the config file with user-only permissions (credentials inside)."""
    config_file = path or paths.atlassian_env()
    body = "".join(f"{key}={value}\n" for key, value in values.items() if value)
    fs.write_text_atomic(config_file, body)
    platforms.current().make_private(config_file)
    return config_file
