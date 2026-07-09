#!/bin/bash

# Enables the Atlassian + Bitbucket MCP servers GLOBALLY, once, for both
# Claude Code and Copilot CLI (user-scope registration — active in every
# project/session for this user).
#
# Global scope means the ~150 tool definitions are injected into every
# session, regardless of whether that project touches Jira/Confluence/
# Bitbucket. This is a deliberate tradeoff in favor of a one-time init over
# per-project token economy.
#
# Credentials come from ~/.config/llm_cli/atlassian.env (written by
# setup_atlassian.sh). Config is written directly (not via `claude mcp
# add-json` / `copilot mcp add --env`) so tokens never pass through argv
# (visible in `ps`).
#
# Usage:
#   bash setup_mcp_global.sh      # enable MCP globally (idempotent)
#   bash setup_mcp_global.sh -u   # remove the global MCP registration

CREDS_FILE="$HOME/.config/llm_cli/atlassian.env"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
CLAUDE_CONFIG="$HOME/.claude.json"
COPILOT_CONFIG="$HOME/.copilot/mcp-config.json"

# Server names MUST be the exact IDs from the enterprise MCP registry
# (mcp-registry.exail.com): Copilot's "Registry only" allowlist policy matches
# on server name only. Claude Code has no such policy and accepts any name.
SERVER_JIRA="io.github.b1ff/atlassian-dc-mcp-jira"
SERVER_CONFLUENCE="io.github.b1ff/atlassian-dc-mcp-confluence"
SERVER_BITBUCKET="io.github.b1ff/atlassian-dc-mcp-bitbucket"

write_mcp_config() {
    local config_file="$1"

    if [ ! -f "$CREDS_FILE" ]; then
        echo "    [ERROR] $CREDS_FILE not found. Run setup_atlassian.sh first."
        exit 1
    fi

    # shellcheck source=/dev/null
    source "$CREDS_FILE"

    mkdir -p "$(dirname "$config_file")"

    # Tokens go through the environment, never through argv (visible in ps).
    CONFLUENCE_URL="$CONFLUENCE_URL" JIRA_URL="$JIRA_URL" BITBUCKET_URL="$BITBUCKET_URL" \
    BITBUCKET_USERNAME="$BITBUCKET_USERNAME" CONFLUENCE_TOKEN="$CONFLUENCE_TOKEN" \
    JIRA_TOKEN="$JIRA_TOKEN" BITBUCKET_TOKEN="$BITBUCKET_TOKEN" \
    SERVER_JIRA="$SERVER_JIRA" SERVER_CONFLUENCE="$SERVER_CONFLUENCE" SERVER_BITBUCKET="$SERVER_BITBUCKET" \
    $PYTHON_BIN - "$config_file" << 'PYEOF'
import json, os, sys

config_file = sys.argv[1]
env = os.environ

# Packages and env vars mirror the registry entries (version pinned to registry).
new_servers = {
    env["SERVER_JIRA"]: {
        "command": "npx",
        "args": ["-y", "@atlassian-dc-mcp/jira@0.19.0"],
        "env": {
            "JIRA_HOST": env["JIRA_URL"],
            "JIRA_API_TOKEN": env["JIRA_TOKEN"],
        },
    },
    env["SERVER_CONFLUENCE"]: {
        "command": "npx",
        "args": ["-y", "@atlassian-dc-mcp/confluence@0.19.0"],
        "env": {
            # Confluence is served on a subpath, so the full API base path is
            # required (CONFLUENCE_HOST would be ignored).
            "CONFLUENCE_API_BASE_PATH": env["CONFLUENCE_URL"] + "/rest",
            "CONFLUENCE_API_TOKEN": env["CONFLUENCE_TOKEN"],
        },
    },
    env["SERVER_BITBUCKET"]: {
        "command": "npx",
        "args": ["-y", "@atlassian-dc-mcp/bitbucket@0.19.0"],
        "env": {
            "BITBUCKET_HOST": env["BITBUCKET_URL"],
            "BITBUCKET_API_BASE_PATH": env["BITBUCKET_URL"] + "/rest/api/latest/",
            "BITBUCKET_API_TOKEN": env["BITBUCKET_TOKEN"],
        },
    },
}

# Preserve unrelated servers if the config already exists, but drop the
# legacy names this script used to manage.
try:
    existing = json.load(open(config_file))
except (FileNotFoundError, json.JSONDecodeError):
    existing = {}

servers = existing.setdefault("mcpServers", {})
for legacy in ("mcp-atlassian", "bitbucket"):
    servers.pop(legacy, None)
servers.update(new_servers)

with open(config_file, "w") as f:
    json.dump(existing, f, indent=2)
    f.write("\n")
PYEOF
    chmod 600 "$config_file"
}

enable_global_mcp() {
    if command -v claude > /dev/null 2>&1 || [ -d "$HOME/.claude" ]; then
        write_mcp_config "$CLAUDE_CONFIG"
        echo "    [OK] Atlassian + Bitbucket MCP registered globally for claude (user scope: $CLAUDE_CONFIG)."
    fi

    if command -v copilot > /dev/null 2>&1 || [ -d "$HOME/.copilot" ]; then
        write_mcp_config "$COPILOT_CONFIG"
        echo "    [OK] Atlassian + Bitbucket MCP registered globally for copilot (user config: $COPILOT_CONFIG)."
    fi
}

remove_servers_from() {
    local config_file="$1"
    [ -f "$config_file" ] || { echo "    [OK] No config found at $config_file."; return 0; }

    SERVER_JIRA="$SERVER_JIRA" SERVER_CONFLUENCE="$SERVER_CONFLUENCE" SERVER_BITBUCKET="$SERVER_BITBUCKET" \
    $PYTHON_BIN - "$config_file" << 'PYEOF'
import json, os, sys

config_file = sys.argv[1]
env = os.environ

with open(config_file) as f:
    config = json.load(f)

servers = config.get("mcpServers", {})
for name in (
    env["SERVER_JIRA"],
    env["SERVER_CONFLUENCE"],
    env["SERVER_BITBUCKET"],
    "mcp-atlassian",
    "bitbucket",
):
    servers.pop(name, None)

with open(config_file, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print("    [OK] Atlassian servers removed from " + config_file + ", other entries kept.")
PYEOF
}

disable_global_mcp() {
    remove_servers_from "$CLAUDE_CONFIG"
    remove_servers_from "$COPILOT_CONFIG"
}

if [ "$1" = "-u" ]; then
    echo "Removing global MCP configuration..."
    disable_global_mcp
else
    echo "Enabling Atlassian + Bitbucket MCP globally (user scope)..."
    enable_global_mcp
fi
