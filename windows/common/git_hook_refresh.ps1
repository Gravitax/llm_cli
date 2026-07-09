# Called by the sh git hooks (post-merge / post-checkout) installed by
# setup_git_hooks.ps1. Refreshes the context cache only when this tool home
# already indexed the project. Kept as a separate entrypoint so the hash
# contract (Get-ProjectHash) stays in exactly one place: lib_cache.ps1.
# The hook passes the project dir already converted to Windows form (cygpath -w).

param([string]$ProjectDir)

try {
    . (Join-Path $PSScriptRoot 'lib_cache.ps1')
    if (-not $TOOL_PROFILE_OK) { exit 0 }
    if (-not $ProjectDir) { $ProjectDir = (Get-Location).Path }
    Invoke-CacheRefreshIfIndexed $ProjectDir
} catch {
    # A cache refresh failure must never fail the git operation.
}
exit 0
