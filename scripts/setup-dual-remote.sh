#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  printf "Usage: %s <github-ssh-url>\n" "$0"
  printf "Example: %s git@github.com:lifeplay/godfather-bot.git\n" "$0"
  exit 1
fi

GITHUB_URL="$1"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf "Error: run this script inside a git repository.\n"
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  ORIGIN_URL="$(git remote get-url origin)"
  if git remote get-url gitlab >/dev/null 2>&1; then
    printf "gitlab remote already exists, keeping it.\n"
  else
    git remote rename origin gitlab
    printf "Renamed origin -> gitlab (%s)\n" "$ORIGIN_URL"
  fi
fi

if git remote get-url github >/dev/null 2>&1; then
  git remote set-url github "$GITHUB_URL"
  printf "Updated github remote to %s\n" "$GITHUB_URL"
else
  git remote add github "$GITHUB_URL"
  printf "Added github remote %s\n" "$GITHUB_URL"
fi

printf "\nCurrent remotes:\n"
git remote -v
