# Installs Headroom (context-compression proxy, github.com/headroomlabs-ai/headroom)
# and durably wraps the active tool so its API calls go through the local proxy
# (~15-20% token savings on coding agents, 60-95% on JSON-heavy tool output).
# Windows PowerShell 5.1 port of common/setup_headroom.sh.
#
# Usage:
#   powershell -File setup_headroom.ps1            install + wrap + verify
#   powershell -File setup_headroom.ps1 -Ensure    non-interactive repair: skips
#                                                  silently when not installed
#   powershell -File setup_headroom.ps1 -Unwrap    unwrap (restores direct API access)

param(
    [switch]$Ensure,
    [switch]$Unwrap
)

. (Join-Path $PSScriptRoot 'tool_profile.ps1')
if (-not $TOOL_PROFILE_OK) { exit 1 }
. (Join-Path $PSScriptRoot 'lib_log.ps1')
. (Join-Path $PSScriptRoot 'lib_settings.ps1')
. (Join-Path $PSScriptRoot 'lib_headroom.ps1')

function Get-HeadroomBin {
    return Get-Command headroom -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Install-Headroom {
    if (Get-HeadroomBin) { return $true }

    print_step "Installing headroom-ai"
    if (-not (Get-Command pip -ErrorAction SilentlyContinue)) {
        print_err "pip not found - install Python 3.10+ first."
        return $false
    }

    & pip install --user "headroom-ai[all]"
    if ($LASTEXITCODE -ne 0) { print_err "pip install headroom-ai failed."; return $false }
    if (-not (Get-HeadroomBin)) {
        print_err "headroom missing from PATH after install - add the Python Scripts dir to PATH."
        return $false
    }
    print_ok "headroom installed."
    return $true
}

# Writes or removes the durable proxy routing (env.ANTHROPIC_BASE_URL) in the
# tool settings - `headroom wrap` only sets it transiently for its own session.
function Set-ProxyRouting([string]$Action) {
    $settings = Join-Path $TOOL_HOME 'settings.json'
    $s = Get-SettingsObject $settings
    if ($Action -eq 'add') {
        Ensure-NoteProperty $s 'env' ([pscustomobject]@{})
        Ensure-NoteProperty $s.env 'ANTHROPIC_BASE_URL' ''
        $s.env.ANTHROPIC_BASE_URL = "http://127.0.0.1:$HEADROOM_PROXY_PORT"
    } elseif ($s.PSObject.Properties.Name -contains 'env') {
        $s.env.PSObject.Properties.Remove('ANTHROPIC_BASE_URL')
    }
    Save-SettingsObject $s $settings
}

function Set-HeadroomWrap {
    if (Test-HeadroomWrapped) { print_ok "$TOOL_NAME already wrapped."; return $true }

    print_step "Wrapping $TOOL_NAME with the headroom proxy"
    # Durable part 1 - `headroom wrap` registers the retrieve/compression MCP
    # servers and context tools. It also launches a session of the tool;
    # `-- --version` makes that child session exit immediately.
    $output = & headroom wrap $TOOL_NAME -- --version 2>&1
    if ($LASTEXITCODE -ne 0) { print_err "headroom wrap $TOOL_NAME failed: $output"; return $false }
    # Durable part 2 - proxy routing in settings.json (what `headroom doctor`
    # checks as "claude routed"); wrap alone only exports it transiently.
    Set-ProxyRouting 'add'
    if (-not (Test-HeadroomWrapped)) {
        print_err "wrap ran but $TOOL_HOME\settings.json shows no proxy routing."
        return $false
    }
    print_ok "$TOOL_NAME wrapped - durable proxy routing in $TOOL_HOME\settings.json."
    return $true
}

function Test-HeadroomHealth {
    print_step "Verifying headroom health"
    Invoke-EnsureHeadroomProxy
    if (-not (Test-HeadroomProxyAlive)) {
        print_err "headroom proxy is not reachable - $TOOL_NAME cannot call the API while wrapped."
        print_err "Unwrap with: powershell -File $PSCommandPath -Unwrap"
        return $false
    }
    # Doctor output is diagnostic: unrelated warnings (other tools, shell env)
    # must not fail the setup; the load-bearing checks above already did.
    & headroom doctor 2>&1 | ForEach-Object { Write-Host "    $_" }
    print_ok "headroom proxy reachable and $TOOL_NAME routed."
    return $true
}

function Remove-HeadroomWrap {
    if (-not (Get-HeadroomBin)) { print_err "headroom not installed - nothing to unwrap."; return $false }
    & headroom unwrap $TOOL_NAME
    if ($LASTEXITCODE -ne 0) { print_err "headroom unwrap $TOOL_NAME failed."; return $false }
    Set-ProxyRouting 'remove'
    print_ok "$TOOL_NAME unwrapped - API calls go directly to the provider again."
    return $true
}

# --- main ---

if ($TOOL_HAS_HEADROOM -ne 1) {
    print_info "[SKIP] headroom wrap not supported for the $TOOL_NAME profile yet."
    exit 0
}

if ($Unwrap) {
    if (Remove-HeadroomWrap) { exit 0 } else { exit 1 }
}

if ($Ensure -and -not (Get-HeadroomBin)) {
    print_info "[SKIP] headroom not installed - enable with: powershell -File $PSCommandPath"
    exit 0
}

if (-not (Install-Headroom)) { exit 1 }
if (-not (Set-HeadroomWrap)) { exit 1 }
if (Test-HeadroomHealth) { exit 0 } else { exit 1 }
