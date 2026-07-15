# Shared llm_cli configuration (enterprise URLs + Atlassian tokens).
# Must be dot-sourced. Windows counterpart of common/lib_config.sh.
# Single source of truth written by setup_atlassian.sh (Linux/WSL side).

$LLM_CLI_CONFIG = Join-Path $env:USERPROFILE '.config\llm_cli\atlassian.env'

# Returns a hashtable of the config values, or $null when not configured yet.
function Get-LlmCliConfig {
    if (-not (Test-Path -LiteralPath $LLM_CLI_CONFIG)) { return $null }
    $config = @{}
    foreach ($line in (Get-Content -LiteralPath $LLM_CLI_CONFIG)) {
        if ($line -match '^\s*([A-Z_]+)=(.*)$') { $config[$matches[1]] = $matches[2].Trim() }
    }
    return $config
}
