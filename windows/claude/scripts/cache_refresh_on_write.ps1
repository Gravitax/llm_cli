# PostToolUse hook - regenerates the context cache when Claude creates any file.
#
# Triggered by Claude Code after every Write tool call.
# Any new file is a structural change worth indexing - no extension filter applied.
#
# Registered in ~/.claude/settings.json under hooks.PostToolUse (matcher: Write).
# Windows PowerShell 5.1 port of claude/scripts/cache_refresh_on_write.sh.

try {
    # Drain stdin - Claude Code sends full tool JSON (incl. file content) via stdin pipe.
    # Not reading it can cause a broken-pipe on Claude Code's side, silently aborting the hook.
    $raw = [Console]::In.ReadToEnd()

    . (Join-Path $PSScriptRoot 'lib_cache.ps1')
    if (-not $TOOL_PROFILE_OK) { exit 0 }

    Invoke-CacheRefreshIfIndexed (Get-ProjectDir)
} catch {
    # A hook failure must never fail the tool call.
}
exit 0
