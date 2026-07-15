#!/bin/bash

# Installs RTK and configures the Claude Code PreToolUse hook.
# RTK intercepts bash commands (git, ls, tests...) and compresses output
# before it reaches the LLM context (~70-80% token savings on CLI output).
# Install logic lives in lib_deps.sh (ensure_jq / ensure_rtk) — this script
# only adds the Claude-specific hook configuration on top.
#
# Usage:
#   bash setup_rtk.sh        # Install and configure
#   bash setup_rtk.sh -u     # Remove hook and RTK artifacts

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Installed copy: lib_deps.sh sits next to this script; repo copy: it is in common/.
if [ -f "$SCRIPT_DIR/lib_deps.sh" ]; then
    source "$SCRIPT_DIR/lib_deps.sh"
else
    source "$SCRIPT_DIR/../../common/lib_deps.sh"
fi

ensure_path_in_profile() {
    local profile_line='export PATH="$HOME/.local/bin:$PATH"'
    local profile_files=("$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile")
    for profile in "${profile_files[@]}"; do
        if [ -f "$profile" ] && grep -qF '.local/bin' "$profile"; then
            return 0
        fi
    done
    for profile in "${profile_files[@]}"; do
        if [ -f "$profile" ]; then
            echo "$profile_line" >> "$profile"
            echo "    [OK] PATH updated in $profile"
            return 0
        fi
    done
}

if [ "$1" = "-u" ]; then
    echo "Removing RTK hook..."
    export PATH="$LOCAL_BIN:$PATH"
    if command -v rtk > /dev/null 2>&1; then
        rtk init -g --uninstall 2>&1 | sed 's/^/    /'
    else
        echo "    [WARN] rtk not found in PATH, skipping uninstall."
    fi
    echo "RTK hook removed. Restart Claude Code to apply."
else
    echo "Setting up RTK output compression..."
    ensure_jq || exit 1
    ensure_rtk || exit 1
    ensure_path_in_profile
    export PATH="$LOCAL_BIN:$PATH"
    rtk init -g --auto-patch 2>&1 | sed 's/^/    /'
    echo "RTK ready. Restart Claude Code to activate the hook."
    echo "Check savings after a session with: rtk gain"
fi
