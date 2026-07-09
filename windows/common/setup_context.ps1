# Writes the global instructions file ($TOOL_INSTRUCTIONS_GLOBAL) for the active tool.
# Overwrites the file entirely - always authoritative, no incremental patching.
# The template is deliberately compact: it is loaded into context on every turn
# of every session, so every line here has a permanent token cost.
# Windows PowerShell 5.1 port of common/setup_context.sh.

. (Join-Path $PSScriptRoot 'tool_profile.ps1')
if (-not $TOOL_PROFILE_OK) { exit 1 }
. (Join-Path $PSScriptRoot 'lib_log.ps1')

$parentDir = Split-Path -Parent $TOOL_INSTRUCTIONS_GLOBAL
if (-not (Test-Path -LiteralPath $parentDir)) {
    New-Item -ItemType Directory -Force -Path $parentDir | Out-Null
}

# Shared behavioral core - placeholders are substituted after building.
$content = @'
# Code quality (SOLID)
- Naming: snake_case variables, CamelCase classes, UPPER_SNAKE_CASE constants. Descriptive names, no cryptic abbreviations.
- Functions: single responsibility, max ~20 lines, guard clauses, max 2 nesting levels, no magic numbers or strings.
- Comments: English, explain why not what, no commented-out code, one-line doc per public function/class.
- Modules: single responsibility, depend on abstractions, open for extension closed for modification.
- Errors: never swallowed silently; always carry context (what failed, where, why).
- No duplicate logic - extract immediately. Consistency with existing codebase patterns wins over preference.

# Enterprise context (Exail)
All code and data are confidential. Jira = tracking, Confluence = docs, Bitbucket = source (git.exail.com).
Research before assuming: verify any API, interface or module in Bitbucket (`search_code`, `get_file_content`),
Confluence (architecture docs) or Jira (acceptance criteria) - never guess what can be checked.
Jira workflow: read the full ticket description AND all comments before working; comment status when done or blocked.

# Commits & PRs
Commit format: [JIRA-KEY] short imperative description. Branch: feature/JIRA-KEY-short-description.
Reference the Jira ticket in commits and PR descriptions.
NEVER run git push without explicit user confirmation. Force push is strictly forbidden.

# Security
Never log, print, commit or hardcode credentials, tokens, API keys or PII - env vars or secret managers only.
Internal URLs (git.exail.com, jira.exail.com, ...) must not appear in external-facing documentation.
Delete temporary credential files immediately after use.

# Destructive actions
Before a multi-file refactor: summarize the plan and wait for confirmation.
Never delete files or overwrite uncommitted changes without explicit user confirmation.

# Token economy
Be concise. For code tasks: return code only, no explanation, unless the user asks for one.
Read the project context index first (see the local {{INSTRUCTIONS_LOCAL}}) and open only the 2-3 relevant files
instead of scanning the tree. Avoid re-reading files already in context.

# MCP tools - Atlassian & Bitbucket (global, user scope)
MCP servers are registered globally (user scope), once, for this user - active in every session.
(Setup is not ported to Windows yet; if Jira/Confluence/Bitbucket tools are unavailable, configure from Linux/WSL.)
Three Data Center servers (io.github.b1ff/atlassian-dc-mcp-*): Jira (issues, search, comments),
Confluence (pages, search), Bitbucket (repos, files, code search - REST API, no git operations).
Prefer MCP browsing to read individual files; git clone only to run code or tests locally.
URL pattern: https://git.exail.com/scm/<PROJECT_KEY>/<repo-slug>.git (key uppercase, slug lowercase).

# Maintenance scripts ({{TOOL_HOME}}\scripts\, run with: powershell -NoProfile -File <script>)
- setup_env.ps1 - full environment repair (scripts sync, instructions, hooks). Run when anything seems out of date.
- setup_context_cache.ps1 [path] - regenerate the project symbol index after structural changes (-u to remove).
- check_optimizations.ps1 [path] - diagnose the optimization setup (cache, wrapper, hooks).
'@

# Tool-specific sections.
if ($TOOL_PROFILE -eq 'claude') {
    $content += @'


# Subagents
For large codebase exploration or parallel research, delegate to subagents to keep the main context clean.
Reports must stay under 500 words - no raw file dumps. Not for small targeted reads (use Read/Grep directly).

@RTK.md
'@
} else {
    $content += @'


# CLI output compression (RTK)
If the `rtk` binary is available, prefix shell commands with it to compress their output
before it reaches context: `rtk git status`, `rtk git diff`, `rtk grep`, `rtk ls`, `rtk read <file>`.
Fall back to the plain command if rtk fails.
'@
}

# Substitute tool-specific placeholders.
$content = $content.Replace('{{TOOL_HOME}}', $TOOL_HOME).Replace('{{INSTRUCTIONS_LOCAL}}', $TOOL_INSTRUCTIONS_LOCAL)
$content += "`n"

Write-Utf8NoBom $TOOL_INSTRUCTIONS_GLOBAL $content

$lineCount = ($content -split "`n").Count - 1
Write-Host "    [OK] $TOOL_INSTRUCTIONS_GLOBAL rewritten ($lineCount lines)."
