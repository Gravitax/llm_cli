#!/bin/bash

# Resolves tool-specific paths and feature flags from TOOL_PROFILE (claude | copilot).
# Must be sourced. Resolution order:
#   1. profile.env next to this file (written by setup_scripts_sync.sh at install time)
#   2. TOOL_PROFILE environment variable (exported by the env orchestrators)
# profile.env wins so that an installed copy always targets its own tool home,
# even if another tool's profile is still exported in the shell.

_TOOL_PROFILE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

if [ -f "$_TOOL_PROFILE_DIR/profile.env" ]; then
    source "$_TOOL_PROFILE_DIR/profile.env"
fi

case "$TOOL_PROFILE" in
    claude)
        TOOL_NAME="claude"
        TOOL_HOME="$HOME/.claude"
        TOOL_INSTRUCTIONS_GLOBAL="$TOOL_HOME/CLAUDE.md"
        TOOL_INSTRUCTIONS_LOCAL="CLAUDE.md"
        TOOL_IGNORE_FILE=".claudeignore"
        # Claude Code supports settings.json hooks: RTK PreToolUse + cache PostToolUse.
        TOOL_HAS_RTK_HOOK=1
        TOOL_HAS_AGENT_HOOKS=1
        # Headroom writes a durable proxy wrap into settings.json (ANTHROPIC_BASE_URL).
        TOOL_HAS_HEADROOM=1
        ;;
    copilot)
        TOOL_NAME="copilot"
        TOOL_HOME="$HOME/.copilot"
        TOOL_INSTRUCTIONS_GLOBAL="$TOOL_HOME/copilot-instructions.md"
        TOOL_INSTRUCTIONS_LOCAL="AGENTS.md"
        TOOL_IGNORE_FILE=".copilotignore"
        # Copilot CLI has no PreToolUse/PostToolUse hook system.
        TOOL_HAS_RTK_HOOK=0
        TOOL_HAS_AGENT_HOOKS=0
        # Headroom's durable wrap mechanism for Copilot is unverified — keep off.
        TOOL_HAS_HEADROOM=0
        ;;
    *)
        echo "Error: TOOL_PROFILE must be 'claude' or 'copilot' (got: '${TOOL_PROFILE:-unset}')." >&2
        return 1 2>/dev/null || exit 1
        ;;
esac

export TOOL_PROFILE TOOL_NAME TOOL_HOME
export TOOL_INSTRUCTIONS_GLOBAL TOOL_INSTRUCTIONS_LOCAL TOOL_IGNORE_FILE
export TOOL_HAS_RTK_HOOK TOOL_HAS_AGENT_HOOKS TOOL_HAS_HEADROOM
