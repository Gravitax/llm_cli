#!/bin/bash

# Installs every missing runtime dependency of the optimization layer.
# Fully automatic (no prompts) — called by bootstrap.sh before tool activation.
# Failures are counted, reported and reflected in the exit code, but never
# abort the run: independent dependencies still get their chance to install.
#
# Usage: bash setup_dependencies.sh [claude] [copilot]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_log.sh"
source "$SCRIPT_DIR/lib_deps.sh"

failures=0
run_ensure() {
    "$@" || failures=$((failures + 1))
}

print_step "Checking & installing dependencies"

run_ensure ensure_apt_pkg curl curl
run_ensure ensure_apt_pkg git git
run_ensure ensure_jq
run_ensure ensure_node
run_ensure ensure_uv
run_ensure ensure_rtk
run_ensure ensure_headroom

command -v python3 > /dev/null 2>&1 \
    || print_info "[WARN] python3 not found — the context indexer needs it (apt-get install python3)."

for tool in "$@"; do
    case "$tool" in
        claude)  run_ensure ensure_npm_cli "@anthropic-ai/claude-code" claude ;;
        copilot) run_ensure ensure_npm_cli "@github/copilot" copilot ;;
        *)       print_err "Unknown tool '$tool' (expected claude|copilot)."; failures=$((failures + 1)) ;;
    esac
done

if [ "$failures" -gt 0 ]; then
    print_err "$failures dependency step(s) failed — see messages above."
    exit 1
fi
print_ok "All dependencies present."
