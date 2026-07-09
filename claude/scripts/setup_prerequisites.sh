#!/bin/bash

# Checks runtime dependencies and installs Claude Code if missing.
# Must be sourced — uses return on failure.

check_node_version() {
    local node_major
    node_major=$(node --version 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')
    if [ -z "$node_major" ] || [ "$node_major" -lt 20 ]; then
        echo "Error: Node.js >= 20 required (found: $(node --version 2>/dev/null || echo 'none'))."
        echo "Upgrade: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs"
        return 1
    fi
}

ensure_npm_bin_in_path() {
    NPM_BIN="$(npm config get prefix 2>/dev/null)/bin"
    if [[ ":$PATH:" != *":$NPM_BIN:"* ]]; then
        export PATH="$NPM_BIN:$PATH"
    fi
}

install_claude_code() {
    unset -f claude 2>/dev/null
    unalias claude 2>/dev/null
    if ! command -v claude > /dev/null 2>&1; then
        echo "Installing Claude Code via npm..."
        if ! npm install -g @anthropic-ai/claude-code; then
            echo "Error: Claude Code installation failed."
            return 1
        fi
    fi
}

disable_telemetry() {
    export DO_NOT_TRACK=1
    export CLAUDE_TELEMETRY_DISABLED=1
    export NO_UPDATE_NOTIFIER=1
}

check_node_version  || return 1
ensure_npm_bin_in_path
install_claude_code || return 1
disable_telemetry
