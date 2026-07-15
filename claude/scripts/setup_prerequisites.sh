#!/bin/bash

# Checks runtime dependencies and installs Claude Code if missing.
# Must be sourced — uses return on failure.
# Requires lib_deps.sh to be sourced by the caller (claude_env.sh does it).

disable_telemetry() {
    export DO_NOT_TRACK=1
    export CLAUDE_TELEMETRY_DISABLED=1
    export NO_UPDATE_NOTIFIER=1
}

# The wrapper function/alias would shadow `command -v claude` resolution.
unset -f claude 2>/dev/null
unalias claude 2>/dev/null

ensure_node                                       || return 1
ensure_npm_cli "@anthropic-ai/claude-code" claude || return 1
disable_telemetry
