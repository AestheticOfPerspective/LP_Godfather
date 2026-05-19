#!/usr/bin/env bash
set -euo pipefail

printf "[1/4] Syntax check...\n"
python -m compileall -q .

printf "[2/4] Ensure .env is ignored...\n"
if git check-ignore -q .env; then
  printf "OK: .env is ignored.\n"
else
  printf "FAIL: .env is not ignored.\n"
  exit 1
fi

printf "[3/4] Ensure .env.example exists...\n"
test -f .env.example

printf "[4/4] Scan tracked files for likely secrets...\n"
if git ls-files | grep -v '\.env\.example' | xargs -r grep -nE "(BOT_TOKEN=|GEMINI_API_KEY=|NAVIDROME_PASS=|OPENAI_API_KEY=|AIza|xoxb-|ghp_)" | grep -v '\${'; then
  printf "FAIL: potential secret pattern found in tracked files.\n"
  exit 1
else
  printf "OK: no obvious secret patterns found in tracked files.\n"
fi

printf "Preflight passed.\n"
