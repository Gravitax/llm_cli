# Verifies that the token optimizations are correctly configured for the active tool.
# Checks: RTK (Claude only), PostToolUse hooks (Claude only), headroom wrap,
# PowerShell wrapper, context cache, instructions entries.
#
# Usage: powershell -File check_optimizations.ps1 [claude|copilot] [project_path]
# (the tool argument is optional when run from an installed $TOOL_HOME\scripts\ copy)
#
# Windows PowerShell 5.1 port of common/check_optimizations.sh.

param(
    [string]$Tool,
    [string]$ProjectPath
)

# Optional first positional argument selects the tool profile.
if ($Tool -in @('claude', 'copilot')) {
    $env:TOOL_PROFILE = $Tool
} elseif ($Tool -and -not $ProjectPath) {
    $ProjectPath = $Tool
}

. (Join-Path $PSScriptRoot 'tool_profile.ps1')
if (-not $TOOL_PROFILE_OK) { exit 1 }
. (Join-Path $PSScriptRoot 'lib_log.ps1')
. (Join-Path $PSScriptRoot 'lib_cache.ps1')

$SETTINGS_FILE = Join-Path $TOOL_HOME 'settings.json'
# Keep in sync with the target in setup_shell_wrapper.ps1.
$PROFILE_FILES = @($PROFILE.CurrentUserAllHosts, $PROFILE.CurrentUserCurrentHost)

function Check-RtkDependencies {
    print_step "RTK dependencies"

    $rtk = Get-Command rtk -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($rtk) {
        check_ok "rtk $(& $rtk.Source --version) at $($rtk.Source)"
    } else {
        check_fail "rtk not found in PATH"
        check_warn "Fix: powershell -File $TOOL_HOME\scripts\setup_rtk.ps1"
    }

    # Python replaces jq as the load-bearing dependency on Windows (indexer + hash).
    $py = Get-PythonBin
    $pyVersion = ''
    if (Get-Command $py -ErrorAction SilentlyContinue) {
        $pyVersion = (& $py --version 2>$null | Select-Object -First 1)
    }
    if ($pyVersion -match 'Python 3') {
        check_ok "$pyVersion ($py)"
    } else {
        check_fail "Python 3 not found (required by the context indexer)"
        check_warn "Fix: winget install Python.Python.3.11"
    }
    return [bool]$rtk
}

function Check-RtkHook {
    print_step "RTK hook installation"

    # RTK registers a native PreToolUse hook - settings.json only.
    $hookCmd = $null
    if (Test-Path -LiteralPath $SETTINGS_FILE) {
        try {
            $s = Get-Content -Raw -LiteralPath $SETTINGS_FILE | ConvertFrom-Json
            foreach ($entry in @($s.hooks.PreToolUse)) {
                foreach ($hook in @($entry.hooks)) {
                    if ($hook.command -match 'rtk') { $hookCmd = $hook.command; break }
                }
                if ($hookCmd) { break }
            }
        } catch {}
    }

    if ($hookCmd) {
        check_ok "PreToolUse hook registered in settings.json: $hookCmd"
    } else {
        check_fail "RTK PreToolUse hook not found in $SETTINGS_FILE"
        check_warn "Fix: powershell -File $TOOL_HOME\scripts\setup_rtk.ps1"
    }

    if (Test-Path -LiteralPath (Join-Path $TOOL_HOME 'RTK.md')) {
        check_ok "RTK.md present: $TOOL_HOME\RTK.md"
    } else {
        check_fail "RTK.md not found - the agent won't have RTK usage instructions"
        check_warn "Fix: powershell -File $TOOL_HOME\scripts\setup_rtk.ps1"
    }

    $globalRaw = ''
    if (Test-Path -LiteralPath $TOOL_INSTRUCTIONS_GLOBAL) {
        $globalRaw = Get-Content -Raw -LiteralPath $TOOL_INSTRUCTIONS_GLOBAL
    }
    if ($globalRaw.Contains('@RTK.md')) {
        check_ok "@RTK.md referenced in $(Split-Path -Leaf $TOOL_INSTRUCTIONS_GLOBAL)"
    } else {
        check_fail "@RTK.md missing from $TOOL_INSTRUCTIONS_GLOBAL"
        check_warn "Fix: powershell -File $TOOL_HOME\scripts\setup_context.ps1"
    }
}

function Check-RtkSavings {
    print_step "RTK token savings"

    # rtk emits UTF-8 (box-drawing chars); PS 5.1 decodes captured native output
    # with the OEM codepage by default, producing mojibake. Switch just for the capture.
    $prevEncoding = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        $savings = (& rtk gain 2>$null | Out-String)
    } finally {
        [Console]::OutputEncoding = $prevEncoding
    }
    if (-not $savings -or $savings -match 'No tracking|No data') {
        check_warn "No savings data yet - run a session first, then: rtk gain"
        return
    }
    check_ok "RTK savings data available (rtk gain)"
    foreach ($line in ($savings.TrimEnd() -split "`r?`n")) { Write-Host "       $line" }
}

function Check-PostToolUseHooks {
    print_step "Cache refresh hooks (PostToolUse)"

    $raw = ''
    if (Test-Path -LiteralPath $SETTINGS_FILE) { $raw = Get-Content -Raw -LiteralPath $SETTINGS_FILE }
    foreach ($hookScript in @('cache_refresh_on_git.ps1', 'cache_refresh_on_write.ps1')) {
        if ($raw.Contains($hookScript)) {
            check_ok "PostToolUse hook registered: $hookScript"
        } else {
            check_fail "PostToolUse hook missing: $hookScript"
            check_warn "Fix: powershell -File $TOOL_HOME\scripts\setup_env.ps1"
        }
    }
}

function Check-ShellWrapper {
    print_step "PowerShell wrapper"

    $wrapperMarker = "# >>> $TOOL_NAME context-cache wrapper (llm_cli) >>>"
    $found = $false
    foreach ($profileFile in $PROFILE_FILES) {
        if (-not (Test-Path -LiteralPath $profileFile)) { continue }
        if ((Get-Content -Raw -LiteralPath $profileFile).Contains($wrapperMarker)) {
            check_ok "$TOOL_NAME wrapper present in $profileFile"
            $found = $true
        }
    }
    if (-not $found) {
        check_fail "$TOOL_NAME wrapper missing from PowerShell profiles"
        check_warn "Fix: powershell -File $PSScriptRoot\setup_shell_wrapper.ps1"
    }
}

function Check-ContextCache([string]$Project) {
    print_step "Context cache"

    $cacheFile = $null
    try { $cacheFile = Get-CacheFileFor $Project } catch {}

    check_info "Project : $Project"
    check_info "Cache   : $cacheFile"

    if ($cacheFile -and (Test-Path -LiteralPath $cacheFile)) {
        $item = Get-Item -LiteralPath $cacheFile
        $lines = (Get-Content -LiteralPath $cacheFile | Measure-Object -Line).Lines
        $sizeKb = [math]::Round($item.Length / 1KB, 1)
        $generated = ''
        $genLine = Select-String -LiteralPath $cacheFile -Pattern 'Generated:' | Select-Object -First 1
        if ($genLine -and $genLine.Line -match 'Generated: ([^|]+)') { $generated = $matches[1].Trim() }
        check_ok "Cache exists ($lines lines, ${sizeKb}KB, generated: $generated)"
    } else {
        check_fail "No cache found"
        check_warn "Fix: powershell -File $TOOL_HOME\scripts\setup_context_cache.ps1 $Project"
    }
}

function Check-Instructions([string]$Project) {
    print_step "Instructions files"

    $localFile = Join-Path $Project $TOOL_INSTRUCTIONS_LOCAL

    if (Test-Path -LiteralPath $TOOL_INSTRUCTIONS_GLOBAL) {
        $lines = (Get-Content -LiteralPath $TOOL_INSTRUCTIONS_GLOBAL | Measure-Object -Line).Lines
        check_ok "Global instructions: $TOOL_INSTRUCTIONS_GLOBAL ($lines lines)"
    } else {
        check_fail "$TOOL_INSTRUCTIONS_GLOBAL not found"
        check_warn "Fix: powershell -File $TOOL_HOME\scripts\setup_context.ps1"
    }

    $localHasEntry = (Test-Path -LiteralPath $localFile) -and
        ((Get-Content -Raw -LiteralPath $localFile).Contains('# Project context index'))
    if ($localHasEntry) {
        check_ok "'# Project context index' entry present in $localFile"
    } else {
        check_fail "'# Project context index' missing from $localFile"
        check_warn "Fix: powershell -File $TOOL_HOME\scripts\setup_context_cache.ps1 $Project"
    }
}

function Check-Headroom {
    print_step "Headroom compression proxy (optional)"

    . (Join-Path $PSScriptRoot 'lib_headroom.ps1')

    $headroom = Get-Command headroom -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $headroom) {
        if (Test-HeadroomWrapped) {
            check_fail "settings.json routes API calls through headroom but the binary is missing - $TOOL_NAME requests will fail"
            check_warn "Fix: powershell -File $TOOL_HOME\scripts\setup_headroom.ps1 (reinstall) or remove the wrap from settings.json"
        } else {
            check_info "headroom not installed - optional, ~15-20% extra token savings"
            check_info "Enable if wanted: powershell -File $TOOL_HOME\scripts\setup_headroom.ps1"
        }
        return
    }

    check_ok "headroom present at $($headroom.Source)"

    if (Test-HeadroomWrapped) {
        check_ok "$TOOL_NAME wrapped - proxy routing active in settings.json"
    } else {
        check_info "$TOOL_NAME not wrapped - enable with: powershell -File $TOOL_HOME\scripts\setup_headroom.ps1"
        return
    }

    # doctor's exit code also covers unrelated tools (codex, shell env), so the
    # load-bearing check is done directly: wrapped + proxy reachability.
    if (Test-HeadroomProxyAlive) {
        check_ok "headroom proxy reachable on port $HEADROOM_PROXY_PORT"
    } else {
        check_info "proxy not running - the shell wrapper starts it at $TOOL_NAME launch"
        check_info "Details anytime: headroom doctor"
    }

    $perf = (& headroom perf 2>$null | Select-Object -First 5)
    foreach ($line in @($perf)) { Write-Host "       $line" }
}

function Check-GlobalMcp {
    print_step "Global MCP (optional)"

    $mcpConfig = Join-Path $env:USERPROFILE '.claude.json'
    if ($TOOL_NAME -ne 'claude') { $mcpConfig = Join-Path $env:USERPROFILE '.copilot\mcp-config.json' }

    $registered = (Test-Path -LiteralPath $mcpConfig) -and
        ((Get-Content -Raw -LiteralPath $mcpConfig).Contains('io.github.b1ff/atlassian-dc-mcp-jira'))
    if ($registered) {
        check_ok "Atlassian/Bitbucket MCP registered globally ($mcpConfig)"
    } else {
        check_info "MCP not registered globally - Jira/Confluence/Bitbucket tools unavailable"
        check_info "(MCP setup is not ported to Windows yet - configure from Linux/WSL if needed)"
    }
}

if (-not $ProjectPath) { $ProjectPath = Get-ProjectDir }

Write-Host ""
Write-Host "Checking $TOOL_NAME optimizations..."

if ($TOOL_HAS_RTK_HOOK -eq 1) {
    $rtkPresent = Check-RtkDependencies
    if ($rtkPresent) {
        Check-RtkHook
        Check-RtkSavings
    }
}

if ($TOOL_HAS_AGENT_HOOKS -eq 1) {
    Check-PostToolUseHooks
}

if ($TOOL_HAS_HEADROOM -eq 1) {
    Check-Headroom
}

Check-ShellWrapper
Check-ContextCache $ProjectPath
Check-Instructions $ProjectPath
Check-GlobalMcp

Write-Host ""
Write-Host "=============================="
Write-Host "  Passed: " -NoNewline
Write-Host $script:pass -ForegroundColor Green -NoNewline
Write-Host "  Failed: " -NoNewline
Write-Host $script:fail -ForegroundColor Red
Write-Host "=============================="
Write-Host ""

if ($script:fail -ne 0) { exit 1 } else { exit 0 }
