# Shared settings.json editing helpers - must be dot-sourced (replaces jq).
# Round-trips the whole file through ConvertFrom/ConvertTo-Json so unknown fields
# (env, model, enabledPlugins, existing hooks...) are preserved automatically.
# Requires: lib_log.ps1 (Write-Utf8NoBom) and tool_profile.ps1 ($TOOL_HOME, $TOOL_NAME)
# dot-sourced by the caller.
# Windows PowerShell 5.1 port of the jq edits in common/setup_env.sh.

# Loads settings.json as a PSCustomObject (empty object when the file is absent).
function Get-SettingsObject([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $raw = Get-Content -Raw -LiteralPath $Path
        if ($raw -and $raw.Trim()) { return ($raw | ConvertFrom-Json) }
    }
    return New-Object PSObject
}

# Saves settings atomically (tmp + move) with a .bak of the previous version.
# -Depth 16 is mandatory: the default depth of 2 silently flattens nested hooks.
function Save-SettingsObject($Obj, [string]$Path) {
    $json = $Obj | ConvertTo-Json -Depth 16
    if (Test-Path -LiteralPath $Path) {
        Copy-Item -LiteralPath $Path -Destination "$Path.bak" -Force
    }
    $tmp = "$Path.tmp"
    Write-Utf8NoBom $tmp $json
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

# Adds a NoteProperty when missing (ConvertFrom-Json objects have no autovivification).
function Ensure-NoteProperty($Obj, [string]$Name, $Default) {
    if (-not ($Obj.PSObject.Properties.Name -contains $Name)) {
        $Obj | Add-Member -MemberType NoteProperty -Name $Name -Value $Default
    }
}

# Registers a PostToolUse hook in the tool settings if not already present.
# Command shape mirrors the entry rtk writes on Windows: absolute path + shell field.
# $Matcher    - tool matcher (e.g. "Bash", "Write")
# $ScriptName - script filename in $TOOL_HOME\scripts\ (e.g. "cache_refresh_on_git.ps1")
function Register-PostToolUseHook([string]$Matcher, [string]$ScriptName) {
    $settings = Join-Path $TOOL_HOME 'settings.json'

    if ((Test-Path -LiteralPath $settings) -and
        ((Get-Content -Raw -LiteralPath $settings) -match [regex]::Escape($ScriptName))) {
        Write-Host "    [OK] PostToolUse $Matcher hook ($ScriptName) already registered."
        return
    }

    $scriptPath = Join-Path $TOOL_HOME "scripts\$ScriptName"
    $cmd = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $scriptPath + '"'
    $entry = [pscustomobject]@{
        matcher = $Matcher
        hooks   = @([pscustomobject]@{ type = 'command'; command = $cmd; shell = 'powershell' })
    }

    $s = Get-SettingsObject $settings
    Ensure-NoteProperty $s 'hooks' ([pscustomobject]@{})
    Ensure-NoteProperty $s.hooks 'PostToolUse' @()
    $s.hooks.PostToolUse = @($s.hooks.PostToolUse) + @($entry)
    Save-SettingsObject $s $settings

    Write-Host "    [OK] PostToolUse $Matcher hook ($ScriptName) registered in $settings"
}

# Registers a PreToolUse hook (fallback path when `rtk init -g` cannot do it itself).
function Register-PreToolUseHook([string]$Matcher, [string]$Command) {
    $settings = Join-Path $TOOL_HOME 'settings.json'
    $entry = [pscustomobject]@{
        matcher = $Matcher
        hooks   = @([pscustomobject]@{ type = 'command'; command = $Command; shell = 'powershell' })
    }

    $s = Get-SettingsObject $settings
    Ensure-NoteProperty $s 'hooks' ([pscustomobject]@{})
    Ensure-NoteProperty $s.hooks 'PreToolUse' @()
    $s.hooks.PreToolUse = @($s.hooks.PreToolUse) + @($entry)
    Save-SettingsObject $s $settings

    Write-Host "    [OK] PreToolUse $Matcher hook registered in $settings"
}

# Allows reading the context cache without a permission prompt (Claude only).
# The cache lives outside the project (~/.claude/projects/), which Claude Code
# treats as out-of-workspace and would otherwise prompt for on every session.
function Ensure-CacheReadPermission {
    $settings = Join-Path $TOOL_HOME 'settings.json'
    $rule = "Read(~/.$TOOL_NAME/projects/**)"

    if ((Test-Path -LiteralPath $settings) -and
        ((Get-Content -Raw -LiteralPath $settings).Contains($rule))) {
        return
    }

    $s = Get-SettingsObject $settings
    Ensure-NoteProperty $s 'permissions' ([pscustomobject]@{})
    Ensure-NoteProperty $s.permissions 'allow' @()
    $s.permissions.allow = @($s.permissions.allow) + @($rule)
    Save-SettingsObject $s $settings

    Write-Host "    [OK] Cache read permission ($rule) registered in $settings"
}
