# Thoma Explains — automated tech-explainer studio

Thoma, a small comic tech imp, explains AI and tech to beginners in animated tutorials
(ByteMonk-style diagrams, Fireship pace). Why it's built this way: STRATEGY.md.
This folder makes and posts them on its own:

| Format | Size | Where | How often |
|---|---|---|---|
| Tutorial | 16:9, ~5 min, chapters, thumbnail, captions | YouTube (auto) + Telegram file for Facebook | daily, 17:00 |
| Short / Reel | 9:16, 35–55 s, karaoke captions | YouTube Shorts (auto) + Telegram file for Instagram/Facebook | 2 a day, 09:30 and 18:30 |

Instagram/Facebook can also be fully automated (free Meta API, see Keys); until then the bot sends
you the full-quality file and a caption to copy.

Topics come from **IBM Technology, ByteMonk and Fireship** (their feeds and transcripts are used as
research only; every script, visual and voice is original) plus a backlog of evergreen beginner topics.

Everything runs locally for free except the voice (Gemini TTS, free tier) and the script
writing, which only Qoder (your Qoder credits) or Claude (your subscription) does. If neither is
available, the studio waits and retries rather than using a weaker model.

> **New machine?** Follow [SETUP_GUIDE.md](SETUP_GUIDE.md): requirements, accounts, keys and every step, in plain language.

## 1. Install (once)
```bash
cd "/home/toobler/Desktop/ollama yt/erp crm"
uv sync
uv run playwright install chromium-headless-shell
# voice model (~120 MB) if assets/models/ is empty:
curl -L -o assets/models/kokoro.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx
curl -L -o assets/models/voices.bin  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
cp .env.example .env
uv run thoma test-llm
```

## 2. Keys (fill `.env`)
- **Thoma's voice**: a free Gemini key from aistudio.google.com/apikey (no card needed) in `GEMINI_API_KEY`.
  It powers Gemini TTS (natural, styled voice). Add a second key as `GEMINI_API_KEY_2` as a backup. Then run
  `uv run thoma voices`, listen to `out/voices/*.wav`, and put your favourite in `voice.gemini_voice`.
  Optional second voice: Google Cloud Chirp 3 HD (`GOOGLE_TTS_API_KEY`, needs a billing card; the studio
  stops at 900k characters a month so it stays inside the free 1M).
- **YouTube upload**: Google Cloud Console → new project → enable *YouTube Data API v3* → OAuth consent screen
  (External, add yourself as test user) → Credentials → OAuth client ID → *Desktop app* → download JSON to
  `~/.config/thoma-studio/youtube_client.json` → `uv run thoma auth-youtube`.
  Google keeps API uploads **private** until your project passes the YouTube API audit: request it early
  (search "YouTube API Services audit form"). In testing mode the sign-in also expires every 7 days.
- **Facebook + Instagram**: an Instagram *professional* account linked to a Facebook Page, and a Meta app
  (developers.facebook.com) with `pages_manage_posts`, `pages_read_engagement`, `instagram_basic`,
  `instagram_content_publish`. Put the Page ID, a long-lived Page token and the IG user ID in `.env`.
- **Telegram** (recommended): make a bot with @BotFather, send it a message, put the token and your chat ID
  in `.env`. You get every new video on your phone and reply `/approve 12`, `/reject 12`, `/pause`, `/status`.

## 3. Try it
```bash
uv run thoma ideas              # pull topics
uv run thoma make short         # writes, voices and renders one Short (~3 min)
uv run thoma make long          # one 5-minute tutorial (~15-25 min to render on this laptop)
uv run thoma status
```
Videos land in `out/`. Approve one with `uv run thoma approve <id>`; it posts at the next slot.

## 4. Run it 24/7
```bash
./deploy/install-service.sh                 # systemd user service, restarts on crash, survives logout
journalctl --user -u thoma-studio -f        # watch it
systemctl --user stop thoma-studio          # stop it
```
Turn on fully hands-off posting (no approval) by setting `publish.auto_publish: true` in `config.yaml`,
ideally after a couple of weeks of approving videos and trusting the output.

## Working on it with a coding agent
`AGENTS.md` is the guide for Qoder, Qodo, Claude Code or any other agent (Qoder also reads
`.qoder/rules/`). Ask it things like "add a new visual type for timelines" or "make Shorts 3 a day".

## Moving to another computer
1. On the old machine: `./deploy/backup.sh` → `thoma-backup-<date>.tar.gz` (your keys, YouTube sign-in and
   video history; keep it private). Then stop it: `systemctl --user disable --now thoma-studio`, so the two
   machines never post the same thing.
2. Copy the project folder (or `git clone` it from your private repo) plus the backup file to the new machine.
3. There: `./deploy/setup.sh thoma-backup-<date>.tar.gz` (installs everything, downloads the voice model,
   restores the backup), log in to Qoder CLI, then `./deploy/install-service.sh`.

Linux is best for 24/7 (a small always-on PC or a cheap VPS works). On Windows, use WSL.

## Disk use
Long videos are kept 14 days as your copy (~14 files), Shorts are deleted once published (they live on
Telegram), failed ones after 3 days. Change it under `storage:` in config.yaml.
