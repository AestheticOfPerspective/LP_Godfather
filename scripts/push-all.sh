#!/usr/bin/env bash
set -euo pipefail

BRANCH="${1:-main}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf "Error: run this script inside a git repository.\n"
  exit 1
fi

git remote get-url gitlab >/dev/null 2>&1 || {
  printf "Error: missing gitlab remote.\n"
  exit 1
}

git remote get-url github >/dev/null 2>&1 || {
  printf "Error: missing github remote.\n"
  exit 1
}

printf "Pushing branch '%s' to gitlab...\n" "$BRANCH"
git push gitlab "$BRANCH"

printf "Pushing branch '%s' to github...\n" "$BRANCH"
git push github "$BRANCH"

printf "Done.\n"
