# Headroom proxy helpers - must be dot-sourced.
# Shared by setup_headroom.ps1, check_optimizations.ps1 and the shell wrapper.
# Windows counterpart of common/lib_headroom.sh.

. (Join-Path $PSScriptRoot 'tool_profile.ps1')
if (-not $TOOL_PROFILE_OK) { return }

# Default port of `headroom proxy`. Override with: $env:HEADROOM_PROXY_PORT = 8787
$HEADROOM_PROXY_PORT = if ($env:HEADROOM_PROXY_PORT) { $env:HEADROOM_PROXY_PORT } else { 8787 }

# True when the tool settings durably route API calls through the local proxy.
function Test-HeadroomWrapped {
    $settings = Join-Path $TOOL_HOME 'settings.json'
    if (-not (Test-Path -LiteralPath $settings)) { return $false }
    return [bool]((Get-Content -Raw -LiteralPath $settings) -match 'headroom|ANTHROPIC_BASE_URL.*(localhost|127\.0\.0\.1)')
}

# True when the local proxy answers on its port (any HTTP status counts:
# only connection-level failures mean the proxy is down).
function Test-HeadroomProxyAlive {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$HEADROOM_PROXY_PORT/" -UseBasicParsing -TimeoutSec 1 | Out-Null
        return $true
    } catch {
        return ($null -ne $_.Exception.Response)
    }
}

# Starts the proxy if the tool is wrapped and the proxy is down.
# Never blocks the tool launch: every failure degrades to a visible warning,
# because a wrapped tool with a dead proxy cannot reach the API at all.
function Invoke-EnsureHeadroomProxy {
    $headroom = Get-Command headroom -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $headroom) { return }
    if (-not (Test-HeadroomWrapped)) { return }
    if (Test-HeadroomProxyAlive) { return }

    Write-Host "Starting headroom proxy..."
    Start-Process -FilePath $headroom.Source -ArgumentList 'proxy' -WindowStyle Hidden
    foreach ($_attempt in 1..5) {
        Start-Sleep -Seconds 1
        if (Test-HeadroomProxyAlive) { return }
    }
    Write-Warning "headroom proxy failed to start - $TOOL_NAME API calls may fail. Disable with: headroom unwrap $TOOL_NAME"
}
