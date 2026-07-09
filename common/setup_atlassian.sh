#!/bin/bash

# One-time Atlassian credentials setup (Confluence + Jira + Bitbucket), shared
# by Claude Code and Copilot CLI.
#
# Prompts and validates the tokens, then:
#   - stores them in ~/.config/llm_cli/atlassian.env (chmod 600)
#   - stores git credentials for git.exail.com
#   - allows read-only git commands in Claude Code settings
#   - removes legacy user-scope MCP registrations (they injected ~150 tool
#     definitions into EVERY session; MCP is now enabled per project)
#
# To enable the MCP servers in a project that needs them:
#   bash setup_mcp_project.sh [project_path]
#
# Usage:
#   bash setup_atlassian.sh       first-time setup or token rotation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_log.sh"

CONFLUENCE_URL="https://confluence.exail.com/c"
JIRA_URL="https://jira.exail.com/j"
BITBUCKET_URL="https://git.exail.com"
CREDS_FILE="$HOME/.config/llm_cli/atlassian.env"

# Validates a Bearer token against a REST endpoint.
# Sets VALIDATED_USER on success. Returns 1 on failure.
# Args: token, url, display_name_expression (node.js, receives parsed JSON as `d`)
validate_token() {
    local token="$1" url="$2" display_expr="$3"
    local response http_code

    response=$(curl -s --max-time 8 \
        -H "Authorization: Bearer $token" \
        -H "Accept: application/json" \
        "$url" 2>&1)

    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 \
        -H "Authorization: Bearer $token" \
        -H "Accept: application/json" \
        "$url")

    case "$http_code" in
        200)
            VALIDATED_USER=$(echo "$response" | node -e \
                "let r='';process.stdin.on('data',c=>r+=c).on('end',()=>{try{const d=JSON.parse(r);console.log($display_expr)}catch(e){console.log('unknown')}})" \
                2>/dev/null)
            return 0
            ;;
        401) print_err "Token rejected (401). It may have expired or been revoked."; return 1 ;;
        403) print_err "Access forbidden (403). Insufficient permissions."; return 1 ;;
        000) print_err "Cannot reach $url. Check your network connection."; return 1 ;;
        *)   print_err "Unexpected HTTP $http_code from $url."; return 1 ;;
    esac
}

# --- preflight ---

check_prerequisites() {
    print_step "Checking prerequisites"

    if ! command -v node > /dev/null 2>&1; then
        print_err "Node.js not found."
        exit 1
    fi

    if ! command -v uvx > /dev/null 2>&1; then
        print_info "uv not found. Installing..."
        curl -LsSf https://astral.sh/uv/install.sh | sh > /dev/null 2>&1
        export PATH="$HOME/.local/bin:$PATH"
        if ! command -v uvx > /dev/null 2>&1; then
            print_err "uv installation failed. Install manually: https://docs.astral.sh/uv/"
            exit 1
        fi
        print_ok "uv installed."
    fi

    print_ok "Prerequisites met."
}

# --- prompts ---

prompt_value() {
    local label="$1" instructions="$2" var_name="$3"
    echo ""
    [ -n "$instructions" ] && echo -e "$instructions" && echo ""
    read -rp "  $label: " input
    if [ -z "$input" ]; then
        print_err "No value provided for $label."
        exit 1
    fi
    eval "$var_name=\"\$input\""
}

prompt_all_credentials() {
    print_step "Bitbucket username"
    prompt_value "Bitbucket username (your login or email)" "" BITBUCKET_USERNAME

    print_step "Confluence Personal Access Token"
    prompt_value "Confluence token" \
        "    1. Open $CONFLUENCE_URL\n    2. Avatar (top right) > Settings\n    3. Personal Access Tokens > Create" \
        CONFLUENCE_TOKEN

    print_step "Jira Personal Access Token"
    prompt_value "Jira token" \
        "    1. Open $JIRA_URL\n    2. Avatar (top right) > Profile\n    3. Personal Access Tokens > Create token" \
        JIRA_TOKEN

    print_step "Bitbucket Personal Access Token"
    prompt_value "Bitbucket token" \
        "    1. Open $BITBUCKET_URL\n    2. Avatar (top right) > Manage account\n    3. HTTP access tokens > Create token" \
        BITBUCKET_TOKEN
}

validate_all_tokens() {
    print_step "Validating tokens"

    if ! validate_token "$CONFLUENCE_TOKEN" \
        "$CONFLUENCE_URL/rest/api/user/current" \
        "d.displayName"; then
        return 1
    fi
    print_ok "Confluence: $VALIDATED_USER"

    if ! validate_token "$JIRA_TOKEN" \
        "$JIRA_URL/rest/api/2/myself" \
        "d.displayName"; then
        return 1
    fi
    print_ok "Jira: $VALIDATED_USER"

    if ! validate_token "$BITBUCKET_TOKEN" \
        "$BITBUCKET_URL/rest/api/1.0/projects?limit=1" \
        "d.values && d.values.length ? 'token OK' : 'token OK (no projects visible)'"; then
        return 1
    fi
    print_ok "Bitbucket: $VALIDATED_USER"

    return 0
}

# --- configuration ---

# Stores validated credentials for setup_mcp_project.sh (chmod 600).
store_credentials() {
    mkdir -p "$(dirname "$CREDS_FILE")"
    cat > "$CREDS_FILE" << EOF
CONFLUENCE_URL=$CONFLUENCE_URL
JIRA_URL=$JIRA_URL
BITBUCKET_URL=$BITBUCKET_URL
BITBUCKET_USERNAME=$BITBUCKET_USERNAME
CONFLUENCE_TOKEN=$CONFLUENCE_TOKEN
JIRA_TOKEN=$JIRA_TOKEN
BITBUCKET_TOKEN=$BITBUCKET_TOKEN
EOF
    chmod 600 "$CREDS_FILE"
}

configure_git_credentials() {
    local username="$1" token="$2"
    local host="${BITBUCKET_URL#https://}"
    local creds_file="$HOME/.git-credentials"

    # Remove any existing entry for this host then append the updated one.
    sed -i "\|@${host}|d" "$creds_file" 2>/dev/null || true
    echo "https://${username}:${token}@${host}" >> "$creds_file"
    chmod 600 "$creds_file"

    git config --global credential.helper store
}

# Allows read-only git commands without permission prompts (Claude Code only).
configure_claude_permissions() {
    local settings_file="$HOME/.claude/settings.json"
    mkdir -p "$(dirname "$settings_file")"

    node - "$settings_file" << 'EOF'
const fs = require('fs');
const file = process.argv[1];
let settings = {};
try { settings = JSON.parse(fs.readFileSync(file, 'utf8')); } catch {}

settings.permissions ??= {};
settings.permissions.allow ??= [];

const git_perms = [
    'Bash(git clone:*)',
    'Bash(git pull:*)',
    'Bash(git fetch:*)',
    'Bash(git checkout:*)',
    'Bash(git status:*)',
    'Bash(git log:*)',
    'Bash(git diff:*)',
    'Bash(git ls-remote:*)',
    'Bash(git branch:*)',
    'Bash(git push:*)'
];

for (const p of git_perms) {
    if (!settings.permissions.allow.includes(p)) settings.permissions.allow.push(p);
}

fs.writeFileSync(file, JSON.stringify(settings, null, 2) + '\n');
EOF
}

# Removes legacy user/global-scope MCP registrations from both tools.
# Per-project .mcp.json is now the only registration path.
remove_user_scope_registrations() {
    local tool
    for tool in claude copilot; do
        command -v "$tool" > /dev/null 2>&1 || continue
        "$tool" mcp remove confluence    > /dev/null 2>&1 || true
        "$tool" mcp remove mcp-atlassian > /dev/null 2>&1 || true
        "$tool" mcp remove bitbucket     > /dev/null 2>&1 || true
        print_ok "user-scope MCP registrations removed from $tool."
    done
}

# --- main ---

check_prerequisites
prompt_all_credentials

if ! validate_all_tokens; then
    print_err "One or more tokens are invalid. No changes made."
    exit 1
fi

print_step "Storing credentials"
store_credentials
print_ok "credentials stored in $CREDS_FILE (chmod 600)."

print_step "Configuring git credentials for $BITBUCKET_URL"
configure_git_credentials "$BITBUCKET_USERNAME" "$BITBUCKET_TOKEN"
print_ok "git credentials stored in ~/.git-credentials."

if command -v claude > /dev/null 2>&1 || [ -d "$HOME/.claude" ]; then
    print_step "Configuring Claude Code git permissions"
    configure_claude_permissions
    print_ok "read-only git commands allowed in ~/.claude/settings.json."
fi

print_step "Removing user-scope MCP registrations (token economy)"
remove_user_scope_registrations

echo ""
echo "Credentials ready. MCP servers are now enabled PER PROJECT (not globally):"
echo "  cd <project> && bash $SCRIPT_DIR/setup_mcp_project.sh"
echo "This writes a local .mcp.json read by both Claude Code and Copilot CLI,"
echo "so the ~150 Atlassian/Bitbucket tool definitions only load where needed."
echo ""
