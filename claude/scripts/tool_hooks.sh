#!/bin/bash

# Claude-specific pre-launch checks — sourced by common/lib_cache.sh before each launch.
# Extension point: defines _tool_pre_launch, called if present.

# Repairs the RTK PreToolUse hook if it disappeared from settings.json.
_tool_pre_launch() {
    grep -q "rtk hook claude" "$HOME/.claude/settings.json" 2>/dev/null && return 0
    echo "RTK hook missing — reinstalling..."
    bash "$HOME/.claude/scripts/setup_env.sh"
}
