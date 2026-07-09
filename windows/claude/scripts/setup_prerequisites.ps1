# Checks runtime dependencies and installs Claude Code if missing.
# Must be dot-sourced - callers test $PREREQUISITES_OK.
# Windows PowerShell 5.1 port of claude/scripts/setup_prerequisites.sh
# (adds a Python check: the indexer and the cache hash contract depend on it).

$PREREQUISITES_OK = $false

function Test-NodeVersion {
    $nodeVersion = ''
    if (Get-Command node -CommandType Application -ErrorAction SilentlyContinue) {
        $nodeVersion = (& node --version 2>$null | Select-Object -First 1)
    }
    $nodeMajor = 0
    if ($nodeVersion -match '^v(\d+)') { $nodeMajor = [int]$matches[1] }
    if ($nodeMajor -lt 20) {
        $found = if ($nodeVersion) { $nodeVersion } else { 'none' }
        Write-Host "Error: Node.js >= 20 required (found: $found)."
        Write-Host "Install: winget install OpenJS.NodeJS.LTS (or https://nodejs.org)"
        return $false
    }
    return $true
}

function Test-PythonVersion {
    $py = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { 'python' }
    $pyVersion = ''
    if (Get-Command $py -ErrorAction SilentlyContinue) {
        $pyVersion = (& $py --version 2>$null | Select-Object -First 1)
    }
    $ok = $false
    if ($pyVersion -match 'Python (\d+)\.(\d+)') {
        $ok = ([int]$matches[1] -gt 3) -or (([int]$matches[1] -eq 3) -and ([int]$matches[2] -ge 9))
    }
    if (-not $ok) {
        $found = if ($pyVersion) { $pyVersion } else { 'none' }
        Write-Host "Error: Python >= 3.9 required for the context indexer (found: $found)."
        Write-Host "Install: winget install Python.Python.3.11 (or set `$env:PYTHON_BIN to a valid launcher)"
        return $false
    }
    return $true
}

function Add-NpmBinToPath {
    # On Windows the npm prefix IS the global bin directory (no \bin suffix).
    $npmBin = (& npm config get prefix 2>$null | Select-Object -First 1)
    if (-not $npmBin) { return }
    $paths = $env:PATH -split ';'
    if (-not ($paths -contains $npmBin)) {
        $env:PATH = "$npmBin;$env:PATH"
    }
}

function Install-ClaudeCode {
    if (Test-Path Alias:claude) { Remove-Item Alias:claude -Force -ErrorAction SilentlyContinue }
    if (-not (Get-Command claude -CommandType Application -ErrorAction SilentlyContinue)) {
        Write-Host "Installing Claude Code via npm..."
        & npm install -g '@anthropic-ai/claude-code'
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: Claude Code installation failed."
            return $false
        }
    }
    return $true
}

function Disable-Telemetry {
    $env:DO_NOT_TRACK = '1'
    $env:CLAUDE_TELEMETRY_DISABLED = '1'
    $env:NO_UPDATE_NOTIFIER = '1'
}

if ((Test-NodeVersion) -and (Test-PythonVersion)) {
    Add-NpmBinToPath
    if (Install-ClaudeCode) {
        Disable-Telemetry
        $PREREQUISITES_OK = $true
    }
}
