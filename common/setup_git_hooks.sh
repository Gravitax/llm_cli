#!/bin/bash

# Installs git hooks that regenerate the context cache after structural git operations.
# Covers post-merge (git pull / git merge) and post-checkout (git checkout / git switch).
# One hook serves both tools: it refreshes every tool home that has a cache for the repo.
#
# Also configures a global git template directory so future `git clone` and `git init`
# automatically inherit the same hooks.
#
# Usage:
#   bash setup_git_hooks.sh [project_path]     # Install hooks for a specific repo
#   bash setup_git_hooks.sh -u [project_path]  # Remove hooks from a repo

# Refreshes the cache of each tool that already indexed this project.
CACHE_REFRESH='
project_dir=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
project_hash=$(echo -n "$project_dir" | md5sum | cut -c1-8)
for tool_home in "$HOME/.claude" "$HOME/.copilot"; do
    [ -f "$tool_home/projects/$project_hash/context_cache.md" ] || continue
    bash "$tool_home/scripts/setup_context_cache.sh" "$project_dir"
done
'

POST_MERGE_HOOK="#!/bin/bash
# Context cache refresh — only for projects already indexed by a previous session.
$CACHE_REFRESH"

# post-checkout receives: $1=prev HEAD, $2=new HEAD, $3=1 (branch) or 0 (file).
# Only regenerate on branch checkouts — file checkouts do not change the structure.
POST_CHECKOUT_HOOK="#!/bin/bash
# Context cache refresh — only for projects already indexed by a previous session.
[ \"\$3\" = \"1\" ] || exit 0
$CACHE_REFRESH"

TEMPLATE_DIR="$HOME/.git-template"

install_global_template() {
    mkdir -p "$TEMPLATE_DIR/hooks"

    printf '%s' "$POST_MERGE_HOOK" > "$TEMPLATE_DIR/hooks/post-merge"
    printf '%s' "$POST_CHECKOUT_HOOK" > "$TEMPLATE_DIR/hooks/post-checkout"
    chmod +x "$TEMPLATE_DIR/hooks/post-merge" "$TEMPLATE_DIR/hooks/post-checkout"

    git config --global init.templateDir "$TEMPLATE_DIR"
    echo "    [OK] Git template configured at $TEMPLATE_DIR (applies to future git clone / git init)"
}

# Writes hook_content to hook_path, appending if an unrelated hook already exists there.
installHook() {
    local hook_path="$1"
    local hook_content="$2"

    if [ -f "$hook_path" ] && ! grep -qF "setup_context_cache.sh" "$hook_path" 2>/dev/null; then
        printf '\n%s' "$hook_content" >> "$hook_path"
    else
        printf '%s' "$hook_content" > "$hook_path"
    fi
    chmod +x "$hook_path"
}

install_repo_hooks() {
    local project_path
    project_path="$(cd "${1:-$PWD}" && pwd)"
    local git_hooks_dir="$project_path/.git/hooks"

    if [ ! -d "$git_hooks_dir" ]; then
        echo "    [SKIP] No .git/hooks found at $project_path — not a git repository."
        return 1
    fi

    installHook "$git_hooks_dir/post-merge"    "$POST_MERGE_HOOK"
    installHook "$git_hooks_dir/post-checkout" "$POST_CHECKOUT_HOOK"

    echo "    [OK] Git hooks installed in $git_hooks_dir"
}

remove_repo_hooks() {
    local project_path
    project_path="$(cd "${1:-$PWD}" && pwd)"
    local git_hooks_dir="$project_path/.git/hooks"

    for hook in post-merge post-checkout; do
        local hook_path="$git_hooks_dir/$hook"
        [ -f "$hook_path" ] || continue

        # Remove only the refresh block added by this script (old single-tool or new loop form).
        python3.11 - "$hook_path" << 'PYEOF'
import re, sys
path = sys.argv[1]
content = open(path).read()
patterns = [
    re.compile(r'\n?for tool_home in [^\n]*\n(?:.*\n)*?done\n?'),
    re.compile(r'\n?bash "\$HOME/\.(claude|copilot)/scripts/setup_context_cache\.sh".*\n?'),
]
for pattern in patterns:
    content = pattern.sub('', content)
open(path, 'w').write(content)
PYEOF
        echo "    [OK] Context cache hook cleaned in $hook_path"
    done
}

if [ "$1" = "-u" ]; then
    echo "Removing git hooks..."
    remove_repo_hooks "$2"
else
    echo "Installing git hooks..."
    install_global_template
    install_repo_hooks "$1"
fi
