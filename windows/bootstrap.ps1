# Interactive wizard - guides a new Windows machine/user through the llm_cli setup:
#   1. installs missing dependencies (best-effort: npm/pip scriptable installs,
#      winget guidance for node/python/rtk.exe)
#   2. activates the optimization layer for Claude Code
#      (dot-sources claude_env.ps1, so the claude wrapper lands in THIS session -
#      this script must be dot-sourced, not executed)
#   3. runs the diagnostics so you leave with a verified, working setup
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

# --- 1. dependencies (best-effort: scriptable installs + winget guidance) ---

& (Join-Path $_rootDir 'common\setup_dependencies.ps1')
if ($LASTEXITCODE -ne 0) { print_err "Some dependencies are missing - the related steps may fail below." }

# --- 2. tool activation (Claude only - Copilot is not ported to Windows yet) ---

print_step "Activating Claude Code"
. (Join-Path $_rootDir 'claude\claude_env.ps1')

# --- 3. Atlassian + MCP (not ported) ---

print_step "Atlassian + Bitbucket credentials / global MCP"
print_info "[SKIP] Not ported to Windows yet (setup_atlassian.sh / setup_mcp_global.sh - use Linux/WSL)."

# --- 4. verification ---
# (Headroom is installed by the dependencies step and wrapped automatically
# during activation - setup_env.ps1 -Ensure; no dedicated step needed.)

print_step "Verifying setup"
$_projectPath = & git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0 -or -not $_projectPath) { $_projectPath = (Get-Location).Path }
$_checkScript = Join-Path $env:USERPROFILE '.claude\scripts\check_optimizations.ps1'
if (Test-Path -LiteralPath $_checkScript) {
    & $_checkScript claude $_projectPath
}

print_step "Done"
print_ok "Run 'claude' from any project directory."
