#!/bin/bash

# PostToolUse hook — regenerates the context cache when Claude creates any file.
#
# Triggered by Claude Code after every Write tool call.
# Any new file is a structural change worth indexing — no extension filter applied.
#
# Registered in ~/.claude/settings.json under hooks.PostToolUse (matcher: Write).

set -euo pipefail

# Drain stdin — Claude Code sends full tool JSON (incl. file content) via stdin pipe.
# Not reading it can cause a broken-pipe on Claude Code's side, silently aborting the hook.
input=$(cat)

project_dir=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
project_hash=$(echo -n "$project_dir" | md5sum | cut -c1-8)
[ -f "$HOME/.claude/projects/$project_hash/context_cache.md" ] || exit 0
bash "$HOME/.claude/scripts/setup_context_cache.sh" "$project_dir" || true
