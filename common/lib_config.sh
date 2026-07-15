#!/bin/bash

# Shared llm_cli configuration (enterprise URLs + Atlassian tokens) — must be sourced.
# Single source of truth, written by setup_atlassian.sh and read by every consumer:
#   CONFLUENCE_URL, JIRA_URL, BITBUCKET_URL, BITBUCKET_USERNAME,
#   CONFLUENCE_TOKEN, JIRA_TOKEN, BITBUCKET_TOKEN, MCP_REGISTRY_URL (optional).

LLM_CLI_CONFIG="$HOME/.config/llm_cli/atlassian.env"

# Loads the config into the current shell. Returns 1 if not configured yet.
load_llm_cli_config() {
    [ -f "$LLM_CLI_CONFIG" ] || return 1
    source "$LLM_CLI_CONFIG"
}

# Loads the config or fails loudly — for scripts that cannot run without it.
require_llm_cli_config() {
    if ! load_llm_cli_config; then
        echo "    [ERROR] No config at $LLM_CLI_CONFIG — run setup_atlassian.sh first." >&2
        return 1
    fi
}
