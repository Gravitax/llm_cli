#!/bin/bash

# Interactive wizard — guides a new machine/user through the full llm_cli setup:
#   1. activates the optimization layer for Claude Code and/or Copilot CLI
#      (sources claude_env.sh / copilot_env.sh, so claude()/copilot() wrappers
#      land in THIS shell — this script must be sourced, not executed)
#   2. offers the one-time Atlassian + Bitbucket credentials setup
#   3. offers to enable the per-project .mcp.json for the current directory
#   4. runs the diagnostics so you leave with a verified, working setup
#
# Usage:
#   source bootstrap.sh

_SELF="${BASH_SOURCE[0]:-$0}"
ROOT_DIR="$(cd "$(dirname "$_SELF")" && pwd)"
COMMON_DIR="$ROOT_DIR/common"

# Sourced-detection: a plain `bash bootstrap.sh` cannot export claude()/copilot()
# back to the caller's shell, so refuse to proceed silently broken.
(return 0 2>/dev/null)
if [ "$?" -ne 0 ]; then
    echo "Error: this script must be sourced, not executed."
    echo "Usage: source bootstrap.sh"
    exit 1
fi

source "$COMMON_DIR/lib_log.sh"

# Prompts and reads a line into REPLY — portable bash/zsh.
# (In zsh, `read -p` reads from a coprocess instead of printing a prompt,
# so the prompt must be printed manually.)
prompt_reply() {
    printf '%s' "$1"
    read -r REPLY
}

ask_yes_no() {
    local prompt="$1" default="${2:-n}"
    local hint="y/N"
    [ "$default" = "y" ] && hint="Y/n"
    prompt_reply "$prompt [$hint] "
    REPLY="${REPLY:-$default}"
    [[ "$REPLY" =~ ^[Yy]$ ]]
}

print_step "llm_cli setup wizard"
print_info "Root: $ROOT_DIR"

# --- 1. tool activation ---

print_step "Which agent(s) do you want to activate?"
echo "    1) Claude Code"
echo "    2) GitHub Copilot CLI"
echo "    3) Both"
prompt_reply "  Choice [3]: "
tool_choice="${REPLY:-3}"

case "$tool_choice" in
    1) source "$ROOT_DIR/claude/claude_env.sh" || return 1 ;;
    2) source "$ROOT_DIR/copilot/copilot_env.sh" || return 1 ;;
    3|*)
        source "$ROOT_DIR/claude/claude_env.sh" || return 1
        source "$ROOT_DIR/copilot/copilot_env.sh" || return 1
        ;;
esac

# --- 2. Atlassian + Bitbucket credentials (one-time, shared by both tools) ---

print_step "Atlassian + Bitbucket credentials"
CREDS_FILE="$HOME/.config/llm_cli/atlassian.env"
if [ -f "$CREDS_FILE" ]; then
    print_ok "credentials already configured ($CREDS_FILE)."
    if ask_yes_no "  Rotate/reconfigure tokens now?"; then
        bash "$COMMON_DIR/setup_atlassian.sh" || print_err "Atlassian setup failed."
    fi
else
    print_info "No credentials found — needed for Jira/Confluence/Bitbucket MCP tools."
    if ask_yes_no "  Configure them now?" "y"; then
        bash "$COMMON_DIR/setup_atlassian.sh" || print_err "Atlassian setup failed."
    fi
fi

# --- 3. global MCP registration (user scope, one-time) ---

print_step "Global MCP registration (user scope)"
if [ -f "$CREDS_FILE" ]; then
    if grep -q "io.github.b1ff/atlassian-dc-mcp-jira" "$HOME/.claude.json" 2>/dev/null \
        || grep -q "io.github.b1ff/atlassian-dc-mcp-jira" "$HOME/.copilot/mcp-config.json" 2>/dev/null; then
        print_ok "Atlassian/Bitbucket MCP already registered globally."
    else
        print_info "Atlassian/Bitbucket MCP not yet registered globally."
        if ask_yes_no "  Register now (active in every session for this user)?" "y"; then
            bash "$COMMON_DIR/setup_mcp_global.sh" || print_err "Global MCP setup failed."
        else
            print_info "Skipped — enable later with:"
            print_info "  bash $COMMON_DIR/setup_mcp_global.sh"
        fi
    fi
else
    print_info "No credentials yet — configure them first (step above) to enable MCP."
fi

# --- 4. verification ---

print_step "Verifying setup"
PROJECT_PATH="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
for tool in claude copilot; do
    [ -d "$HOME/.$tool" ] || continue
    bash "$HOME/.$tool/scripts/check_optimizations.sh" "$tool" "$PROJECT_PATH"
done

print_step "Done"
print_ok "Run 'claude' and/or 'copilot' from any project directory."
