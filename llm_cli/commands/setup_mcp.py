"""setup-mcp — registers the Atlassian + Bitbucket MCP servers GLOBALLY, once,
for both Claude Code and Copilot CLI (port of setup_mcp_global.sh; now also
available on Windows).

Global scope means the ~150 tool definitions are injected into every session —
a deliberate tradeoff in favor of a one-time init over per-project token economy.
Config files are written directly (not via `claude mcp add-json`) so tokens
never pass through argv (visible in `ps`).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from llm_cli import paths, platforms
from llm_cli.services import config, log, settings_editor

# Server names MUST be the exact IDs from the enterprise MCP registry (if any):
# Copilot's "Registry only" allowlist policy matches on server name only.
SERVER_JIRA = "io.github.b1ff/atlassian-dc-mcp-jira"
SERVER_CONFLUENCE = "io.github.b1ff/atlassian-dc-mcp-confluence"
SERVER_BITBUCKET = "io.github.b1ff/atlassian-dc-mcp-bitbucket"
_LEGACY_SERVER_NAMES = ("mcp-atlassian", "bitbucket")
_MCP_PACKAGE_VERSION = "0.19.0"  # Pinned to the registry entries.


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-mcp", help="register Atlassian+Bitbucket MCP globally (-u to remove)"
    )
    parser.add_argument(
        "-u", "--remove", action="store_true", help="remove the global registration"
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    if args.remove:
        print("Removing global MCP configuration...")
        for config_file, _ in _tool_configs(installed_only=False):
            _remove_servers(config_file)
        return 0
    print("Enabling Atlassian + Bitbucket MCP globally (user scope)...")
    return _enable_global_mcp()


def _tool_configs(installed_only: bool = True) -> list[tuple[Path, str]]:
    """(config_file, tool_name) pairs; filtered to installed tools when asked.

    Claude and Copilot keep MCP in a dedicated config; opencode stores it under
    the `mcp` key of its own opencode.json (a different shape — see below)."""
    entries = [
        (paths.home() / ".claude.json", "claude"),
        (paths.home() / ".copilot" / "mcp-config.json", "copilot"),
        (paths.home() / ".config" / "opencode" / "opencode.json", "opencode"),
    ]
    if not installed_only:
        return entries
    return [
        (config_file, tool)
        for config_file, tool in entries
        if shutil.which(tool) or (paths.home() / f".{tool}").is_dir()
    ]


def _enable_global_mcp() -> int:
    try:
        credentials = config.require()
    except config.ConfigMissingError as error:
        log.print_err(str(error))
        return 1
    for config_file, tool in _tool_configs():
        if tool == "opencode":
            _write_servers_opencode(config_file, credentials)
        else:
            _write_servers(config_file, credentials)
        log.print_ok(
            f"Atlassian + Bitbucket MCP registered globally for {tool} "
            f"(user scope: {config_file})."
        )
    return 0


def _server_definitions(credentials: dict[str, str]) -> dict[str, dict]:
    version = _MCP_PACKAGE_VERSION
    return {
        SERVER_JIRA: {
            "command": "npx",
            "args": ["-y", f"@atlassian-dc-mcp/jira@{version}"],
            "env": {
                "JIRA_HOST": credentials["JIRA_URL"],
                "JIRA_API_TOKEN": credentials["JIRA_TOKEN"],
            },
        },
        SERVER_CONFLUENCE: {
            "command": "npx",
            "args": ["-y", f"@atlassian-dc-mcp/confluence@{version}"],
            "env": {
                # Confluence is served on a subpath, so the full API base path
                # is required (CONFLUENCE_HOST would be ignored).
                "CONFLUENCE_API_BASE_PATH": credentials["CONFLUENCE_URL"] + "/rest",
                "CONFLUENCE_API_TOKEN": credentials["CONFLUENCE_TOKEN"],
            },
        },
        SERVER_BITBUCKET: {
            "command": "npx",
            "args": ["-y", f"@atlassian-dc-mcp/bitbucket@{version}"],
            "env": {
                "BITBUCKET_HOST": credentials["BITBUCKET_URL"],
                "BITBUCKET_API_BASE_PATH": credentials["BITBUCKET_URL"] + "/rest/api/latest/",
                "BITBUCKET_API_TOKEN": credentials["BITBUCKET_TOKEN"],
            },
        },
    }


def _opencode_server_definitions(credentials: dict[str, str]) -> dict[str, dict]:
    """opencode's MCP shape: `mcp.<name> = {type, command[], env, enabled}`,
    where `command` is a flat argv array (no separate command/args split)."""
    flat = {}
    for name, definition in _server_definitions(credentials).items():
        flat[name] = {
            "type": "local",
            "command": [definition["command"], *definition["args"]],
            "enabled": True,
            "env": definition["env"],
        }
    return flat


def _write_servers(config_file: Path, credentials: dict[str, str]) -> None:
    """Upserts our servers, preserving unrelated entries and dropping legacy names."""
    existing = settings_editor.load_json(config_file)
    servers = existing.setdefault("mcpServers", {})
    for legacy in _LEGACY_SERVER_NAMES:
        servers.pop(legacy, None)
    servers.update(_server_definitions(credentials))
    settings_editor.save_json(config_file, existing, backup=False)
    platforms.current().make_private(config_file)


def _write_servers_opencode(config_file: Path, credentials: dict[str, str]) -> None:
    """opencode variant: servers live under the `mcp` key with a different shape
    (type/command[]/env). Unrelated config (provider, model, ...) is preserved."""
    existing = settings_editor.load_json(config_file)
    servers = existing.setdefault("mcp", {})
    for legacy in _LEGACY_SERVER_NAMES:
        servers.pop(legacy, None)
    servers.update(_opencode_server_definitions(credentials))
    settings_editor.save_json(config_file, existing, backup=False)
    platforms.current().make_private(config_file)


def _remove_servers(config_file: Path) -> None:
    if not config_file.is_file():
        log.print_ok(f"No config found at {config_file}.")
        return
    existing = settings_editor.load_json(config_file)
    removed = False
    # Claude/Copilot use "mcpServers"; opencode uses "mcp" — clear both shapes.
    for key in ("mcpServers", "mcp"):
        servers = existing.get(key, {})
        for name in (SERVER_JIRA, SERVER_CONFLUENCE, SERVER_BITBUCKET, *_LEGACY_SERVER_NAMES):
            if name in servers:
                servers.pop(name, None)
                removed = True
    settings_editor.save_json(config_file, existing, backup=False)
    if removed:
        log.print_ok(f"Atlassian servers removed from {config_file}, other entries kept.")
    else:
        log.print_ok(f"No Atlassian servers found in {config_file}.")
