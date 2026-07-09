#!/bin/bash

# Enables the Atlassian + Bitbucket MCP servers for ONE project by writing a
# local .mcp.json (read by both Claude Code and Copilot CLI).
#
# Per-project instead of user scope: the ~150 MCP tool definitions are injected
# into every session of a registered scope, costing tens of thousands of tokens.
# With .mcp.json they only load in projects that actually use Atlassian.
#
# Credentials come from ~/.config/llm_cli/atlassian.env (written by
# setup_atlassian.sh). The generated .mcp.json contains tokens, so it is
# excluded from git via .git/info/exclude (local, never committed).
#
# Usage:
#   bash setup_mcp_project.sh [project_path]      # enable MCP for the project
#   bash setup_mcp_project.sh -u [project_path]   # remove the project .mcp.json

CREDS_FILE="$HOME/.config/llm_cli/atlassian.env"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

# Excludes a file from git locally (works without touching the committed .gitignore).
exclude_from_git() {
    local project_path="$1" pattern="$2"
    local exclude_file="$project_path/.git/info/exclude"
    [ -d "$project_path/.git" ] || return 0
    mkdir -p "$(dirname "$exclude_file")"
    grep -qxF "$pattern" "$exclude_file" 2>/dev/null || echo "$pattern" >> "$exclude_file"
}

write_mcp_json() {
    local project_path="$1"
    local mcp_file="$project_path/.mcp.json"

    if [ ! -f "$CREDS_FILE" ]; then
        echo "    [ERROR] $CREDS_FILE not found. Run setup_atlassian.sh first."
        exit 1
    fi

    # shellcheck source=/dev/null
    source "$CREDS_FILE"

    # Tokens go through the environment, never through argv (visible in ps).
    CONFLUENCE_URL="$CONFLUENCE_URL" JIRA_URL="$JIRA_URL" BITBUCKET_URL="$BITBUCKET_URL" \
    BITBUCKET_USERNAME="$BITBUCKET_USERNAME" CONFLUENCE_TOKEN="$CONFLUENCE_TOKEN" \
    JIRA_TOKEN="$JIRA_TOKEN" BITBUCKET_TOKEN="$BITBUCKET_TOKEN" \
    $PYTHON_BIN - "$mcp_file" << 'PYEOF'
import json, os, sys

mcp_file = sys.argv[1]
env = os.environ

# Server names MUST be the exact IDs from the enterprise MCP registry
# (mcp-registry.exail.com): Copilot's "Registry only" allowlist policy matches
# on server name only. Claude Code has no such policy and accepts any name.
# Packages and env vars mirror the registry entries (version pinned to registry).
config = {
    "mcpServers": {
        "io.github.b1ff/atlassian-dc-mcp-jira": {
            "command": "npx",
            "args": ["-y", "@atlassian-dc-mcp/jira@0.19.0"],
            "env": {
                "JIRA_HOST": env["JIRA_URL"],
                "JIRA_API_TOKEN": env["JIRA_TOKEN"],
            },
        },
        "io.github.b1ff/atlassian-dc-mcp-confluence": {
            "command": "npx",
            "args": ["-y", "@atlassian-dc-mcp/confluence@0.19.0"],
            "env": {
                # Confluence is served on a subpath, so the full API base path is
                # required (CONFLUENCE_HOST would be ignored).
                "CONFLUENCE_API_BASE_PATH": env["CONFLUENCE_URL"] + "/rest",
                "CONFLUENCE_API_TOKEN": env["CONFLUENCE_TOKEN"],
            },
        },
        "io.github.b1ff/atlassian-dc-mcp-bitbucket": {
            "command": "npx",
            "args": ["-y", "@atlassian-dc-mcp/bitbucket@0.19.0"],
            "env": {
                "BITBUCKET_HOST": env["BITBUCKET_URL"],
                "BITBUCKET_API_BASE_PATH": env["BITBUCKET_URL"] + "/rest/api/latest/",
                "BITBUCKET_API_TOKEN": env["BITBUCKET_TOKEN"],
            },
        },
    }
}

# Preserve unrelated servers if a .mcp.json already exists, but drop the
# legacy names this script used to manage (blocked by the Copilot allowlist).
try:
    existing = json.load(open(mcp_file))
    servers = existing.setdefault("mcpServers", {})
    for legacy in ("mcp-atlassian", "bitbucket"):
        servers.pop(legacy, None)
    servers.update(config["mcpServers"])
    config = existing
except (FileNotFoundError, json.JSONDecodeError):
    pass

with open(mcp_file, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PYEOF
    chmod 600 "$mcp_file"

    exclude_from_git "$project_path" ".mcp.json"

    echo "    [OK] .mcp.json written at $mcp_file (git-excluded locally)."
    echo "    [OK] Atlassian + Bitbucket MCP active in this project for claude and copilot."
}

remove_mcp_json() {
    local project_path="$1"
    local mcp_file="$project_path/.mcp.json"

    if [ ! -f "$mcp_file" ]; then
        echo "    [OK] No .mcp.json found at $project_path."
        return 0
    fi

    # Only remove the servers this script manages; keep any others.
    $PYTHON_BIN - "$mcp_file" << 'PYEOF'
import json, os, sys
mcp_file = sys.argv[1]
config = json.load(open(mcp_file))
servers = config.get("mcpServers", {})
# Current registry-named servers + legacy names from earlier versions.
for name in (
    "io.github.b1ff/atlassian-dc-mcp-jira",
    "io.github.b1ff/atlassian-dc-mcp-confluence",
    "io.github.b1ff/atlassian-dc-mcp-bitbucket",
    "mcp-atlassian",
    "bitbucket",
):
    servers.pop(name, None)
if servers:
    with open(mcp_file, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    print("    [OK] Atlassian servers removed, other servers kept.")
else:
    os.remove(mcp_file)
    print("    [OK] .mcp.json removed.")
PYEOF
}

if [ "$1" = "-u" ]; then
    project_path="$(cd "${2:-$PWD}" && pwd)"
    echo "Removing project MCP configuration..."
    remove_mcp_json "$project_path"
else
    project_path="$(cd "${1:-$PWD}" && pwd)"
    echo "Enabling Atlassian + Bitbucket MCP for $project_path..."
    write_mcp_json "$project_path"
fi
