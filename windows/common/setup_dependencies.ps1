# Installs missing runtime dependencies (best-effort: Windows has no scripted
# installer for every tool). Scriptable here: Claude Code (npm), headroom (pip).
# Everything else gets clear winget guidance instead of a silent failure.
# Windows PowerShell 5.1 port of common/setup_dependencies.sh.

. (Join-Path $PSScriptRoot 'lib_log.ps1')

$script:failures = 0

function Test-Bin([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# Reports a dependency that cannot be installed from a script on Windows.
function Assert-ManualDependency([string]$Name, [string]$Hint) {
    if (Test-Bin $Name) { print_ok "$Name present."; return }
    $script:failures++
    print_err "$Name not found - install it manually: $Hint"
}

# Installs a binary through its package runner when that runner is available.
function Install-ScriptedDependency([string]$Name, [string]$Runner, [string[]]$InstallArgs, [string]$RunnerHint) {
    if (Test-Bin $Name) { print_ok "$Name present."; return }
    if (-not (Test-Bin $Runner)) {
        $script:failures++
        print_err "$Name not found and $Runner unavailable - $RunnerHint"
        return
    }
    print_info "Installing $Name via $Runner..."
    & $Runner @InstallArgs
    if ($LASTEXITCODE -ne 0 -or -not (Test-Bin $Name)) {
        $script:failures++
        print_err "$Name installation failed - check the $Runner global bin dir is on PATH."
    } else {
        print_ok "$Name installed."
    }
}

print_step "Checking & installing dependencies (best-effort)"

Assert-ManualDependency git    "winget install Git.Git"
Assert-ManualDependency node   "winget install OpenJS.NodeJS.LTS (>= 20 required)"
Assert-ManualDependency python "winget install Python.Python.3.11"
Assert-ManualDependency rtk    "no scripted installer on Windows - get rtk.exe from github.com/rtk-ai/rtk releases and put it on PATH"

Install-ScriptedDependency claude   npm @('install', '-g', '@anthropic-ai/claude-code') 'install Node first.'
Install-ScriptedDependency headroom pip @('install', '--user', 'headroom-ai[all]')      'install Python first.'

if ($script:failures -gt 0) {
    print_err "$($script:failures) dependency step(s) need attention - see above."
    exit 1
}
print_ok "All dependencies present."
