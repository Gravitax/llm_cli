#!/bin/bash

# Repairs the tool environment: scripts sync, global instructions, tool-specific hooks.
# When run from the source repo: full setup (sync + instructions + hooks).
# When run from $TOOL_HOME/scripts/: skips the sync (repo layout required) and
# repairs what can be repaired in place (RTK hook, PostToolUse hooks).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/tool_profile.sh" || exit 1

# Sync and instructions rewrite require the source repo layout (common/ + overlay).
if [ "$(basename "$SCRIPT_DIR")" = "common" ]; then
    bash "$SCRIPT_DIR/setup_scripts_sync.sh"
    bash "$SCRIPT_DIR/setup_context.sh"
else
    bash "$SCRIPT_DIR/setup_context.sh"
fi

# Registers a PostToolUse hook in the tool settings if not already present.
# $1 — tool matcher (e.g. "Bash", "Write")
# $2 — script filename in $TOOL_HOME/scripts/ (e.g. "cache_refresh_on_git.sh")
registerPostToolUseHook() {
    local matcher="$1"
    local script_name="$2"
    local hook_cmd="bash \$HOME/.$TOOL_NAME/scripts/$script_name"
    local settings="$TOOL_HOME/settings.json"

    if grep -qF "$script_name" "$settings" 2>/dev/null; then
        echo "    [OK] PostToolUse $matcher hook ($script_name) already registered."
        return
    fi

    if ! command -v jq > /dev/null 2>&1; then
        echo "    [WARN] jq not found — PostToolUse $matcher hook not registered."
        return
    fi

    local tmp
    tmp=$(mktemp)
    jq --arg matcher "$matcher" --arg cmd "$hook_cmd" '
        .hooks.PostToolUse //= [] |
        .hooks.PostToolUse += [{"matcher": $matcher, "hooks": [{"type": "command", "command": $cmd}]}]
    ' "$settings" > "$tmp" && mv "$tmp" "$settings"

    echo "    [OK] PostToolUse $matcher hook ($script_name) registered in $settings"
}

# Allows reading the context cache without a permission prompt (Claude only).
# The cache lives outside the project (~/.claude/projects/), which Claude Code
# treats as out-of-workspace and would otherwise prompt for on every session.
ensure_cache_read_permission() {
    local settings="$TOOL_HOME/settings.json"
    local rule="Read(~/.$TOOL_NAME/projects/**)"

    if grep -qF "$rule" "$settings" 2>/dev/null; then
        return
    fi

    if ! command -v jq > /dev/null 2>&1; then
        echo "    [WARN] jq not found — cache read permission not registered."
        return
    fi

    local tmp
    tmp=$(mktemp)
    jq --arg rule "$rule" '
        .permissions //= {} |
        .permissions.allow //= [] |
        .permissions.allow += [$rule]
    ' "$settings" > "$tmp" && mv "$tmp" "$settings"

    echo "    [OK] Cache read permission ($rule) registered in $settings"
}

# Ensures the RTK PreToolUse hook is active (feature-gated: Claude only).
ensure_rtk_hook() {
    if ! grep -q "rtk hook $TOOL_NAME" "$TOOL_HOME/settings.json" 2>/dev/null; then
        bash "$TOOL_HOME/scripts/setup_rtk.sh"
    elif ! command -v jq > /dev/null 2>&1; then
        echo "    [WARN] jq not found — RTK hook registered but inactive."
        echo "    Fix: sudo apt-get install -y jq"
    fi
}

if [ "$TOOL_HAS_RTK_HOOK" = "1" ]; then
    ensure_rtk_hook
fi

if [ "$TOOL_HAS_AGENT_HOOKS" = "1" ]; then
    registerPostToolUseHook "Bash"  "cache_refresh_on_git.sh"
    registerPostToolUseHook "Write" "cache_refresh_on_write.sh"
    ensure_cache_read_permission
fi

if [ "$TOOL_HAS_HEADROOM" = "1" ]; then
    bash "$SCRIPT_DIR/setup_headroom.sh" --ensure
fi

echo "    [OK] $TOOL_NAME environment ready."
