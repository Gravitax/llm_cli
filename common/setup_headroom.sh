#!/bin/bash

# Installs Headroom (context-compression proxy, github.com/headroomlabs-ai/headroom)
# and durably wraps the active tool so its API calls go through the local proxy
# (~15-20% token savings on coding agents, 60-95% on JSON-heavy tool output).
# Stacks on top of RTK and the context cache — they optimize different layers.
#
# Usage:
#   setup_headroom.sh            install + wrap + verify
#   setup_headroom.sh --ensure   non-interactive repair: skips silently when
#                                headroom is not installed (no network install)
#   setup_headroom.sh -u         unwrap the tool (restores direct API access)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/tool_profile.sh" || exit 1
source "$SCRIPT_DIR/lib_log.sh"
source "$SCRIPT_DIR/lib_headroom.sh"

install_headroom() {
    command -v headroom > /dev/null 2>&1 && return 0

    print_step "Installing headroom-ai"
    if command -v uv > /dev/null 2>&1; then
        uv tool install "headroom-ai[all]" || { print_err "uv tool install headroom-ai failed."; return 1; }
    elif command -v pip3 > /dev/null 2>&1; then
        pip3 install --user "headroom-ai[all]" || { print_err "pip3 install headroom-ai failed."; return 1; }
    else
        print_err "Neither uv nor pip3 found — cannot install headroom."
        return 1
    fi

    export PATH="$HOME/.local/bin:$PATH"
    command -v headroom > /dev/null 2>&1 || { print_err "headroom missing from PATH after install."; return 1; }
    print_ok "headroom installed ($(command -v headroom))."
}

# Writes or removes the durable proxy routing (env.ANTHROPIC_BASE_URL) in the
# tool settings — `headroom wrap` only sets it transiently for its own session.
write_proxy_routing() {
    local action="$1" settings="$TOOL_HOME/settings.json"
    command -v jq > /dev/null 2>&1 || { print_err "jq not found — cannot edit $settings."; return 1; }

    local tmp
    tmp=$(mktemp)
    if [ "$action" = "add" ]; then
        jq --arg url "http://127.0.0.1:$HEADROOM_PROXY_PORT" \
            '.env //= {} | .env.ANTHROPIC_BASE_URL = $url' "$settings" > "$tmp"
    else
        jq 'if .env then .env |= del(.ANTHROPIC_BASE_URL) else . end' "$settings" > "$tmp"
    fi || { rm -f "$tmp"; print_err "failed to edit $settings."; return 1; }
    mv "$tmp" "$settings"
}

apply_wrap() {
    headroom_is_wrapped && { print_ok "$TOOL_NAME already wrapped."; return 0; }

    print_step "Wrapping $TOOL_NAME with the headroom proxy"
    # Durable part 1 — `headroom wrap` registers the retrieve/compression MCP
    # servers and context tools. It also launches a session of the tool;
    # `-- --version` makes that child session exit immediately.
    local output
    if ! output=$(headroom wrap "$TOOL_NAME" -- --version 2>&1); then
        print_err "headroom wrap $TOOL_NAME failed: $output"
        return 1
    fi
    # Durable part 2 — proxy routing in settings.json (what `headroom doctor`
    # checks as "claude routed"); wrap alone only exports it transiently.
    write_proxy_routing add || return 1
    headroom_is_wrapped || { print_err "wrap ran but $TOOL_HOME/settings.json shows no proxy routing."; return 1; }
    print_ok "$TOOL_NAME wrapped — durable proxy routing in $TOOL_HOME/settings.json."
}

verify_wrap() {
    print_step "Verifying headroom health"
    _ensure_headroom_proxy
    if ! _headroom_proxy_alive; then
        print_err "headroom proxy is not reachable — $TOOL_NAME cannot call the API while wrapped."
        print_err "Unwrap with: bash $SCRIPT_DIR/setup_headroom.sh -u"
        return 1
    fi
    # Doctor output is diagnostic: unrelated warnings (other tools, shell env)
    # must not fail the setup; the load-bearing checks above already did.
    # The codex rows are filtered out — doctor probes every tool it can wrap,
    # and the OpenAI Codex CLI is not part of this layer.
    headroom doctor 2>&1 | grep -vi codex | sed 's/^/    /'
    print_ok "headroom proxy reachable and $TOOL_NAME routed."
}

remove_wrap() {
    command -v headroom > /dev/null 2>&1 || { print_err "headroom not installed — nothing to unwrap."; return 1; }
    headroom unwrap "$TOOL_NAME" || { print_err "headroom unwrap $TOOL_NAME failed."; return 1; }
    write_proxy_routing remove || return 1
    print_ok "$TOOL_NAME unwrapped — API calls go directly to the provider again."
}

# --- main ---

if [ "$TOOL_HAS_HEADROOM" != "1" ]; then
    print_info "[SKIP] headroom wrap not supported for the $TOOL_NAME profile yet."
    exit 0
fi

case "${1:-}" in
    -u)
        remove_wrap
        exit $?
        ;;
    --ensure)
        if ! command -v headroom > /dev/null 2>&1; then
            print_info "[SKIP] headroom not installed — enable with: bash $SCRIPT_DIR/setup_headroom.sh"
            exit 0
        fi
        ;;
esac

install_headroom || exit 1
apply_wrap || exit 1
verify_wrap
