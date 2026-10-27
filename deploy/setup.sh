#!/usr/bin/env bash
# Set up Thoma Studio on a new Linux machine (Ubuntu/Debian; on Windows use WSL).
# Run from the project folder:  ./deploy/setup.sh  [path/to/thoma-backup.tar.gz]
set -euo pipefail
cd "$(dirname "$0")/.."

command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

uv sync
uv run playwright install --with-deps chromium-headless-shell   # asks for sudo once (system libraries)

./deploy/fetch-assets.sh

if [ -n "${1:-}" ]; then   # restore keys, YouTube sign-in and the video history from backup.sh
  STAGE="$(mktemp -d)"; tar -xzf "$1" -C "$STAGE"
  [ -f "$STAGE/env" ] && cp "$STAGE/env" .env
  [ -f "$STAGE/studio.db" ] && mkdir -p data && cp "$STAGE/studio.db" data/studio.db
  [ -d "$STAGE/out" ] && mkdir -p out && cp -rn "$STAGE/out/." out/   # videos still waiting to go out
  [ -d "$STAGE/config" ] && mkdir -p ~/.config && cp -r "$STAGE/config" ~/.config/thoma-studio
  rm -rf "$STAGE"
  echo "Restored keys, YouTube sign-in and history from $1"
fi
[ -f .env ] || cp .env.example .env

if ! command -v qodercli >/dev/null; then
  echo "Qoder CLI not found. Install Node.js 20+, then:  npm i -g @qoder-ai/qodercli  &&  qodercli  (then /login)"
fi
uv run thoma test-llm
echo
echo "Next: check .env, run 'uv run thoma preview assets/samples/short_rag.json short',"
echo "then './deploy/install-service.sh' to run it 24/7."
