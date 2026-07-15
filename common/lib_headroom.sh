#!/bin/bash

# Headroom proxy helpers — must be sourced.
# Shared by setup_headroom.sh, check_optimizations.sh and the shell wrappers.
# Tool paths come from tool_profile.sh (profile.env at install time, TOOL_PROFILE in repo).

_LIB_HEADROOM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "$_LIB_HEADROOM_DIR/tool_profile.sh" || return 1

# Default port of `headroom proxy`. Override with: export HEADROOM_PROXY_PORT=8787
HEADROOM_PROXY_PORT="${HEADROOM_PROXY_PORT:-8787}"

# True when the tool settings durably route API calls through the local proxy.
headroom_is_wrapped() {
    grep -Eq "headroom|ANTHROPIC_BASE_URL.*(localhost|127\.0\.0\.1)" \
        "$TOOL_HOME/settings.json" 2>/dev/null
}

# True when the local proxy answers on its port (any HTTP response counts).
_headroom_proxy_alive() {
    curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$HEADROOM_PROXY_PORT/"
}

# Resolves how headroom can route copilot: BYOK needs a provider key in the
# environment; otherwise a saved Copilot OAuth token enables --subscription.
# Prints "byok" or "subscription"; returns 1 when neither is available.
_headroom_copilot_mode() {
    if [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${COPILOT_PROVIDER_API_KEY:-}" ]; then
        echo "byok"
        return 0
    fi
    case "$(headroom copilot-auth status 2>/dev/null)" in
        *"not logged in"*) return 1 ;;
        *"logged in"*)     echo "subscription"; return 0 ;;
        *)                 return 1 ;;
    esac
}

# Launcher-mode launch (copilot): routes through headroom when possible,
# falls back to a plain launch otherwise — never blocks the tool.
_launch_with_headroom() {
    local tool="$1"; shift
    if [ -n "${LLM_CLI_NO_HEADROOM:-}" ] || ! command -v headroom > /dev/null 2>&1; then
        command "$tool" "$@"
        return
    fi

    local mode
    if ! mode=$(_headroom_copilot_mode); then
        echo "headroom idle: set ANTHROPIC_API_KEY or run 'headroom copilot-auth login' to enable compression."
        command "$tool" "$@"
        return
    fi

    if [ "$mode" = "subscription" ]; then
        headroom wrap "$tool" --subscription -- "$@"
    else
        headroom wrap "$tool" -- "$@"
    fi
}

# Starts the proxy if the tool is wrapped and the proxy is down.
# Never blocks the tool launch: every failure degrades to a visible warning,
# because a wrapped tool with a dead proxy cannot reach the API at all.
_ensure_headroom_proxy() {
    command -v headroom > /dev/null 2>&1 || return 0
    headroom_is_wrapped || return 0
    _headroom_proxy_alive && return 0

    echo "Starting headroom proxy..."
    nohup headroom proxy > /dev/null 2>&1 &
    local _attempt
    for _attempt in 1 2 3 4 5; do
        sleep 1
        _headroom_proxy_alive && return 0
    done
    echo "    [WARN] headroom proxy failed to start — $TOOL_NAME API calls may fail." >&2
    echo "    Disable the wrap with: headroom unwrap $TOOL_NAME" >&2
}
