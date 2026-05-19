#!/usr/bin/env bash
#
# Push the current branch to both the studio and the public stage.
#
#   Studio (gitlab/origin): full linear history
#   Stage  (github):        squashed orphan snapshot, force-pushed
#
# Stage strategy keeps the public mirror as a curated showcase: every push
# produces a single root commit that reflects the current tree, with no
# trace of internal iterations. The studio remote is unaffected.
#
# Usage: bash scripts/push-all.sh [<branch>] [<release-message>]
#
set -euo pipefail

BRANCH="${1:-main}"
RELEASE_MSG="${2:-}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf "Error: run this script inside a git repository.\n" >&2
  exit 1
fi

STUDIO_REMOTE=""
if git remote get-url gitlab >/dev/null 2>&1; then
  STUDIO_REMOTE="gitlab"
elif git remote get-url origin >/dev/null 2>&1; then
  STUDIO_REMOTE="origin"
fi

if [[ -z "$STUDIO_REMOTE" ]]; then
  printf "Error: no studio remote found (expected 'gitlab' or 'origin').\n" >&2
  exit 1
fi

if ! git remote get-url github >/dev/null 2>&1; then
  printf "Error: missing 'github' stage remote. Run scripts/setup-dual-remote.sh first.\n" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  printf "Error: working tree is dirty. Commit or stash before running.\n" >&2
  exit 1
fi

if ! git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  printf "Error: local branch '%s' does not exist.\n" "$BRANCH" >&2
  exit 1
fi

git checkout --quiet "$BRANCH"

printf "[1/2] Studio: pushing '%s' to %s (full history)...\n" "$BRANCH" "$STUDIO_REMOTE"
git push "$STUDIO_REMOTE" "$BRANCH"

printf "[2/2] Stage: building squashed snapshot of '%s' for github (force)...\n" "$BRANCH"

SHORT="$(git rev-parse --short HEAD)"
DEFAULT_MSG="Public release snapshot of $BRANCH @ $SHORT"
COMMIT_MSG="${RELEASE_MSG:-$DEFAULT_MSG}"
TMP_BRANCH="_stage_snapshot_$(date +%s)"

cleanup() {
  git checkout --quiet "$BRANCH" 2>/dev/null || true
  git branch -D --quiet "$TMP_BRANCH" 2>/dev/null || true
}
trap cleanup EXIT

git checkout --quiet --orphan "$TMP_BRANCH"
git add -A
git commit --quiet -m "$COMMIT_MSG"
git push --force github "$TMP_BRANCH":"$BRANCH"

printf "Done. Studio (%s) + Stage (github) updated.\n" "$STUDIO_REMOTE"
