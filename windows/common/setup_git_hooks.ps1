# Installs git hooks that regenerate the context cache after structural git operations.
# Covers post-merge (git pull / git merge) and post-checkout (git checkout / git switch).
# One hook serves both tools: it refreshes every tool home that has a cache for the repo.
#
# Also configures a global git template directory so future `git clone` and `git init`
# automatically inherit the same hooks.
#
# Git for Windows always runs hooks under its bundled sh.exe, so the hook files
# stay sh scripts (LF, no BOM); their body delegates to git_hook_refresh.ps1 so
# the hash contract stays in PowerShell/Python (a POSIX md5sum of /c/... paths
# would never match the cache key).
#
# Usage:
#   powershell -File setup_git_hooks.ps1 [project_path]     # Install hooks for a specific repo
#   powershell -File setup_git_hooks.ps1 -u [project_path]  # Remove hooks from a repo
#
# Windows PowerShell 5.1 port of common/setup_git_hooks.sh.

param(
    [switch]$u,
    [string]$ProjectPath
)

. (Join-Path $PSScriptRoot 'lib_log.ps1')

$HOOK_COMMENT = '# Context cache refresh - only for projects already indexed by a previous session.'

# Refreshes the cache of each tool that already indexed this project.
$CACHE_REFRESH = @(
    'project_dir=$(git rev-parse --show-toplevel 2>/dev/null || pwd)'
    'win_dir=$(cygpath -w "$project_dir" 2>/dev/null || echo "$project_dir")'
    'for tool_home in "$HOME/.claude" "$HOME/.copilot"; do'
    '    [ -f "$tool_home/scripts/git_hook_refresh.ps1" ] || continue'
    '    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$tool_home/scripts/git_hook_refresh.ps1")" "$win_dir" || true'
    'done'
) -join "`n"

$POST_MERGE_HOOK = "#!/bin/sh`n$HOOK_COMMENT`n$CACHE_REFRESH`n"

# post-checkout receives: $1=prev HEAD, $2=new HEAD, $3=1 (branch) or 0 (file).
# Only regenerate on branch checkouts - file checkouts do not change the structure.
$POST_CHECKOUT_HOOK = "#!/bin/sh`n$HOOK_COMMENT`n[ `"`$3`" = `"1`" ] || exit 0`n$CACHE_REFRESH`n"

$TEMPLATE_DIR = Join-Path $env:USERPROFILE '.git-template'

function Install-GlobalTemplate {
    $hooksDir = Join-Path $TEMPLATE_DIR 'hooks'
    New-Item -ItemType Directory -Force -Path $hooksDir | Out-Null

    Write-Utf8NoBom (Join-Path $hooksDir 'post-merge') $POST_MERGE_HOOK
    Write-Utf8NoBom (Join-Path $hooksDir 'post-checkout') $POST_CHECKOUT_HOOK

    & git config --global init.templateDir $TEMPLATE_DIR
    Write-Host "    [OK] Git template configured at $TEMPLATE_DIR (applies to future git clone / git init)"
}

# Writes hook content to hook path, appending if an unrelated hook already exists there.
function Install-Hook([string]$HookPath, [string]$HookContent) {
    $existing = ''
    if (Test-Path -LiteralPath $HookPath) {
        $existing = Get-Content -Raw -LiteralPath $HookPath
    }
    if ($existing -and -not $existing.Contains('git_hook_refresh.ps1')) {
        Write-Utf8NoBom $HookPath ($existing.TrimEnd("`r", "`n") + "`n`n" + $HookContent)
    } else {
        Write-Utf8NoBom $HookPath $HookContent
    }
}

function Install-RepoHooks([string]$Project) {
    if (-not $Project) { $Project = (Get-Location).Path }
    $projectPath = (Resolve-Path -LiteralPath $Project).ProviderPath
    $gitHooksDir = Join-Path $projectPath '.git\hooks'

    if (-not (Test-Path -LiteralPath $gitHooksDir)) {
        Write-Host "    [SKIP] No .git\hooks found at $projectPath - not a git repository."
        return
    }

    Install-Hook (Join-Path $gitHooksDir 'post-merge') $POST_MERGE_HOOK
    Install-Hook (Join-Path $gitHooksDir 'post-checkout') $POST_CHECKOUT_HOOK

    Write-Host "    [OK] Git hooks installed in $gitHooksDir"
}

function Remove-RepoHooks([string]$Project) {
    if (-not $Project) { $Project = (Get-Location).Path }
    $projectPath = (Resolve-Path -LiteralPath $Project).ProviderPath
    $gitHooksDir = Join-Path $projectPath '.git\hooks'

    foreach ($hook in @('post-merge', 'post-checkout')) {
        $hookPath = Join-Path $gitHooksDir $hook
        if (-not (Test-Path -LiteralPath $hookPath)) { continue }

        # Remove only the refresh block added by this script.
        $content = Get-Content -Raw -LiteralPath $hookPath
        $patterns = @(
            ('(?s)\r?\n?' + [regex]::Escape($HOOK_COMMENT) + '\n.*?done\n?'),
            '\r?\n?for tool_home in [^\n]*\n(?:.*\n)*?done\n?'
        )
        foreach ($pattern in $patterns) {
            $content = [regex]::Replace($content, $pattern, '')
        }
        Write-Utf8NoBom $hookPath $content
        Write-Host "    [OK] Context cache hook cleaned in $hookPath"
    }
}

if ($u) {
    Write-Host "Removing git hooks..."
    Remove-RepoHooks $ProjectPath
} else {
    Write-Host "Installing git hooks..."
    Install-GlobalTemplate
    Install-RepoHooks $ProjectPath
}
