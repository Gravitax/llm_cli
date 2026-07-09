#!/bin/bash

# Writes a persistent <tool>() wrapper to the user's shell profiles.
# The wrapper refreshes the context cache (stale detection) before launching the tool.
# Idempotent — identified by a marker comment. Outdated wrappers (not delegating
# to lib_cache.sh) are replaced automatically.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/tool_profile.sh" || exit 1

MARKER="# $TOOL_NAME context-cache wrapper"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
# Add any additional shell profile paths here to extend wrapper installation targets.
PROFILE_FILES=("$HOME/.zshrc" "$HOME/.bashrc")

remove_outdated_wrapper() {
    local profile="$1"
    $PYTHON_BIN - "$profile" "$MARKER" "$TOOL_NAME" << 'PYEOF'
import re, sys
path, marker, tool = sys.argv[1:]
content = open(path).read()
pattern = re.compile(r'\n?' + re.escape(marker) + r'\n' + re.escape(tool) + r'\(\).*?\n\}', re.DOTALL)
open(path, 'w').write(pattern.sub('', content))
PYEOF
}

write_wrapper() {
    local profile="$1"
    cat >> "$profile" << EOF

$MARKER
$TOOL_NAME() {
    # Delegates stale detection and cache rebuild to lib_cache.sh (single source of truth).
    source "\$HOME/.$TOOL_NAME/scripts/lib_cache.sh"
    _check_and_build_cache
    echo "Starting $TOOL_NAME..."
    command $TOOL_NAME "\$@"
}
EOF
    echo "    [OK] $TOOL_NAME wrapper added to $profile (takes effect in new terminals)"
}

for profile in "${PROFILE_FILES[@]}"; do
    [ -f "$profile" ] || continue
    if grep -qF "$MARKER" "$profile" 2>/dev/null; then
        # Replace if outdated: must delegate to lib_cache.sh (single source of truth).
        grep -A3 -F "$MARKER" "$profile" | grep -qF ".$TOOL_NAME/scripts/lib_cache.sh" && continue
        remove_outdated_wrapper "$profile"
        echo "    [OK] Outdated $TOOL_NAME wrapper replaced in $profile"
    fi
    write_wrapper "$profile"
done
