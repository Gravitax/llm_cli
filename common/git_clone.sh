#!/bin/bash

# Clones a Bitbucket Server repository from the configured host, using the
# credentials stored in ~/.git-credentials by setup_atlassian.sh.
# Usage: git_clone.sh <PROJECT>/<repo>
# Example: git_clone.sh PL/myservice

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_config.sh"

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <PROJECT>/<repo>" >&2
    exit 1
fi

require_llm_cli_config || exit 1

HOST="${BITBUCKET_URL#https://}"
CRED=$(grep "@${HOST}" ~/.git-credentials 2>/dev/null | head -1 || true)
if [ -z "$CRED" ]; then
    echo "    [ERROR] No credentials for $HOST in ~/.git-credentials — run setup_atlassian.sh first." >&2
    exit 1
fi

GIT_USER=$(echo "$CRED" | sed 's|https://||;s|:.*||')
GIT_TOKEN=$(echo "$CRED" | sed 's|.*://[^:]*:||;s|@.*||')

git -c credential.helper="!f() { echo username=$GIT_USER; echo password=$GIT_TOKEN; }; f" \
    clone "$BITBUCKET_URL/scm/$1.git"
