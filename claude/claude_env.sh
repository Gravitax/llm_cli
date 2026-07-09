#!/bin/bash

# Orchestrator — installs and activates the Claude Code token-optimization layer.
#
# Usage:
#   source claude_env.sh

# BASH_SOURCE[0] is empty in zsh when sourcing — fall back to $0 which zsh populates correctly.
_SELF="${BASH_SOURCE[0]:-$0}"
CLAUDE_DIR="$(cd "$(dirname "$_SELF")" && pwd)"
COMMON_DIR="$(cd "$CLAUDE_DIR/.." && pwd)/common"

export TOOL_PROFILE=claude
source "$COMMON_DIR/tool_profile.sh"                || return 1
source "$CLAUDE_DIR/scripts/setup_prerequisites.sh" || return 1

bash "$COMMON_DIR/setup_env.sh"
bash "$COMMON_DIR/setup_shell_wrapper.sh"

claude() {
    # Source the INSTALLED lib: its profile.env pins the claude profile even if
    # another tool's env script was sourced last in this shell.
    source "$HOME/.claude/scripts/lib_cache.sh"
    _check_and_build_cache
    echo "Starting Claude..."
    command claude "$@"
}
unalias claude 2>/dev/null

echo "Ready. Run: claude"
