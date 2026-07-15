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

# Settings mode (claude): durable proxy routing lives in settings.json, the
# wrapper only has to make sure the proxy is up before launching.
write_settings_wrapper() {
    local profile="$1"
    cat >> "$profile" << EOF

$MARKER
$TOOL_NAME() {
    # Delegates stale detection and cache rebuild to lib_cache.sh (single source of truth).
    source "\$HOME/.$TOOL_NAME/scripts/lib_cache.sh"
    _check_and_build_cache
    # A headroom-wrapped tool cannot reach the API unless the local proxy is up.
    if [ -f "\$HOME/.$TOOL_NAME/scripts/lib_headroom.sh" ]; then
        source "\$HOME/.$TOOL_NAME/scripts/lib_headroom.sh"
        _ensure_headroom_proxy
    fi
    echo "Starting $TOOL_NAME..."
    command $TOOL_NAME "\$@"
}
EOF
}

# Launcher mode (copilot): headroom has no durable routing for this tool — it
# builds a transient BYOK env, so the launch itself must go through it.
# The routing decision lives in lib_headroom.sh (_launch_with_headroom).
write_launcher_wrapper() {
    local profile="$1"
    cat >> "$profile" << EOF

$MARKER
$TOOL_NAME() {
    # Delegates stale detection and cache rebuild to lib_cache.sh (single source of truth).
    source "\$HOME/.$TOOL_NAME/scripts/lib_cache.sh"
    _check_and_build_cache
    source "\$HOME/.$TOOL_NAME/scripts/lib_headroom.sh"
    echo "Starting $TOOL_NAME..."
    # Routes through headroom when a provider key or Copilot OAuth allows it,
    # plain launch otherwise. Opt out per session with LLM_CLI_NO_HEADROOM=1.
    _launch_with_headroom $TOOL_NAME "\$@"
}
EOF
}

write_wrapper() {
    local profile="$1"
    if [ "$TOOL_HEADROOM_MODE" = "launcher" ]; then
        write_launcher_wrapper "$profile"
    else
        write_settings_wrapper "$profile"
    fi
    echo "    [OK] $TOOL_NAME wrapper added to $profile (takes effect in new terminals)"
}

for profile in "${PROFILE_FILES[@]}"; do
    [ -f "$profile" ] || continue
    if grep -qF "$MARKER" "$profile" 2>/dev/null; then
        # Replace if outdated: the up-to-date wrapper handles headroom for its mode
        # (settings -> lib_headroom.sh proxy ensure, launcher -> headroom wrap launch).
        if [ "$TOOL_HEADROOM_MODE" = "launcher" ]; then
            current_marker="_launch_with_headroom"
        else
            current_marker=".$TOOL_NAME/scripts/lib_headroom.sh"
        fi
        grep -A14 -F "$MARKER" "$profile" | grep -qF "$current_marker" && continue
        remove_outdated_wrapper "$profile"
        echo "    [OK] Outdated $TOOL_NAME wrapper replaced in $profile"
    fi
    write_wrapper "$profile"
done
