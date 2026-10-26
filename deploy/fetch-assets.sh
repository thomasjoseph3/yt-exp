#!/usr/bin/env bash
# Downloads the files that are too big for git: the local backup voice model and the music.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/models assets/music
REL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
[ -s assets/models/kokoro.onnx ] || curl -fsSL -o assets/models/kokoro.onnx $REL/kokoro-v1.0.int8.onnx
[ -s assets/models/voices.bin ]  || curl -fsSL -o assets/models/voices.bin  $REL/voices-v1.0.bin
# Kevin MacLeod, CC BY 4.0 (credited automatically in descriptions)
for t in "Sneaky Snitch" "Fluffing a Duck" "Carefree" "Wallpaper" "Local Forecast - Elevator" "Inspired"; do
  [ -s "assets/music/$t.mp3" ] || curl -fsSL -o "assets/music/$t.mp3" "https://incompetech.com/music/royalty-free/mp3-royaltyfree/${t// /%20}.mp3"
done
# speech aligner (finds when each word is spoken, so visuals and captions stay in sync)
[ -d assets/models/whisper ] || uv run python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8', download_root='assets/models/whisper')"
echo "assets ready"
