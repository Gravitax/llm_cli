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
source "$COMMON_DIR/tool_profile.sh"                 || return 1
source "$COMMON_DIR/lib_deps.sh"                     || return 1
source "$COPILOT_DIR/scripts/setup_prerequisites.sh" || return 1

bash "$COMMON_DIR/setup_env.sh"
bash "$COMMON_DIR/setup_shell_wrapper.sh"

# Load the project-local .mcp.json in prompt mode too (interactive mode loads it by default).
export GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP=true

copilot() {
    # Source the INSTALLED lib: its profile.env pins the copilot profile even if
    # another tool's env script was sourced last in this shell.
    source "$HOME/.copilot/scripts/lib_cache.sh"
    _check_and_build_cache
    source "$HOME/.copilot/scripts/lib_headroom.sh"
    echo "Starting Copilot..."
    # Routes through headroom when a provider key or Copilot OAuth allows it,
    # plain launch otherwise. Opt out per session with LLM_CLI_NO_HEADROOM=1.
    _launch_with_headroom copilot "$@"
}
unalias copilot 2>/dev/null

# Surface the exact OAuth commands (red banner) whenever compression would stay idle.
if command -v headroom > /dev/null 2>&1; then
    source "$HOME/.copilot/scripts/lib_headroom.sh"
    _headroom_export_ghe_env
    if ! _headroom_copilot_mode > /dev/null 2>&1; then
        _headroom_print_login_warning
    fi
fi

echo "Ready. Run: copilot"
