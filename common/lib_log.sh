#!/bin/bash

# Shared logging helpers — must be sourced.
# print_* for setup scripts, check_* for diagnostic scripts (with pass/fail counters).

OK_TAG="\033[0;32m[OK]\033[0m"
FAIL_TAG="\033[0;31m[FAIL]\033[0m"
WARN_TAG="\033[0;33m[WARN]\033[0m"
INFO_TAG="\033[0;34m[INFO]\033[0m"

pass=0
fail=0

# Prints a section header.
print_step() { echo "" && echo "==> $1"; }
# Prints a success line.
print_ok()   { echo "    [OK] $1"; }
# Prints an error line.
print_err()  { echo "    [ERROR] $1"; }
# Prints a plain info line.
print_info() { echo "    $1"; }

# Records and prints a passing diagnostic check.
check_ok()   { echo -e "  $OK_TAG   $1"; ((pass++)); }
# Records and prints a failing diagnostic check.
check_fail() { echo -e "  $FAIL_TAG $1"; ((fail++)); }
# Prints a non-blocking diagnostic warning.
check_warn() { echo -e "  $WARN_TAG $1"; }
# Prints a diagnostic info line.
check_info() { echo -e "  $INFO_TAG $1"; }
