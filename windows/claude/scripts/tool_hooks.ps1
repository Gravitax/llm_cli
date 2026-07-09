# Claude-specific pre-launch checks - dot-sourced by common/lib_cache.ps1 before each launch.
# Extension point: defines Invoke-ToolPreLaunchHook, called if present.
# Windows PowerShell 5.1 port of claude/scripts/tool_hooks.sh.

# Repairs the RTK PreToolUse hook if it disappeared from settings.json.
# The regex tolerates Windows command forms (`C:\...\rtk.exe hook claude`).
function Invoke-ToolPreLaunchHook {
    $settings = Join-Path $env:USERPROFILE '.claude\settings.json'
    $raw = ''
    if (Test-Path -LiteralPath $settings) { $raw = Get-Content -Raw -LiteralPath $settings }
    if ($raw -match 'rtk(\.exe)?\\?"? hook claude') { return }
    Write-Host "RTK hook missing - reinstalling..."
    & (Join-Path $env:USERPROFILE '.claude\scripts\setup_env.ps1')
}
