#!/bin/bash

# Generates a compact project context index for the current (or given) directory.
# The index maps file → symbols (functions, classes) in a few hundred tokens,
# so the tool can target specific files without reading everything linearly.
# Tool paths (cache root, instructions file, ignore file) come from tool_profile.sh.
#
# project_path — git root (or explicit path): scoped for indexing and cache hash key.
# launch_dir   — directory where the tool was invoked: receives the local
#                instructions file and the ignore file. Defaults to project_path.
#
# Usage:
#   bash setup_context_cache.sh [project_path] [launch_dir]    # Generate index
#   bash setup_context_cache.sh -u [project_path]              # Remove index + entry

PYTHON_BIN="${PYTHON_BIN:-python3.11}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/tool_profile.sh" || exit 1

GEN_SCRIPT="$SCRIPT_DIR/gen_context_cache.py"
MARKER="# Project context index"

# Computes the cache file path for a project path.
cache_file_for() {
    local project_hash
    project_hash=$(echo -n "$1" | md5sum | cut -c1-8)
    echo "$TOOL_HOME/projects/$project_hash/context_cache.md"
}

generate_index() {
    local project_path launch_dir
    project_path="$(cd "${1:-$PWD}" && pwd)"
    # launch_dir defaults to project_path when called manually (not from the wrapper).
    launch_dir="$(cd "${2:-$project_path}" && pwd)"

    if [ ! -f "$GEN_SCRIPT" ]; then
        echo "    Error: $GEN_SCRIPT not found."
        return 1
    fi

    local cache_file backup_file
    cache_file=$(cache_file_for "$project_path")
    backup_file="${cache_file}.bak"

    cp "$cache_file" "$backup_file" 2>/dev/null || true

    # Stream output directly so the progress bar can update in real time.
    TOOL_HOME="$TOOL_HOME" $PYTHON_BIN "$GEN_SCRIPT" "$project_path" "$cache_file"
    local exit_code=$?

    if [ $exit_code -ne 0 ]; then
        if [ -f "$backup_file" ]; then
            mv "$backup_file" "$cache_file"
            echo "    [WARN] Index generation failed — previous cache restored." >&2
        fi
        return 1
    fi

    rm -f "$backup_file"

    if [ -f "$cache_file" ]; then
        if [ "$project_path" != "$launch_dir" ]; then
            remove_entry "$launch_dir"
        fi
        inject_instructions_entry "$cache_file" "$project_path" "$launch_dir"
    fi

    create_ignore_file "$launch_dir"

    # Install git hooks so mid-session structural changes also trigger a refresh.
    local git_hooks_script="$SCRIPT_DIR/setup_git_hooks.sh"
    if [ -f "$git_hooks_script" ]; then
        bash "$git_hooks_script" "$project_path"
    fi

    # The steps above rewrite files inside the project (instructions entry, ignore
    # file), which would make the cache look stale on the next launch and force a
    # rebuild every time. Touch it last so it is newer than those artifacts.
    touch "$cache_file"
}

# Creates the tool ignore file in the launch directory when absent.
create_ignore_file() {
    local project_path="$1"
    local ignore_file="$project_path/$TOOL_IGNORE_FILE"

    [ -f "$ignore_file" ] && return 0

    cat > "$ignore_file" << EOF
# $TOOL_IGNORE_FILE — files excluded from the context index (gitignore-style)

# Hidden files and directories
.*
!$TOOL_IGNORE_FILE
!.gitignore
!.env.example

# Dependencies
node_modules/
vendor/
.venv/
venv/
env/
site-packages/

# Build and dist
dist/
build/
out/
target/
__pycache__/
*.pyc
*.class
*.o
*.a
*.so
*.dll
*.exe

# Generated and minified assets
*.min.js
*.min.css
*.bundle.js
*.map

# Locks
package-lock.json
yarn.lock
pnpm-lock.yaml
poetry.lock
Pipfile.lock
Cargo.lock
composer.lock
Gemfile.lock

# Logs and coverage
*.log
logs/
*.out
coverage/
htmlcov/
lcov.info

# IDE and OS
.idea/
.vscode/
*.swp
.DS_Store
Thumbs.db

# Certificates and secrets
*.pem
*.key
*.cert
*.p12
*.pfx
*.jks

# Archives, binaries and media
*.zip
*.tar
*.tar.gz
*.rar
*.7z
*.jar
*.war
*.bin
*.dat
*.db
*.sqlite
*.sqlite3
*.png
*.jpg
*.jpeg
*.gif
*.ico
*.svg
*.webp
*.mp4
*.mp3
*.pdf
EOF
    echo "    [OK] $TOOL_IGNORE_FILE created at $ignore_file"
}

# Removes an existing index entry from an instructions file (by marker).
strip_entry() {
    local instructions_file="$1"
    grep -qF "$MARKER" "$instructions_file" 2>/dev/null || return 0
    $PYTHON_BIN - "$instructions_file" "$MARKER" << 'PYEOF'
import re, sys
path, marker = sys.argv[1:]
content = open(path).read()
pattern = re.compile(r'\n?' + re.escape(marker) + r'.*?(?=\n# |\Z)', re.DOTALL)
open(path, "w").write(pattern.sub("", content))
PYEOF
}

# Writes the index pointer entry into the local instructions file.
inject_instructions_entry() {
    local cache_file="$1"
    local project_path="$2"
    local launch_dir="${3:-$2}"
    local instructions_file="$launch_dir/$TOOL_INSTRUCTIONS_LOCAL"

    # Remove existing entry then append fresh (ensures path stays current).
    strip_entry "$instructions_file"

    local refresh_triggers
    if [ "$TOOL_HAS_AGENT_HOOKS" = "1" ]; then
        refresh_triggers="- Any Write tool call (new file created)
- git checkout, switch, merge, pull, rebase, clone
- Every \`$TOOL_NAME\` launch (stale detection via shell wrapper)"
    else
        refresh_triggers="- Every \`$TOOL_NAME\` launch (stale detection via shell wrapper)
- git checkout, switch, merge, pull, rebase (via git hooks)"
    fi

    cat >> "$instructions_file" << EOF

$MARKER
A compact symbol index of $project_path is pre-generated at:
  \`$cache_file\`
Read it at session start, identify the 2-3 relevant files, then open only those.
Format: path | LOC | symbols. A missing file is either in $TOOL_IGNORE_FILE or not yet created.

Auto-refresh (re-read the index after these events):
$refresh_triggers

Regenerate manually after large structural changes:
  bash $TOOL_HOME/scripts/setup_context_cache.sh $project_path

Global standards, MCP tools reference and git clone helper: see $TOOL_INSTRUCTIONS_GLOBAL
EOF
    echo "    [OK] $instructions_file entry updated"
}

remove_entry() {
    local project_path
    project_path="$(cd "${1:-$PWD}" && pwd)"
    local instructions_file="$project_path/$TOOL_INSTRUCTIONS_LOCAL"

    if grep -qF "$MARKER" "$instructions_file" 2>/dev/null; then
        strip_entry "$instructions_file"
        echo "    [OK] Context index entry removed from $instructions_file"
    else
        echo "    [OK] No context index entry found in $instructions_file"
    fi
}

# Removes the index entry and deletes the cache file.
remove_index() {
    local project_path
    project_path="$(cd "${1:-$PWD}" && pwd)"

    remove_entry "$project_path"

    local cache_file
    cache_file=$(cache_file_for "$project_path")
    if [ -f "$cache_file" ]; then
        rm -f "$cache_file"
        echo "    [OK] Cache file removed: $cache_file"
    fi
}

if [ "$1" = "-u" ]; then
    echo "Removing context cache..."
    remove_index "$2"
else
    echo "Generating project context index..."
    generate_index "$1" "$2"
fi
