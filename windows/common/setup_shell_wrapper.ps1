# Writes a persistent <tool> wrapper function to the user's PowerShell profile.
# The wrapper refreshes the context cache (stale detection) before launching the tool.
# Idempotent - identified by begin/end marker comments; outdated blocks are replaced.
#
# Target: $PROFILE.CurrentUserAllHosts (profile.ps1) - loaded by every PowerShell
# host without touching the user's host-specific profile.
#
# Windows PowerShell 5.1 port of common/setup_shell_wrapper.sh.

. (Join-Path $PSScriptRoot 'tool_profile.ps1')
if (-not $TOOL_PROFILE_OK) { exit 1 }

$markerBegin = "# >>> $TOOL_NAME context-cache wrapper (llm_cli) >>>"
$markerEnd = "# <<< $TOOL_NAME context-cache wrapper (llm_cli) <<<"

# The block is expanded at load time, not at write time - single-quoted template.
# Get-Command -CommandType Application is the PS equivalent of bash `command <tool>`:
# it can only resolve the real binary, never this function (no recursion).
$block = @'
# >>> {{TOOL}} context-cache wrapper (llm_cli) >>>
function global:{{TOOL}} {
    # Delegates stale detection and cache rebuild to lib_cache.ps1 (single source of truth).
    . "$env:USERPROFILE\.{{TOOL}}\scripts\lib_cache.ps1"
    Invoke-CheckAndBuildCache
    # A headroom-wrapped tool cannot reach the API unless the local proxy is up.
    if (Test-Path "$env:USERPROFILE\.{{TOOL}}\scripts\lib_headroom.ps1") {
        . "$env:USERPROFILE\.{{TOOL}}\scripts\lib_headroom.ps1"
        Invoke-EnsureHeadroomProxy
    }
    Write-Host "Starting {{TOOL}}..."
    $exe = Get-Command {{TOOL}} -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($exe) { & $exe.Source @args }
    else { Write-Error "{{TOOL}} binary not found in PATH." }
}
# <<< {{TOOL}} context-cache wrapper (llm_cli) <<<
'@
$block = $block.Replace('{{TOOL}}', $TOOL_NAME)

$profilePath = $PROFILE.CurrentUserAllHosts

$existing = ''
if (Test-Path -LiteralPath $profilePath) {
    $existing = Get-Content -Raw -LiteralPath $profilePath
}

if ($existing.Contains($markerBegin)) {
    # Replace only if outdated: must delegate to lib_cache.ps1 AND ensure the headroom proxy.
    $blockPattern = '(?s)' + [regex]::Escape($markerBegin) + '.*?' + [regex]::Escape($markerEnd)
    $currentBlock = [regex]::Match($existing, $blockPattern).Value
    if ($currentBlock.Contains(".$TOOL_NAME\scripts\lib_headroom.ps1")) {
        Write-Host "    [OK] $TOOL_NAME wrapper already present in $profilePath"
        exit 0
    }
    $existing = [regex]::Replace($existing, '(?s)\r?\n?' + $blockPattern + '\r?\n?', '')
    Write-Host "    [OK] Outdated $TOOL_NAME wrapper replaced in $profilePath"
}

$newContent = $existing.TrimEnd("`r", "`n")
if ($newContent) { $newContent += "`r`n" }
$newContent += "`r`n" + ($block -replace "`r?`n", "`r`n") + "`r`n"

$profileDir = Split-Path -Parent $profilePath
if (-not (Test-Path -LiteralPath $profileDir)) {
    New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
}
# UTF-8 with BOM: PS 5.1 parses BOM-less .ps1 files as ANSI.
[IO.File]::WriteAllText($profilePath, $newContent, (New-Object System.Text.UTF8Encoding($true)))

Write-Host "    [OK] $TOOL_NAME wrapper added to $profilePath (takes effect in new terminals)"
