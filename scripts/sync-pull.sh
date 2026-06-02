#!/usr/bin/env bash
# sync-pull.sh — Pull changes from Beast Tower via Tailscale SSH
# Run this on Pink Tiger after working on code.
# Usage: ./sync-pull.sh

set -euo pipefail

BEAST="100.67.192.68"
BEAST_PATH="LP_Godfather_Deploy"
LOCAL_PATH="$HOME/Projects/LP_Godfather"

echo "🔁 Syncing Tiger ← Beast ..."

rsync -avz --delete \
  --exclude='.env' \
  --exclude='data/' \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  -e "ssh -o BatchMode=yes" \
  "fossnomade@${BEAST}:${BEAST_PATH}/" \
  "${LOCAL_PATH}/"

echo "✅ Sync done."
echo ""
echo "💡 Vergiss nicht zu commiten:"
echo "   cd ${LOCAL_PATH} && git add -A && git commit -m 'sync from beast'"
