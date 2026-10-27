#!/usr/bin/env bash
# Pack what is NOT in the code: secrets (.env), the YouTube sign-in, the database (ideas, scripts,
# your verdicts, the schedule) and the videos not published yet (ready / approved / scheduled).
# Usage: ./deploy/backup.sh   ->  thoma-backup-<date>.tar.gz   (keep it private: it holds your keys)
set -euo pipefail
cd "$(dirname "$0")/.."
STAGE="$(mktemp -d)"
[ -f .env ] && cp .env "$STAGE/env"
[ -f data/studio.db ] && cp data/studio.db "$STAGE/studio.db"
[ -d ~/.config/thoma-studio ] && cp -r ~/.config/thoma-studio "$STAGE/config"
[ -d secrets ] && [ ! -d "$STAGE/config" ] && cp -r secrets "$STAGE/config"   # Docker setup
if [ -f data/studio.db ]; then
  mkdir -p "$STAGE/out"
  python3 - "$STAGE/out" <<'PY'
import shutil, sqlite3, sys
from pathlib import Path
rows = sqlite3.connect("data/studio.db").execute(
    "SELECT path FROM videos WHERE status IN ('ready','approved','scheduled') AND path IS NOT NULL")
for (p,) in rows:
    folder = Path("out") / Path(p).parent.name
    if folder.is_dir():
        shutil.copytree(folder, Path(sys.argv[1]) / folder.name)
        print("  video", folder.name)
PY
fi
OUT="$(pwd)/thoma-backup-$(date +%Y%m%d).tar.gz"
tar -czf "$OUT" -C "$STAGE" .
rm -rf "$STAGE"
chmod 600 "$OUT"
echo "Saved $OUT"
