# Orchestrator - installs and activates the Claude Code token-optimization layer.
#
# Usage:
#   . .\windows\claude\claude_env.ps1        (must be dot-sourced)
#
# Windows PowerShell 5.1 port of claude/claude_env.sh.

# Dot-source detection: a plain execution cannot define the claude wrapper
# in the caller's session, so refuse to proceed silently broken.
if ($MyInvocation.InvocationName -ne '.') {
    Write-Host "Error: this script must be dot-sourced, not executed."
    Write-Host "Usage: . $($MyInvocation.MyCommand.Path)"
    exit 1
}

$_claudeDir = $PSScriptRoot
$_commonDir = Join-Path (Split-Path -Parent $_claudeDir) 'common'

$env:TOOL_PROFILE = 'claude'
. (Join-Path $_commonDir 'tool_profile.ps1')
if (-not $TOOL_PROFILE_OK) { return }

. (Join-Path $_claudeDir 'scripts\setup_prerequisites.ps1')
if (-not $PREREQUISITES_OK) { return }

& (Join-Path $_commonDir 'setup_env.ps1')
& (Join-Path $_commonDir 'setup_shell_wrapper.ps1')

# Session wrapper - same body as the persistent block written to $PROFILE.
function global:claude {
    # Source the INSTALLED lib: its profile.env pins the claude profile even if
    # another tool's env script was sourced last in this session.
    . "$env:USERPROFILE\.claude\scripts\lib_cache.ps1"
    Invoke-CheckAndBuildCache
    Write-Host "Starting Claude..."
    $exe = Get-Command claude -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($exe) { & $exe.Source @args }
    else { Write-Error "claude binary not found in PATH." }
}
if (Test-Path Alias:claude) { Remove-Item Alias:claude -Force -ErrorAction SilentlyContinue }

Write-Host "Ready. Run: claude"
