#!/bin/bash

# Writes the global instructions file ($TOOL_INSTRUCTIONS_GLOBAL) for the active tool.
# Overwrites the file entirely — always authoritative, no incremental patching.
# The template is deliberately compact: it is loaded into context on every turn
# of every session, so every line here has a permanent token cost.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/tool_profile.sh" || exit 1

mkdir -p "$(dirname "$TOOL_INSTRUCTIONS_GLOBAL")"

# Shared behavioral core — placeholders are substituted after writing.
cat > "$TOOL_INSTRUCTIONS_GLOBAL" << 'EOF'
# Code quality (SOLID)
- Naming: snake_case variables, CamelCase classes, UPPER_SNAKE_CASE constants. Descriptive names, no cryptic abbreviations.
- Functions: single responsibility, max ~20 lines, guard clauses, max 2 nesting levels, no magic numbers or strings.
- Comments: English, explain why not what, no commented-out code, one-line doc per public function/class.
- Modules: single responsibility, depend on abstractions, open for extension closed for modification.
- Errors: never swallowed silently; always carry context (what failed, where, why).
- No duplicate logic — extract immediately. Consistency with existing codebase patterns wins over preference.

# Enterprise context (Exail)
All code and data are confidential. Jira = tracking, Confluence = docs, Bitbucket = source (git.exail.com).
Research before assuming: verify any API, interface or module in Bitbucket (`search_code`, `get_file_content`),
Confluence (architecture docs) or Jira (acceptance criteria) — never guess what can be checked.
Jira workflow: read the full ticket description AND all comments before working; comment status when done or blocked.

# Commits & PRs
Commit format: [JIRA-KEY] short imperative description. Branch: feature/JIRA-KEY-short-description.
Reference the Jira ticket in commits and PR descriptions.
NEVER run git push without explicit user confirmation. Force push is strictly forbidden.

# Security
Never log, print, commit or hardcode credentials, tokens, API keys or PII — env vars or secret managers only.
Internal URLs (git.exail.com, jira.exail.com, ...) must not appear in external-facing documentation.
Delete temporary credential files immediately after use.

# Destructive actions
Before a multi-file refactor: summarize the plan and wait for confirmation.
Never delete files or overwrite uncommitted changes without explicit user confirmation.

# Token economy
Be concise. For code tasks: return code only, no explanation, unless the user asks for one.
Read the project context index first (see the local {{INSTRUCTIONS_LOCAL}}) and open only the 2-3 relevant files
instead of scanning the tree. Avoid re-reading files already in context.

# MCP tools — Atlassian & Bitbucket (per project)
MCP servers are enabled per project via a local .mcp.json — not globally (token economy).
If Jira/Confluence/Bitbucket tools are needed but unavailable, enable them once:
  bash {{TOOL_HOME}}/scripts/setup_mcp_project.sh
Three Data Center servers (io.github.b1ff/atlassian-dc-mcp-*): Jira (issues, search, comments),
Confluence (pages, search), Bitbucket (repos, files, code search — REST API, no git operations).
Prefer MCP browsing to read individual files; git clone only to run code or tests locally:
  bash {{TOOL_HOME}}/scripts/git_clone_exail.sh <PROJECT>/<repo>
URL pattern: https://git.exail.com/scm/<PROJECT_KEY>/<repo-slug>.git (key uppercase, slug lowercase).

# Maintenance scripts ({{TOOL_HOME}}/scripts/)
- setup_env.sh — full environment repair (scripts sync, instructions, hooks). Run when anything seems out of date.
- setup_context_cache.sh [path] — regenerate the project symbol index after structural changes (-u to remove).
- setup_mcp_project.sh [path] — enable Atlassian+Bitbucket MCP for a project (-u to remove).
- check_optimizations.sh [path] — diagnose the optimization setup (cache, wrapper, hooks).
- git_clone_exail.sh <PROJECT>/<repo> — clone from git.exail.com with stored credentials.
EOF

# Tool-specific sections.
if [ "$TOOL_PROFILE" = "claude" ]; then
    cat >> "$TOOL_INSTRUCTIONS_GLOBAL" << 'EOF'

# Subagents
For large codebase exploration or parallel research, delegate to subagents to keep the main context clean.
Reports must stay under 500 words — no raw file dumps. Not for small targeted reads (use Read/Grep directly).

@RTK.md
EOF
else
    cat >> "$TOOL_INSTRUCTIONS_GLOBAL" << 'EOF'

# CLI output compression (RTK)
If the `rtk` binary is available, prefix shell commands with it to compress their output
before it reaches context: `rtk git status`, `rtk git diff`, `rtk grep`, `rtk ls`, `rtk read <file>`.
Fall back to the plain command if rtk fails.
EOF
fi

# Substitute tool-specific placeholders.
sed -i \
    -e "s|{{TOOL_HOME}}|$TOOL_HOME|g" \
    -e "s|{{INSTRUCTIONS_LOCAL}}|$TOOL_INSTRUCTIONS_LOCAL|g" \
    "$TOOL_INSTRUCTIONS_GLOBAL"

line_count=$(wc -l < "$TOOL_INSTRUCTIONS_GLOBAL")
echo "    [OK] $TOOL_INSTRUCTIONS_GLOBAL rewritten ($line_count lines)."
