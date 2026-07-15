# Interactive wizard - guides a new Windows machine/user through the llm_cli setup:
#   1. activates the optimization layer for Claude Code
#      (dot-sources claude_env.ps1, so the claude wrapper lands in THIS session -
#      this script must be dot-sourced, not executed)
#   2. runs the diagnostics so you leave with a verified, working setup
#
# Atlassian credentials and global MCP registration are not ported to Windows yet;
# the Copilot CLI profile is not ported either.
#
# Usage:
#   . .\windows\bootstrap.ps1
#
# Windows PowerShell 5.1 port of bootstrap.sh.

# Dot-source detection: a plain execution cannot define the claude wrapper
# in the caller's session, so refuse to proceed silently broken.
if ($MyInvocation.InvocationName -ne '.') {
    Write-Host "Error: this script must be dot-sourced, not executed."
    Write-Host "Usage: . $($MyInvocation.MyCommand.Path)"
    exit 1
}

$_rootDir = $PSScriptRoot
. (Join-Path $_rootDir 'common\lib_log.ps1')

print_step "llm_cli setup wizard (Windows)"
print_info "Root: $_rootDir"

# --- 1. tool activation (Claude only - Copilot is not ported to Windows yet) ---

print_step "Activating Claude Code"
. (Join-Path $_rootDir 'claude\claude_env.ps1')

# --- 2. Atlassian + MCP (not ported) ---

print_step "Atlassian + Bitbucket credentials / global MCP"
print_info "[SKIP] Not ported to Windows yet (setup_atlassian.sh / setup_mcp_global.sh - use Linux/WSL)."

# --- 3. Headroom compression proxy (optional) ---

print_step "Headroom compression proxy (optional, ~15-20% token savings)"
$_headroomScript = Join-Path $env:USERPROFILE '.claude\scripts\setup_headroom.ps1'
if (Test-Path -LiteralPath $_headroomScript) {
    $_reply = Read-Host "  Install headroom and wrap claude now? [Y/n]"
    if (-not $_reply -or $_reply -match '^[Yy]$') {
        & $_headroomScript
        if ($LASTEXITCODE -ne 0) { print_err "Headroom setup failed." }
    } else {
        print_info "Skipped - enable later with: powershell -File $_headroomScript"
    }
}

# --- 4. verification ---

print_step "Verifying setup"
$_projectPath = & git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0 -or -not $_projectPath) { $_projectPath = (Get-Location).Path }
$_checkScript = Join-Path $env:USERPROFILE '.claude\scripts\check_optimizations.ps1'
if (Test-Path -LiteralPath $_checkScript) {
    & $_checkScript claude $_projectPath
}

print_step "Done"
print_ok "Run 'claude' from any project directory."
