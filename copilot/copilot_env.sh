#!/bin/bash

# Orchestrator — installs and activates the GitHub Copilot CLI token-optimization layer.
#
# Usage:
#   source copilot_env.sh

# BASH_SOURCE[0] is empty in zsh when sourcing — fall back to $0 which zsh populates correctly.
_SELF="${BASH_SOURCE[0]:-$0}"
COPILOT_DIR="$(cd "$(dirname "$_SELF")" && pwd)"
COMMON_DIR="$(cd "$COPILOT_DIR/.." && pwd)/common"

export TOOL_PROFILE=copilot
source "$COMMON_DIR/tool_profile.sh" || return 1

if ! command -v copilot > /dev/null 2>&1; then
    echo "Error: Copilot CLI not found. Install it with: npm install -g @github/copilot"
    return 1
fi

bash "$COMMON_DIR/setup_env.sh"
bash "$COMMON_DIR/setup_shell_wrapper.sh"

# Load the project-local .mcp.json in prompt mode too (interactive mode loads it by default).
export GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP=true

copilot() {
    # Source the INSTALLED lib: its profile.env pins the copilot profile even if
    # another tool's env script was sourced last in this shell.
    source "$HOME/.copilot/scripts/lib_cache.sh"
    _check_and_build_cache
    echo "Starting Copilot..."
    command copilot "$@"
}
unalias copilot 2>/dev/null

echo "Ready. Run: copilot"
