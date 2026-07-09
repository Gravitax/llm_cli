#!/bin/bash

# PostToolUse hook — regenerates the context cache when Claude runs a structural git command.
#
# Triggered by Claude Code after every Bash tool call.
# Reads the tool call JSON from stdin, checks if the command was a structural git operation,
# and regenerates the cache if so.
#
# Structural git commands detected:
#   git clone, git checkout, git switch, git merge, git pull, git rebase
#
# Registered in ~/.claude/settings.json under hooks.PostToolUse.

set -euo pipefail

input=$(cat)

bash_command=$(echo "$input" | python3.11 - << 'PYEOF'
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("command", ""))
except Exception:
    print("")
PYEOF
)

if echo "$bash_command" | grep -qE '\bgit (clone|checkout|switch|merge|pull|rebase)\b'; then
    project_dir=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    project_hash=$(echo -n "$project_dir" | md5sum | cut -c1-8)
    [ -f "$HOME/.claude/projects/$project_hash/context_cache.md" ] || exit 0
    bash "$HOME/.claude/scripts/setup_context_cache.sh" "$project_dir" || true
fi
