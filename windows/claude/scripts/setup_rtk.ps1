# Configures the RTK PreToolUse hook for Claude Code.
# RTK intercepts bash commands (git, ls, tests...) and compresses output
# before it reaches the LLM context (~70-80% token savings on CLI output).
#
# Unlike the bash version, this port never tries to install RTK itself: the
# Unix curl|sh installer does not apply on Windows. It expects a Windows rtk.exe
# on PATH and prints install guidance when missing. jq is not needed on Windows
# (settings.json is edited natively via lib_settings.ps1).
#
# Usage:
#   powershell -File setup_rtk.ps1        # Configure the hook
#   powershell -File setup_rtk.ps1 -u     # Remove the hook
#
# Windows PowerShell 5.1 port of claude/scripts/setup_rtk.sh.

param([switch]$u)

# Installed copies have the libs next to them; the repo keeps them in windows\common\.
$libDir = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $libDir 'lib_settings.ps1'))) {
    $libDir = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'common'
}
. (Join-Path $libDir 'lib_log.ps1')
. (Join-Path $libDir 'lib_settings.ps1')

$TOOL_NAME = 'claude'
$TOOL_HOME = Join-Path $env:USERPROFILE '.claude'

function Get-RtkExe {
    $cmd = Get-Command rtk -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    # Default install location even when not on PATH yet.
    $localRtk = Join-Path $env:USERPROFILE '.local\bin\rtk.exe'
    if (Test-Path -LiteralPath $localRtk) { return $localRtk }
    return $null
}

function Test-RtkHookRegistered {
    $settings = Join-Path $TOOL_HOME 'settings.json'
    if (-not (Test-Path -LiteralPath $settings)) { return $false }
    return ((Get-Content -Raw -LiteralPath $settings) -match ('rtk(\.exe)?\\?"? hook ' + $TOOL_NAME))
}

if ($u) {
    Write-Host "Removing RTK hook..."
    $rtk = Get-RtkExe
    if ($rtk) {
        & $rtk init -g --uninstall 2>&1 | ForEach-Object { "    $_" }
    } else {
        Write-Host "    [WARN] rtk not found, skipping uninstall."
    }
    Write-Host "RTK hook removed. Restart Claude Code to apply."
    exit 0
}

Write-Host "Setting up RTK output compression..."

$rtk = Get-RtkExe
if (-not $rtk) {
    Write-Host "    Error: rtk.exe not found."
    Write-Host "    Install the Windows build from https://github.com/rtk-ai/rtk/releases"
    Write-Host "    into $env:USERPROFILE\.local\bin and add that directory to PATH."
    exit 1
}
Write-Host "    [OK] RTK found: $(& $rtk --version) at $rtk"

if (Test-RtkHookRegistered) {
    Write-Host "    [OK] RTK PreToolUse hook already registered."
} else {
    & $rtk init -g 2>&1 | ForEach-Object { "    $_" }
    if (-not (Test-RtkHookRegistered)) {
        # Fallback: write the hook entry ourselves, mirroring the shape rtk uses on Windows.
        Register-PreToolUseHook 'Bash' "$rtk hook $TOOL_NAME"
    }
}

Write-Host "RTK ready. Restart Claude Code to activate the hook."
Write-Host "Check savings after a session with: rtk gain"
