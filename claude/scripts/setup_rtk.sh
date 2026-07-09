#!/bin/bash

# Installs RTK and configures the Claude Code PreToolUse hook.
# RTK intercepts bash commands (git, ls, tests...) and compresses output
# before it reaches the LLM context (~70-80% token savings on CLI output).
#
# Usage:
#   bash setup_rtk.sh        # Install and configure
#   bash setup_rtk.sh -u     # Remove hook and RTK artifacts

PYTHON_BIN="${PYTHON_BIN:-python3.11}"

RTK_LOCAL_BIN="$HOME/.local/bin"

install_jq() {
    if command -v jq > /dev/null 2>&1; then
        return 0
    fi
    echo "    Installing jq (required by RTK hook)..."
    if command -v apt-get > /dev/null 2>&1; then
        sudo apt-get install -y jq
    elif command -v brew > /dev/null 2>&1; then
        brew install jq > /dev/null 2>&1
    else
        echo "    Error: cannot install jq automatically. Install it manually: https://jqlang.github.io/jq/"
        return 1
    fi
    command -v jq > /dev/null 2>&1 || { echo "    Error: jq installation failed."; return 1; }
    echo "    [OK] jq installed."
}

install_rtk() {
    if command -v rtk > /dev/null 2>&1; then
        echo "    [OK] RTK already installed: $(rtk --version)"
        return 0
    fi
    echo "    Installing RTK..."
    if ! curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh; then
        echo "    Error: RTK installation failed."
        return 1
    fi
    export PATH="$RTK_LOCAL_BIN:$PATH"
    if ! command -v rtk > /dev/null 2>&1; then
        echo "    Error: RTK binary not found after install. Add $RTK_LOCAL_BIN to PATH."
        return 1
    fi
    echo "    [OK] RTK installed: $(rtk --version)"
}

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
    export PATH="$RTK_LOCAL_BIN:$PATH"
    if command -v rtk > /dev/null 2>&1; then
        rtk init -g --uninstall 2>&1 | sed 's/^/    /'
    else
        echo "    [WARN] rtk not found in PATH, skipping uninstall."
    fi
    echo "RTK hook removed. Restart Claude Code to apply."
else
    echo "Setting up RTK output compression..."
    install_jq || exit 1
    install_rtk || exit 1
    ensure_path_in_profile
    export PATH="$RTK_LOCAL_BIN:$PATH"
    rtk init -g --auto-patch 2>&1 | sed 's/^/    /'
    echo "RTK ready. Restart Claude Code to activate the hook."
    echo "Check savings after a session with: rtk gain"
fi
