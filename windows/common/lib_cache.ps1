# Shared helper - must be dot-sourced.
# Defines Invoke-CheckAndBuildCache used by the tool wrapper functions (claude).
# Tool paths come from tool_profile.ps1 (profile.env at install time, TOOL_PROFILE in repo).
# Windows PowerShell 5.1 port of common/lib_cache.sh.

. (Join-Path $PSScriptRoot 'tool_profile.ps1')

# Resolves the Python launcher (the indexer and the hash contract depend on it).
function Get-PythonBin {
    if ($env:PYTHON_BIN) { return $env:PYTHON_BIN }
    return 'python'
}

# Hash contract: 8 first hex chars of MD5 of str(Path(project_dir).resolve()) as
# computed by Python. Delegating to Python is deliberate - it canonicalizes the
# path to its true on-disk casing, so the wrapper, the hooks and the indexer
# (hashlib.md5 in gen_context_cache.py) always agree on the same cache key.
# No other code may compute this hash.
function Get-ProjectHash([string]$Path) {
    $py = Get-PythonBin
    # .encode() with no argument (UTF-8 default) - avoids embedded quotes, which
    # PS 5.1 strips when passing arguments to native executables.
    $code = 'import hashlib,sys,pathlib; print(hashlib.md5(str(pathlib.Path(sys.argv[1]).resolve()).encode()).hexdigest()[:8])'
    $out = & $py -c $code $Path 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $out) {
        throw "Get-ProjectHash: '$py' failed for path '$Path' (is Python installed?)"
    }
    return ([string]($out | Select-Object -First 1)).Trim()
}

# Returns the git root of the current directory, or the current directory itself.
function Get-ProjectDir {
    $dir = & git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $dir) { return (Get-Location).Path }
    return [string]$dir
}

# Computes the cache file path for a project path.
function Get-CacheFileFor([string]$ProjectPath) {
    $hash = Get-ProjectHash $ProjectPath
    return (Join-Path $TOOL_HOME "projects\$hash\context_cache.md")
}

# Returns $true (stale) if the cache should be regenerated, $false (fresh) otherwise.
# Stale when: cache missing, older than CACHE_MAX_AGE_MIN, or any source file is newer.
# The mtime scan below catches real changes; the TTL is only a safety net,
# so a long default avoids useless rebuilds. Override with: $env:CACHE_MAX_AGE_MIN = 10
function Test-CacheStale([string]$CacheFile, [string]$ProjectDir) {
    if (-not (Test-Path -LiteralPath $CacheFile)) { return $true }

    $maxAgeMin = 60
    if ($env:CACHE_MAX_AGE_MIN) { $maxAgeMin = [int]$env:CACHE_MAX_AGE_MIN }

    $cacheTime = (Get-Item -LiteralPath $CacheFile).LastWriteTime
    $ageMin = ((Get-Date) - $cacheTime).TotalMinutes
    if ($ageMin -ge $maxAgeMin) { return $true }

    # Files only: directory mtimes bump on any child creation/removal (even ignored
    # files like .claudeignore), which would flag the cache stale on every launch.
    # -Depth 5 mirrors the bash find -maxdepth 6; Select-Object -First 1 stops the
    # enumeration as soon as one newer file is found.
    $newer = Get-ChildItem -LiteralPath $ProjectDir -Recurse -Depth 5 -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -notlike '.*' -and
            $_.FullName -notmatch '\\(\.git|node_modules|__pycache__|\.venv|dist|build)(\\|$)' -and
            $_.LastWriteTime -gt $cacheTime
        } |
        Select-Object -First 1
    if ($newer) { return $true }

    return $false
}

# Runs optional tool-specific pre-launch checks (e.g. Claude's RTK hook repair).
# Overlays provide tool_hooks.ps1 defining Invoke-ToolPreLaunchHook; absence is not an error.
function Invoke-ToolPreLaunch {
    $hooksFile = Join-Path $TOOL_HOME 'scripts\tool_hooks.ps1'
    if (-not (Test-Path -LiteralPath $hooksFile)) { return }
    . $hooksFile
    if (Get-Command Invoke-ToolPreLaunchHook -ErrorAction SilentlyContinue) { Invoke-ToolPreLaunchHook }
}

# Regenerates the project context index when stale; called by the shell wrappers.
# Never throws: a cache failure must not block the tool launch.
function Invoke-CheckAndBuildCache {
    try {
        # projectDir - git root, used as the indexing scope and cache hash key.
        # launchDir  - directory where the tool was invoked; receives the local
        #              instructions file and the ignore file.
        $projectDir = Get-ProjectDir
        $launchDir = (Get-Location).Path
        $cacheFile = Get-CacheFileFor $projectDir

        Invoke-ToolPreLaunch

        if (Test-CacheStale $cacheFile $projectDir) {
            Write-Host "Updating context cache..."
            & (Join-Path $TOOL_HOME 'scripts\setup_context_cache.ps1') $projectDir $launchDir
        } else {
            $maxAgeMin = 60
            if ($env:CACHE_MAX_AGE_MIN) { $maxAgeMin = [int]$env:CACHE_MAX_AGE_MIN }
            Write-Host "Context cache up to date (< ${maxAgeMin}min, no source changes)."
        }
    } catch {
        Write-Host "    [WARN] Context cache skipped: $($_.Exception.Message)"
    }
}

# Refreshes the cache only when the project was already indexed by a previous
# session. Shared by the PostToolUse hooks and the git hooks.
function Invoke-CacheRefreshIfIndexed([string]$ProjectDir) {
    $cacheFile = Get-CacheFileFor $ProjectDir
    if (-not (Test-Path -LiteralPath $cacheFile)) { return }
    & (Join-Path $TOOL_HOME 'scripts\setup_context_cache.ps1') $ProjectDir
}
