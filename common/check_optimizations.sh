#!/bin/bash

# Verifies that the token optimizations are correctly configured for the active tool.
# Checks: RTK (Claude only), PostToolUse hooks (Claude only), headroom wrap,
# shell wrapper, context cache, instructions entries.
#
# Usage: bash check_optimizations.sh [claude|copilot] [project_path]
# (the tool argument is optional when run from an installed $TOOL_HOME/scripts/ copy)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Optional first positional argument selects the tool profile.
case "$1" in
    claude|copilot) export TOOL_PROFILE="$1"; shift ;;
esac

source "$SCRIPT_DIR/tool_profile.sh" || exit 1
source "$SCRIPT_DIR/lib_log.sh"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
SETTINGS_FILE="$TOOL_HOME/settings.json"
# Keep in sync with PROFILE_FILES in setup_shell_wrapper.sh.
PROFILE_FILES=("$HOME/.zshrc" "$HOME/.bashrc")

check_rtk_dependencies() {
    print_step "RTK dependencies"

    if command -v rtk > /dev/null 2>&1; then
        check_ok "rtk $(rtk --version) at $(command -v rtk)"
    else
        check_fail "rtk not found in PATH"
        check_warn "Fix: bash $TOOL_HOME/scripts/setup_rtk.sh"
    fi

    if command -v jq > /dev/null 2>&1; then
        check_ok "jq $(jq --version)"
    else
        check_fail "jq not found (required by RTK hook)"
        check_warn "Fix: sudo apt-get install -y jq"
    fi
}

check_rtk_hook() {
    print_step "RTK hook installation"

    # RTK registers a native PreToolUse hook via `rtk init -g` — settings.json only.
    local hook_cmd
    hook_cmd=$($PYTHON_BIN - "$SETTINGS_FILE" << 'PYEOF'
import json, sys
try:
    s = json.load(open(sys.argv[1]))
    for e in s.get("hooks", {}).get("PreToolUse", []):
        for h in e.get("hooks", []):
            cmd = h.get("command", "")
            if "rtk" in cmd:
                print(cmd)
                exit(0)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
PYEOF
)

    if [ -n "$hook_cmd" ]; then
        check_ok "PreToolUse hook registered in settings.json: $hook_cmd"
    else
        check_fail "RTK PreToolUse hook not found in $SETTINGS_FILE"
        check_warn "Fix: bash $TOOL_HOME/scripts/setup_rtk.sh"
    fi

    if [ -f "$TOOL_HOME/RTK.md" ]; then
        check_ok "RTK.md present: $TOOL_HOME/RTK.md"
    else
        check_fail "RTK.md not found — the agent won't have RTK usage instructions"
        check_warn "Fix: bash $TOOL_HOME/scripts/setup_rtk.sh"
    fi

    if grep -qF "@RTK.md" "$TOOL_INSTRUCTIONS_GLOBAL" 2>/dev/null; then
        check_ok "@RTK.md referenced in $(basename "$TOOL_INSTRUCTIONS_GLOBAL")"
    else
        check_fail "@RTK.md missing from $TOOL_INSTRUCTIONS_GLOBAL"
        check_warn "Fix: bash $TOOL_HOME/scripts/setup_context.sh"
    fi
}

check_rtk_savings() {
    print_step "RTK token savings"

    local savings
    savings=$(rtk gain 2>/dev/null)
    if echo "$savings" | grep -q "No tracking\|No data"; then
        check_warn "No savings data yet — run a session first, then: rtk gain"
        return
    fi
    local tokens_saved commands
    tokens_saved=$(echo "$savings" | grep "Tokens saved" | grep -oP '[\d.]+[KM]?\s+\(\d+\.\d+%\)')
    commands=$(echo "$savings"     | grep "Total commands" | grep -oP '\d+')
    check_ok "RTK savings — $commands commands — saved $tokens_saved"
    echo "$savings" | sed 's/^/       /'
}

# RTK without a hook system (copilot): the agent prefixes commands with rtk
# because its instructions tell it to — check the binary and that block.
check_rtk_instructions() {
    print_step "RTK output compression (via instructions)"

    if command -v rtk > /dev/null 2>&1; then
        check_ok "rtk $(rtk --version) at $(command -v rtk)"
    else
        check_fail "rtk not found in PATH — the agent's rtk-prefixed commands will fail"
        check_warn "Fix: bash $TOOL_HOME/scripts/setup_dependencies.sh"
    fi

    if grep -qF "# CLI output compression (RTK)" "$TOOL_INSTRUCTIONS_GLOBAL" 2>/dev/null; then
        check_ok "RTK usage block present in $(basename "$TOOL_INSTRUCTIONS_GLOBAL")"
    else
        check_fail "RTK usage block missing from $TOOL_INSTRUCTIONS_GLOBAL"
        check_warn "Fix: bash $TOOL_HOME/scripts/setup_context.sh"
    fi
}

check_post_tool_use_hooks() {
    print_step "Cache refresh hooks (PostToolUse)"

    for hook_script in cache_refresh_on_git.sh cache_refresh_on_write.sh; do
        if grep -qF "$hook_script" "$SETTINGS_FILE" 2>/dev/null; then
            check_ok "PostToolUse hook registered: $hook_script"
        else
            check_fail "PostToolUse hook missing: $hook_script"
            check_warn "Fix: bash $TOOL_HOME/scripts/setup_env.sh"
        fi
    done
}

check_shell_wrapper() {
    print_step "Shell wrapper"

    local wrapper_marker="# $TOOL_NAME context-cache wrapper"
    for profile in "${PROFILE_FILES[@]}"; do
        if [ ! -f "$profile" ]; then
            check_warn "$profile not found (skipped)"
        elif grep -qF "$wrapper_marker" "$profile"; then
            check_ok "$TOOL_NAME() wrapper present in $profile"
        else
            check_fail "$TOOL_NAME() wrapper missing from $profile"
            check_warn "Fix: bash $SCRIPT_DIR/setup_shell_wrapper.sh"
        fi
    done
}

check_context_cache() {
    print_step "Context cache"

    local project_path="$1"
    local project_hash cache_file
    project_hash=$(echo -n "$project_path" | md5sum | cut -c1-8)
    cache_file="$TOOL_HOME/projects/$project_hash/context_cache.md"

    check_info "Project : $project_path"
    check_info "Cache   : $cache_file"

    if [ -f "$cache_file" ]; then
        local lines size generated
        lines=$(wc -l < "$cache_file")
        size=$(du -h "$cache_file" | cut -f1)
        generated=$(grep "Generated:" "$cache_file" | sed 's/.*Generated: //' | cut -d'|' -f1 | xargs)
        check_ok "Cache exists ($lines lines, $size, generated: $generated)"
    else
        check_fail "No cache found"
        check_warn "Fix: bash $TOOL_HOME/scripts/setup_context_cache.sh $project_path"
    fi
}

check_instructions() {
    print_step "Instructions files"

    local project_path="$1"
    local local_file="$project_path/$TOOL_INSTRUCTIONS_LOCAL"

    if [ -f "$TOOL_INSTRUCTIONS_GLOBAL" ]; then
        check_ok "Global instructions: $TOOL_INSTRUCTIONS_GLOBAL ($(wc -l < "$TOOL_INSTRUCTIONS_GLOBAL") lines)"
    else
        check_fail "$TOOL_INSTRUCTIONS_GLOBAL not found"
        check_warn "Fix: bash $TOOL_HOME/scripts/setup_context.sh"
    fi

    if grep -qF "# Project context index" "$local_file" 2>/dev/null; then
        check_ok "'# Project context index' entry present in $local_file"
    else
        check_fail "'# Project context index' missing from $local_file"
        check_warn "Fix: bash $TOOL_HOME/scripts/setup_context_cache.sh $project_path"
    fi
}

check_headroom() {
    print_step "Headroom compression proxy (optional)"

    source "$SCRIPT_DIR/lib_headroom.sh"

    if ! command -v headroom > /dev/null 2>&1; then
        if headroom_is_wrapped; then
            check_fail "settings.json routes API calls through headroom but the binary is missing — $TOOL_NAME requests will fail"
            check_warn "Fix: bash $TOOL_HOME/scripts/setup_headroom.sh (reinstall) or remove the wrap from $TOOL_HOME/settings.json"
        else
            check_info "headroom not installed — optional, ~15-20% extra token savings"
            check_info "Enable if wanted: bash $TOOL_HOME/scripts/setup_headroom.sh"
        fi
        return
    fi

    check_ok "headroom present at $(command -v headroom)"

    # Launcher mode (copilot): routing happens at launch through the shell wrapper.
    if [ "$TOOL_HEADROOM_MODE" = "launcher" ]; then
        local wrapper_routed=0
        for profile in "${PROFILE_FILES[@]}"; do
            grep -qF "_launch_with_headroom" "$profile" 2>/dev/null && wrapper_routed=1
        done
        if [ "$wrapper_routed" = "1" ]; then
            check_ok "$TOOL_NAME launches through headroom (shell wrapper)"
        else
            check_fail "shell wrapper does not launch $TOOL_NAME through headroom"
            check_warn "Fix: bash $TOOL_HOME/scripts/setup_shell_wrapper.sh"
        fi
        if _headroom_copilot_mode > /dev/null; then
            check_ok "routing credentials available (mode: $(_headroom_copilot_mode))"
        else
            check_info "no ANTHROPIC_API_KEY and no Copilot OAuth — launches stay plain (compression idle)"
            check_info "Enable: export ANTHROPIC_API_KEY=... or headroom copilot-auth login"
        fi
        return
    fi

    if headroom_is_wrapped; then
        check_ok "$TOOL_NAME wrapped — proxy routing active in settings.json"
    else
        check_info "$TOOL_NAME not wrapped — enable with: bash $TOOL_HOME/scripts/setup_headroom.sh"
        return
    fi

    # doctor's exit code also covers unrelated tools (codex, shell env), so the
    # load-bearing check is done directly: wrapped + proxy reachability.
    if _headroom_proxy_alive; then
        check_ok "headroom proxy reachable on port $HEADROOM_PROXY_PORT"
    else
        check_info "proxy not running — the shell wrapper starts it at $TOOL_NAME launch"
        check_info "Details anytime: headroom doctor"
    fi

    local perf
    perf=$(headroom perf 2>/dev/null | head -5)
    [ -n "$perf" ] && echo "$perf" | sed 's/^/       /'
}

check_global_mcp() {
    print_step "Global MCP (optional)"

    local mcp_config
    if [ "$TOOL_NAME" = "claude" ]; then
        mcp_config="$HOME/.claude.json"
    else
        mcp_config="$HOME/.copilot/mcp-config.json"
    fi

    if grep -q "io.github.b1ff/atlassian-dc-mcp-jira" "$mcp_config" 2>/dev/null; then
        check_ok "Atlassian/Bitbucket MCP registered globally ($mcp_config)"
    else
        check_info "MCP not registered globally — Jira/Confluence/Bitbucket tools unavailable"
        check_info "Enable if needed: bash $TOOL_HOME/scripts/setup_mcp_global.sh"
    fi
}

project_path="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

echo ""
echo "Checking $TOOL_NAME optimizations..."

if [ "$TOOL_HAS_RTK_HOOK" = "1" ]; then
    check_rtk_dependencies
    if command -v rtk > /dev/null 2>&1; then
        check_rtk_hook
        check_rtk_savings
    fi
else
    check_rtk_instructions
fi

if [ "$TOOL_HAS_AGENT_HOOKS" = "1" ]; then
    check_post_tool_use_hooks
fi

if [ "$TOOL_HAS_HEADROOM" = "1" ]; then
    check_headroom
fi

check_shell_wrapper
check_context_cache "$project_path"
check_instructions "$project_path"
check_global_mcp

echo ""
echo "=============================="
echo -e "  Passed: \033[0;32m$pass\033[0m  Failed: \033[0;31m$fail\033[0m"
echo "=============================="
echo ""

[ "$fail" -eq 0 ]
