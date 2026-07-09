# Shared logging helpers - must be dot-sourced.
# print_* for setup scripts, check_* for diagnostic scripts (with pass/fail counters).
# Windows PowerShell 5.1 port of common/lib_log.sh.

$script:pass = 0
$script:fail = 0

# Prints a section header.
function print_step([string]$Message) { Write-Host ""; Write-Host "==> $Message" }
# Prints a success line.
function print_ok([string]$Message)   { Write-Host "    [OK] $Message" }
# Prints an error line.
function print_err([string]$Message)  { Write-Host "    [ERROR] $Message" }
# Prints a plain info line.
function print_info([string]$Message) { Write-Host "    $Message" }

# Records and prints a passing diagnostic check.
function check_ok([string]$Message) {
    Write-Host "  " -NoNewline
    Write-Host "[OK]" -ForegroundColor Green -NoNewline
    Write-Host "   $Message"
    $script:pass++
}

# Records and prints a failing diagnostic check.
function check_fail([string]$Message) {
    Write-Host "  " -NoNewline
    Write-Host "[FAIL]" -ForegroundColor Red -NoNewline
    Write-Host " $Message"
    $script:fail++
}

# Prints a non-blocking diagnostic warning.
function check_warn([string]$Message) {
    Write-Host "  " -NoNewline
    Write-Host "[WARN]" -ForegroundColor Yellow -NoNewline
    Write-Host " $Message"
}

# Prints a diagnostic info line.
function check_info([string]$Message) {
    Write-Host "  " -NoNewline
    Write-Host "[INFO]" -ForegroundColor Blue -NoNewline
    Write-Host " $Message"
}

# Writes a file as UTF-8 without BOM (PS 5.1 Out-File defaults to UTF-16;
# a BOM breaks .claudeignore parsing and sh git hook shebangs).
function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    [IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding($false)))
}

# Appends to a file as UTF-8 without BOM (creates the file when absent).
function Add-Utf8NoBom([string]$Path, [string]$Content) {
    [IO.File]::AppendAllText($Path, $Content, (New-Object System.Text.UTF8Encoding($false)))
}
