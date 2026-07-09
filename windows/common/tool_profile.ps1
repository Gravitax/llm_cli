# Resolves tool-specific paths and feature flags from TOOL_PROFILE (claude | copilot).
# Must be dot-sourced. Resolution order:
#   1. profile.env next to this file (written by setup_scripts_sync.ps1 at install time)
#   2. TOOL_PROFILE environment variable (exported by the env orchestrators)
# profile.env wins so that an installed copy always targets its own tool home,
# even if another tool's profile is still exported in the shell.
#
# Callers must test $TOOL_PROFILE_OK after dot-sourcing.
# Windows PowerShell 5.1 port of common/tool_profile.sh.

$TOOL_PROFILE_OK = $false

$_profileEnvFile = Join-Path $PSScriptRoot 'profile.env'
$TOOL_PROFILE = $env:TOOL_PROFILE
if (Test-Path -LiteralPath $_profileEnvFile) {
    foreach ($_line in (Get-Content -LiteralPath $_profileEnvFile)) {
        if ($_line -match '^\s*TOOL_PROFILE=(.+)\s*$') { $TOOL_PROFILE = $matches[1].Trim() }
    }
}

switch ($TOOL_PROFILE) {
    'claude' {
        $TOOL_NAME = 'claude'
        $TOOL_HOME = Join-Path $env:USERPROFILE '.claude'
        $TOOL_INSTRUCTIONS_GLOBAL = Join-Path $TOOL_HOME 'CLAUDE.md'
        $TOOL_INSTRUCTIONS_LOCAL = 'CLAUDE.md'
        $TOOL_IGNORE_FILE = '.claudeignore'
        # Claude Code supports settings.json hooks: RTK PreToolUse + cache PostToolUse.
        $TOOL_HAS_RTK_HOOK = 1
        $TOOL_HAS_AGENT_HOOKS = 1
        $TOOL_PROFILE_OK = $true
    }
    'copilot' {
        Write-Error "The 'copilot' profile is not ported to Windows yet (use the bash scripts under WSL)."
    }
    default {
        $_got = if ($TOOL_PROFILE) { $TOOL_PROFILE } else { 'unset' }
        Write-Error "TOOL_PROFILE must be 'claude' (got: '$_got')."
    }
}

if ($TOOL_PROFILE_OK) {
    # Exported for child processes (gen_context_cache.py resolves TOOL_HOME from env).
    $env:TOOL_PROFILE = $TOOL_PROFILE
    $env:TOOL_HOME = $TOOL_HOME
}
