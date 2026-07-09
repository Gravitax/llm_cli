#!/bin/bash

# Clones a Bitbucket Server repository using credentials from ~/.git-credentials.
# Usage: git_clone_exail.sh <PROJECT>/<repo>
# Example: git_clone_exail.sh PL/evdroneservices

set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <PROJECT>/<repo>" >&2
    exit 1
fi

CRED=$(grep git.exail.com ~/.git-credentials | head -1)
GIT_USER=$(echo "$CRED" | sed 's|https://||;s|:.*||')
GIT_TOKEN=$(echo "$CRED" | sed 's|.*://[^:]*:||;s|@.*||')

git -c credential.helper="!f() { echo username=$GIT_USER; echo password=$GIT_TOKEN; }; f" \
    clone "https://git.exail.com/scm/$1.git"
