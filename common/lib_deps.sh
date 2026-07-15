#!/bin/bash

# Shared dependency installers — must be sourced. Every ensure_* is idempotent:
# already present -> silent success; missing -> automatic install; impossible ->
# loud error (return 1, never swallowed). Used by setup_dependencies.sh
# (bootstrap), setup_rtk.sh, setup_prerequisites.sh and setup_atlassian.sh.

LOCAL_BIN="$HOME/.local/bin"

# Installs a binary through the system package manager (apt-get or brew).
ensure_apt_pkg() {
    local bin="$1" pkg="$2"
    command -v "$bin" > /dev/null 2>&1 && return 0

    echo "    Installing $pkg..."
    if command -v apt-get > /dev/null 2>&1; then
        sudo apt-get install -y "$pkg"
    elif command -v brew > /dev/null 2>&1; then
        brew install "$pkg"
    else
        echo "    [ERROR] No package manager found — install $pkg manually." >&2
        return 1
    fi
    command -v "$bin" > /dev/null 2>&1 || { echo "    [ERROR] $pkg installation failed." >&2; return 1; }
    echo "    [OK] $pkg installed."
}

ensure_jq() { ensure_apt_pkg jq jq; }

# Node.js >= 20 — required by the claude/copilot CLIs and the MCP servers.
ensure_node() {
    local node_major
    node_major=$(node --version 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')
    [ -n "$node_major" ] && [ "$node_major" -ge 20 ] && return 0

    echo "    Installing Node.js 20 (requires sudo)..."
    if ! command -v apt-get > /dev/null 2>&1; then
        echo "    [ERROR] Cannot install Node.js automatically — install Node >= 20 manually." >&2
        return 1
    fi
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - \
        && sudo apt-get install -y nodejs
    node_major=$(node --version 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')
    [ -n "$node_major" ] && [ "$node_major" -ge 20 ] \
        || { echo "    [ERROR] Node.js installation failed." >&2; return 1; }
    echo "    [OK] Node.js $(node --version) installed."
}

# Puts npm's global bin dir on PATH for the current shell.
ensure_npm_bin_in_path() {
    local npm_bin
    npm_bin="$(npm config get prefix 2>/dev/null)/bin"
    case ":$PATH:" in
        *":$npm_bin:"*) ;;
        *) export PATH="$npm_bin:$PATH" ;;
    esac
}

# Installs a global npm CLI when its binary is missing. Args: package, binary.
ensure_npm_cli() {
    local pkg="$1" bin="$2"
    ensure_npm_bin_in_path
    command -v "$bin" > /dev/null 2>&1 && return 0

    echo "    Installing $pkg via npm..."
    npm install -g "$pkg" || { echo "    [ERROR] npm install -g $pkg failed." >&2; return 1; }
    command -v "$bin" > /dev/null 2>&1 \
        || { echo "    [ERROR] $bin not found after install — check \$(npm config get prefix)/bin in PATH." >&2; return 1; }
    echo "    [OK] $bin installed."
}

# uv — package runner used by the MCP servers and the headroom install.
ensure_uv() {
    command -v uvx > /dev/null 2>&1 && return 0

    echo "    Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh > /dev/null 2>&1
    export PATH="$LOCAL_BIN:$PATH"
    command -v uvx > /dev/null 2>&1 \
        || { echo "    [ERROR] uv installation failed. Install manually: https://docs.astral.sh/uv/" >&2; return 1; }
    echo "    [OK] uv installed."
}

# RTK (CLI output compression) — shared by claude (hook) and copilot (instructions).
ensure_rtk() {
    command -v rtk > /dev/null 2>&1 && return 0

    echo "    Installing RTK..."
    if ! curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh; then
        echo "    [ERROR] RTK installation failed." >&2
        return 1
    fi
    export PATH="$LOCAL_BIN:$PATH"
    command -v rtk > /dev/null 2>&1 \
        || { echo "    [ERROR] RTK binary not found after install. Add $LOCAL_BIN to PATH." >&2; return 1; }
    echo "    [OK] RTK installed: $(rtk --version)"
}

# Headroom (context-compression proxy) — uv tool install, pip fallback.
ensure_headroom() {
    command -v headroom > /dev/null 2>&1 && return 0

    echo "    Installing headroom-ai (large: ML dependencies)..."
    if command -v uv > /dev/null 2>&1; then
        uv tool install "headroom-ai[all]" || { echo "    [ERROR] uv tool install headroom-ai failed." >&2; return 1; }
    elif command -v pip3 > /dev/null 2>&1; then
        pip3 install --user "headroom-ai[all]" || { echo "    [ERROR] pip3 install headroom-ai failed." >&2; return 1; }
    else
        echo "    [ERROR] Neither uv nor pip3 found — cannot install headroom." >&2
        return 1
    fi
    export PATH="$LOCAL_BIN:$PATH"
    command -v headroom > /dev/null 2>&1 \
        || { echo "    [ERROR] headroom missing from PATH after install." >&2; return 1; }
    echo "    [OK] headroom installed."
}
