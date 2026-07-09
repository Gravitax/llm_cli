#!/bin/bash

# Syncs shared scripts (common/) plus the tool overlay (<tool>/scripts/) to
# $TOOL_HOME/scripts/, so the tool can invoke them at a fixed path during sessions.
# Writes profile.env so installed copies resolve their own tool profile.
# Must be run from the repository (needs the common/ and overlay layout).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/tool_profile.sh" || exit 1

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OVERLAY_DIR="$REPO_ROOT/$TOOL_NAME/scripts"
TARGET_DIR="$TOOL_HOME/scripts"

if [ ! -d "$SCRIPT_DIR" ] || [ "$(basename "$SCRIPT_DIR")" != "common" ]; then
    echo "    [SKIP] Scripts sync requires the source repository layout."
    exit 0
fi

mkdir -p "$TARGET_DIR"

cp "$SCRIPT_DIR"/*.sh "$SCRIPT_DIR"/*.py "$TARGET_DIR/" \
    || { echo "Error: failed to sync common scripts to $TARGET_DIR"; exit 1; }

if [ -d "$OVERLAY_DIR" ]; then
    cp "$OVERLAY_DIR"/*.sh "$TARGET_DIR/" \
        || { echo "Error: failed to sync $TOOL_NAME overlay scripts to $TARGET_DIR"; exit 1; }
fi

# profile.env lets installed copies resolve their tool profile without any env var.
echo "TOOL_PROFILE=$TOOL_PROFILE" > "$TARGET_DIR/profile.env"

chmod +x "$TARGET_DIR"/*.sh "$TARGET_DIR"/*.py

echo "    [OK] Scripts synced to $TARGET_DIR (profile: $TOOL_PROFILE)"
