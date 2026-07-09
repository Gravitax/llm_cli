# Generates a compact project context index for the current (or given) directory.
# The index maps file -> symbols (functions, classes) in a few hundred tokens,
# so the tool can target specific files without reading everything linearly.
# Tool paths (cache root, instructions file, ignore file) come from tool_profile.ps1.
#
# ProjectPath - git root (or explicit path): scoped for indexing and cache hash key.
# LaunchDir   - directory where the tool was invoked: receives the local
#               instructions file and the ignore file. Defaults to ProjectPath.
#
# Usage:
#   powershell -File setup_context_cache.ps1 [project_path] [launch_dir]   # Generate index
#   powershell -File setup_context_cache.ps1 -u [project_path]            # Remove index + entry
#
# Windows PowerShell 5.1 port of common/setup_context_cache.sh.

param(
    [switch]$u,
    [string]$ProjectPath,
    [string]$LaunchDir
)

. (Join-Path $PSScriptRoot 'lib_cache.ps1')
if (-not $TOOL_PROFILE_OK) { exit 1 }
. (Join-Path $PSScriptRoot 'lib_log.ps1')

$MARKER = '# Project context index'

# Installed copies have the indexer next to them; the repo keeps it in common\ (shared with bash).
$GEN_SCRIPT = Join-Path $PSScriptRoot 'gen_context_cache.py'
if (-not (Test-Path -LiteralPath $GEN_SCRIPT)) {
    $repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $GEN_SCRIPT = Join-Path $repoRoot 'common\gen_context_cache.py'
}

# Removes an existing index entry from an instructions file (by marker).
function Remove-EntryFromFile([string]$InstructionsFile) {
    if (-not (Test-Path -LiteralPath $InstructionsFile)) { return }
    $content = Get-Content -Raw -LiteralPath $InstructionsFile
    if (-not $content -or -not $content.Contains($MARKER)) { return }
    $pattern = '(?s)\r?\n?' + [regex]::Escape($MARKER) + '.*?(?=\r?\n# |\z)'
    $new = [regex]::Replace($content, $pattern, '')
    Write-Utf8NoBom $InstructionsFile $new
}

# Writes the index pointer entry into the local instructions file.
function Add-InstructionsEntry([string]$CacheFile, [string]$Project, [string]$Launch) {
    $instructionsFile = Join-Path $Launch $TOOL_INSTRUCTIONS_LOCAL

    # Remove existing entry then append fresh (ensures path stays current).
    Remove-EntryFromFile $instructionsFile

    if ($TOOL_HAS_AGENT_HOOKS -eq 1) {
        $refreshTriggers = @'
- Any Write tool call (new file created)
- git checkout, switch, merge, pull, rebase, clone
- Every `{{TOOL}}` launch (stale detection via shell wrapper)
'@
    } else {
        $refreshTriggers = @'
- Every `{{TOOL}}` launch (stale detection via shell wrapper)
- git checkout, switch, merge, pull, rebase (via git hooks)
'@
    }
    $refreshTriggers = $refreshTriggers.Replace('{{TOOL}}', $TOOL_NAME)

    $entry = @'

{{MARKER}}
A compact symbol index of {{PROJECT}} is pre-generated at:
  `{{CACHE}}`
Read it at session start, identify the 2-3 relevant files, then open only those.
Format: path | LOC | symbols. A missing file is either in {{IGNORE}} or not yet created.

Auto-refresh (re-read the index after these events):
{{TRIGGERS}}

Regenerate manually after large structural changes:
  powershell -NoProfile -File {{TOOL_HOME}}\scripts\setup_context_cache.ps1 {{PROJECT}}

Global standards and MCP tools reference: see {{GLOBAL}}
'@
    $entry = $entry.Replace('{{MARKER}}', $MARKER).
        Replace('{{PROJECT}}', $Project).
        Replace('{{CACHE}}', $CacheFile).
        Replace('{{IGNORE}}', $TOOL_IGNORE_FILE).
        Replace('{{TRIGGERS}}', $refreshTriggers).
        Replace('{{TOOL_HOME}}', $TOOL_HOME).
        Replace('{{GLOBAL}}', $TOOL_INSTRUCTIONS_GLOBAL)

    Add-Utf8NoBom $instructionsFile ($entry + "`n")
    Write-Host "    [OK] $instructionsFile entry updated"
}

# Creates the tool ignore file in the launch directory when absent.
function New-IgnoreFile([string]$Launch) {
    $ignoreFile = Join-Path $Launch $TOOL_IGNORE_FILE
    if (Test-Path -LiteralPath $ignoreFile) { return }

    $body = @"
# $TOOL_IGNORE_FILE - files excluded from the context index (gitignore-style)

# Hidden files and directories
.*
!$TOOL_IGNORE_FILE
!.gitignore
!.env.example

# Dependencies
node_modules/
vendor/
.venv/
venv/
env/
site-packages/

# Build and dist
dist/
build/
out/
target/
__pycache__/
*.pyc
*.class
*.o
*.a
*.so
*.dll
*.exe

# Generated and minified assets
*.min.js
*.min.css
*.bundle.js
*.map

# Locks
package-lock.json
yarn.lock
pnpm-lock.yaml
poetry.lock
Pipfile.lock
Cargo.lock
composer.lock
Gemfile.lock

# Logs and coverage
*.log
logs/
*.out
coverage/
htmlcov/
lcov.info

# IDE and OS
.idea/
.vscode/
*.swp
.DS_Store
Thumbs.db

# Certificates and secrets
*.pem
*.key
*.cert
*.p12
*.pfx
*.jks

# Archives, binaries and media
*.zip
*.tar
*.tar.gz
*.rar
*.7z
*.jar
*.war
*.bin
*.dat
*.db
*.sqlite
*.sqlite3
*.png
*.jpg
*.jpeg
*.gif
*.ico
*.svg
*.webp
*.mp4
*.mp3
*.pdf
"@
    Write-Utf8NoBom $ignoreFile ($body + "`n")
    Write-Host "    [OK] $TOOL_IGNORE_FILE created at $ignoreFile"
}

function Remove-Entry([string]$Project) {
    if (-not $Project) { $Project = (Get-Location).Path }
    $projectPath = (Resolve-Path -LiteralPath $Project).ProviderPath
    $instructionsFile = Join-Path $projectPath $TOOL_INSTRUCTIONS_LOCAL

    $hasEntry = (Test-Path -LiteralPath $instructionsFile) -and
        ((Get-Content -Raw -LiteralPath $instructionsFile).Contains($MARKER))
    if ($hasEntry) {
        Remove-EntryFromFile $instructionsFile
        Write-Host "    [OK] Context index entry removed from $instructionsFile"
    } else {
        Write-Host "    [OK] No context index entry found in $instructionsFile"
    }
}

# Removes the index entry and deletes the cache file.
function Remove-Index([string]$Project) {
    if (-not $Project) { $Project = (Get-Location).Path }
    $projectPath = (Resolve-Path -LiteralPath $Project).ProviderPath

    Remove-Entry $projectPath

    $cacheFile = Get-CacheFileFor $projectPath
    if (Test-Path -LiteralPath $cacheFile) {
        Remove-Item -LiteralPath $cacheFile -Force
        Write-Host "    [OK] Cache file removed: $cacheFile"
    }
}

function New-Index([string]$Project, [string]$Launch) {
    if (-not $Project) { $Project = (Get-Location).Path }
    $projectPath = (Resolve-Path -LiteralPath $Project).ProviderPath
    # LaunchDir defaults to the project path when called manually (not from the wrapper).
    if (-not $Launch) { $Launch = $projectPath }
    $launchDir = (Resolve-Path -LiteralPath $Launch).ProviderPath

    if (-not (Test-Path -LiteralPath $GEN_SCRIPT)) {
        Write-Host "    Error: $GEN_SCRIPT not found."
        return $false
    }

    $cacheFile = Get-CacheFileFor $projectPath
    $backupFile = "$cacheFile.bak"
    if (Test-Path -LiteralPath $cacheFile) {
        Copy-Item -LiteralPath $cacheFile -Destination $backupFile -Force
    }

    # Stream output directly so the progress bar can update in real time.
    $py = Get-PythonBin
    & $py $GEN_SCRIPT $projectPath $cacheFile

    if ($LASTEXITCODE -ne 0) {
        if (Test-Path -LiteralPath $backupFile) {
            Move-Item -LiteralPath $backupFile -Destination $cacheFile -Force
            Write-Host "    [WARN] Index generation failed - previous cache restored."
        }
        return $false
    }
    Remove-Item -LiteralPath $backupFile -Force -ErrorAction SilentlyContinue

    if (Test-Path -LiteralPath $cacheFile) {
        if ($projectPath -ne $launchDir) {
            Remove-Entry $launchDir
        }
        Add-InstructionsEntry $cacheFile $projectPath $launchDir
    }

    New-IgnoreFile $launchDir

    # Install git hooks so mid-session structural changes also trigger a refresh.
    $gitHooksScript = Join-Path $PSScriptRoot 'setup_git_hooks.ps1'
    if (Test-Path -LiteralPath $gitHooksScript) {
        & $gitHooksScript $projectPath
    }

    # The steps above rewrite files inside the project (instructions entry, ignore
    # file), which would make the cache look stale on the next launch and force a
    # rebuild every time. Touch it last so it is newer than those artifacts.
    if (Test-Path -LiteralPath $cacheFile) {
        (Get-Item -LiteralPath $cacheFile).LastWriteTime = Get-Date
    }
    return $true
}

if ($u) {
    Write-Host "Removing context cache..."
    Remove-Index $ProjectPath
} else {
    Write-Host "Generating project context index..."
    if (-not (New-Index $ProjectPath $LaunchDir)) { exit 1 }
}
