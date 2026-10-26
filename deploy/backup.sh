#!/usr/bin/env bash
# Pack what is NOT in the code: secrets (.env), the YouTube sign-in, and the video history.
# Usage: ./deploy/backup.sh   ->  thoma-backup-<date>.tar.gz   (keep it private: it holds your keys)
set -euo pipefail
cd "$(dirname "$0")/.."
STAGE="$(mktemp -d)"
[ -f .env ] && cp .env "$STAGE/env"
[ -f data/studio.db ] && cp data/studio.db "$STAGE/studio.db"
[ -d ~/.config/thoma-studio ] && cp -r ~/.config/thoma-studio "$STAGE/config"
OUT="$(pwd)/thoma-backup-$(date +%Y%m%d).tar.gz"
tar -czf "$OUT" -C "$STAGE" .
rm -rf "$STAGE"
chmod 600 "$OUT"
echo "Saved $OUT"
