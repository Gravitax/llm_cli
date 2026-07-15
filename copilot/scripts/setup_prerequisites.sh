#!/bin/bash

# Checks runtime dependencies and installs the Copilot CLI if missing.
# Must be sourced — uses return on failure.
# Requires lib_deps.sh to be sourced by the caller (copilot_env.sh does it).

# The wrapper function/alias would shadow `command -v copilot` resolution.
unset -f copilot 2>/dev/null
unalias copilot 2>/dev/null

ensure_node                              || return 1
ensure_npm_cli "@github/copilot" copilot || return 1
