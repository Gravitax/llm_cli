# Repairs the tool environment: scripts sync, global instructions, tool-specific hooks.
# When run from the source repo (windows\common\): full setup (sync + instructions + hooks).
# When run from $TOOL_HOME\scripts\: skips the sync (repo layout required) and
# repairs what can be repaired in place (RTK hook, PostToolUse hooks).
# Windows PowerShell 5.1 port of common/setup_env.sh.

. (Join-Path $PSScriptRoot 'tool_profile.ps1')
if (-not $TOOL_PROFILE_OK) { exit 1 }
. (Join-Path $PSScriptRoot 'lib_log.ps1')
. (Join-Path $PSScriptRoot 'lib_settings.ps1')

# Sync and instructions rewrite require the source repo layout (windows\common\ + overlay).
if ((Split-Path -Leaf $PSScriptRoot) -eq 'common') {
    & (Join-Path $PSScriptRoot 'setup_scripts_sync.ps1')
    & (Join-Path $PSScriptRoot 'setup_context.ps1')
} else {
    & (Join-Path $PSScriptRoot 'setup_context.ps1')
}

# Ensures the RTK PreToolUse hook is active (feature-gated: Claude only).
# The regex tolerates both `rtk hook claude` and Windows forms like
# `C:\...\rtk.exe hook claude` or a quoted path.
function Ensure-RtkHook {
    $settings = Join-Path $TOOL_HOME 'settings.json'
    $raw = ''
    if (Test-Path -LiteralPath $settings) { $raw = Get-Content -Raw -LiteralPath $settings }
    if ($raw -notmatch ('rtk(\.exe)?\\?"? hook ' + $TOOL_NAME)) {
        & (Join-Path $TOOL_HOME 'scripts\setup_rtk.ps1')
    }
}

if ($TOOL_HAS_RTK_HOOK -eq 1) {
    Ensure-RtkHook
}

if ($TOOL_HAS_AGENT_HOOKS -eq 1) {
    Register-PostToolUseHook 'Bash' 'cache_refresh_on_git.ps1'
    Register-PostToolUseHook 'Write' 'cache_refresh_on_write.ps1'
    Ensure-CacheReadPermission
}

if ($TOOL_HAS_HEADROOM -eq 1) {
    & (Join-Path $PSScriptRoot 'setup_headroom.ps1') -Ensure
}

Write-Host "    [OK] $TOOL_NAME environment ready."
