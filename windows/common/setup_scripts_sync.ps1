# Syncs shared scripts (windows\common\) plus the tool overlay (windows\<tool>\scripts\)
# and the shared Python indexer (common\gen_context_cache.py) to $TOOL_HOME\scripts\,
# so the tool can invoke them at a fixed path during sessions.
# Writes profile.env so installed copies resolve their own tool profile.
# Must be run from the repository (needs the windows\common\ and overlay layout).
# Windows PowerShell 5.1 port of common/setup_scripts_sync.sh.

. (Join-Path $PSScriptRoot 'tool_profile.ps1')
if (-not $TOOL_PROFILE_OK) { exit 1 }
. (Join-Path $PSScriptRoot 'lib_log.ps1')

$windowsDir = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $windowsDir
$overlayDir = Join-Path $windowsDir "$TOOL_NAME\scripts"
$genScript = Join-Path $repoRoot 'common\gen_context_cache.py'
$targetDir = Join-Path $TOOL_HOME 'scripts'

if ((Split-Path -Leaf $PSScriptRoot) -ne 'common' -or (Split-Path -Leaf $windowsDir) -ne 'windows') {
    Write-Host "    [SKIP] Scripts sync requires the source repository layout (windows\common\)."
    exit 0
}

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

try {
    Copy-Item -Path (Join-Path $PSScriptRoot '*.ps1') -Destination $targetDir -Force -ErrorAction Stop
    Copy-Item -LiteralPath $genScript -Destination $targetDir -Force -ErrorAction Stop
} catch {
    Write-Host "Error: failed to sync common scripts to $targetDir ($($_.Exception.Message))"
    exit 1
}

if (Test-Path -LiteralPath $overlayDir) {
    try {
        Copy-Item -Path (Join-Path $overlayDir '*.ps1') -Destination $targetDir -Force -ErrorAction Stop
    } catch {
        Write-Host "Error: failed to sync $TOOL_NAME overlay scripts to $targetDir ($($_.Exception.Message))"
        exit 1
    }
}

# profile.env lets installed copies resolve their tool profile without any env var.
Write-Utf8NoBom (Join-Path $targetDir 'profile.env') "TOOL_PROFILE=$TOOL_PROFILE`n"

# Clear any Zone.Identifier mark so synced scripts run under RemoteSigned policies.
Get-ChildItem -LiteralPath $targetDir -File | Unblock-File -ErrorAction SilentlyContinue

Write-Host "    [OK] Scripts synced to $targetDir (profile: $TOOL_PROFILE)"
