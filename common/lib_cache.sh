#!/bin/bash

# Shared helper — must be sourced.
# Defines _check_and_build_cache used by the tool shell wrappers (claude / copilot).
# Tool paths come from tool_profile.sh (profile.env at install time, TOOL_PROFILE in repo).

_LIB_CACHE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "$_LIB_CACHE_DIR/tool_profile.sh" || return 1

# Maximum cache age in minutes before forcing a regeneration.
# The mtime scan below catches real changes; this is only a safety net,
# so a long TTL avoids useless rebuilds. Override with: export CACHE_MAX_AGE_MIN=10
CACHE_MAX_AGE_MIN="${CACHE_MAX_AGE_MIN:-60}"

# Returns 0 (stale) if the cache should be regenerated, 1 (fresh) if it can be skipped.
# Stale when: cache missing, older than CACHE_MAX_AGE_MIN, or any source file is newer.
_isCacheStale() {
    local cache_file="$1"
    local project_dir="$2"

    [ -f "$cache_file" ] || return 0

    local now cache_mtime age_min
    now=$(date +%s)
    cache_mtime=$(stat -c %Y "$cache_file" 2>/dev/null) || return 0
    age_min=$(( (now - cache_mtime) / 60 ))
    [ "$age_min" -ge "$CACHE_MAX_AGE_MIN" ] && return 0

    find "$project_dir" -maxdepth 6 \
        -not -name ".*" \
        -newer "$cache_file" \
        -not -path "*/.git/*" \
        -not -path "*/node_modules/*" \
        -not -path "*/__pycache__/*" \
        -not -path "*/.venv/*" \
        -not -path "*/dist/*" \
        -not -path "*/build/*" \
        2>/dev/null | grep -q . && return 0

    return 1
}

# Runs optional tool-specific pre-launch checks (e.g. Claude's RTK hook repair).
# Overlays provide tool_hooks.sh defining _tool_pre_launch; absence is not an error.
_run_tool_pre_launch() {
    local hooks_file="$TOOL_HOME/scripts/tool_hooks.sh"
    [ -f "$hooks_file" ] || return 0
    source "$hooks_file"
    type _tool_pre_launch > /dev/null 2>&1 && _tool_pre_launch
}

# Regenerates the project context index when stale; called by the shell wrappers.
_check_and_build_cache() {
    # project_dir — git root, used as the indexing scope and cache hash key.
    # launch_dir  — directory where the tool was invoked; receives the local
    #               instructions file and the ignore file.
    local project_dir launch_dir project_hash cache_file
    project_dir=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    launch_dir=$(pwd)
    project_hash=$(echo -n "$project_dir" | md5sum | cut -c1-8)
    cache_file="$TOOL_HOME/projects/$project_hash/context_cache.md"

    _run_tool_pre_launch

    if _isCacheStale "$cache_file" "$project_dir"; then
        echo "Updating context cache..."
        bash "$TOOL_HOME/scripts/setup_context_cache.sh" "$project_dir" "$launch_dir"
    else
        echo "Context cache up to date (< ${CACHE_MAX_AGE_MIN}min, no source changes)."
    fi
}
