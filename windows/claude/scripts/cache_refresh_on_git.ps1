# PostToolUse hook - regenerates the context cache when Claude runs a structural git command.
#
# Triggered by Claude Code after every Bash tool call.
# Reads the tool call JSON from stdin, checks if the command was a structural git operation,
# and regenerates the cache if so.
#
# Structural git commands detected:
#   git clone, git checkout, git switch, git merge, git pull, git rebase
#
# Registered in ~/.claude/settings.json under hooks.PostToolUse.
# Windows PowerShell 5.1 port of claude/scripts/cache_refresh_on_git.sh.

try {
    # Drain stdin first - Claude Code sends the full tool JSON via stdin pipe.
    # Not reading it can cause a broken-pipe on Claude Code's side.
    $raw = [Console]::In.ReadToEnd()

    . (Join-Path $PSScriptRoot 'lib_cache.ps1')
    if (-not $TOOL_PROFILE_OK) { exit 0 }

    $bashCommand = ''
    try {
        $data = $raw | ConvertFrom-Json
        $bashCommand = [string]$data.tool_input.command
    } catch {}

    if ($bashCommand -match '\bgit (clone|checkout|switch|merge|pull|rebase)\b') {
        Invoke-CacheRefreshIfIndexed (Get-ProjectDir)
    }
} catch {
    # A hook failure must never fail the tool call.
}
exit 0
