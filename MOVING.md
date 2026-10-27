# Continuing Thoma Studio on a new computer

You made a backup on the old laptop (`./deploy/backup.sh`) and put `thoma-backup-<date>.tar.gz` on
Google Drive. It holds everything that is not on GitHub:

| In the backup | What it is |
|---|---|
| `env` | your keys: Gemini, Telegram, YouTube API key... (this is the `.env` file) |
| `studio.db` | the database: ideas, every video's script, your approvals/rejections/feedback, the schedule |
| `out/0012-short` ... `out/0021-short`, `out/0018-long` | the videos still waiting for you (ready / approved / scheduled) |
| `config/` | the YouTube sign-in, if you had done it (only there once `auth-youtube` has run) |

**Keep that file private.** It contains your keys. Delete it from Drive once the new computer works.

> **Only one computer may run the studio.** Both would use the same Telegram bot, fight over your
> messages, and could make or upload the same video twice. From now on, don't run `thoma daemon`,
> `make` or the service on the old laptop. If you do make anything there, run `./deploy/backup.sh`
> again and move the new file over.

Pick the route that matches the new computer:
- **A. Linux** (Ubuntu/Debian), or Windows with WSL: below.
- **B. Windows with Docker Desktop**: further down.

---

## A. Linux (or WSL)

**1. Software** (once). Follow [SETUP_GUIDE.md section 2](SETUP_GUIDE.md#2-software-to-install):
git, Node.js 20+, then sign in to the two script writers:
```bash
npm i -g @qoder-ai/qodercli && qodercli        # type /login, sign in, exit
curl -fsSL https://claude.ai/install.sh | bash && claude   # sign in, exit (Claude checks every script)
```

**2. Get the code and your backup**
```bash
git clone https://github.com/thomasjoseph3/yt-exp.git thoma-studio
cd thoma-studio
```
Download `thoma-backup-<date>.tar.gz` from Google Drive and move it into this `thoma-studio` folder.

**3. Install and restore in one go**
```bash
./deploy/setup.sh thoma-backup-<date>.tar.gz
```
This installs everything (Python packages, the renderer, the voice model, the music) and puts
back your keys, database and videos. It asks for your password once.

**4. Check that everything came across**
```bash
uv run thoma status      # should list #12 ... #21 as "ready"
uv run thoma plan        # the week's calendar
ls out                   # 0012-short ... 0021-short, 0018-long
uv run thoma test-llm    # qoder and claude should say OK
```

**5. Connect YouTube** (once, about 15 minutes). Follow
[SETUP_GUIDE.md: "How to set up YouTube uploading"](SETUP_GUIDE.md#how-to-set-up-youtube-uploading-about-15-minutes)
to get `youtube_client.json`, then:
```bash
uv run thoma auth-youtube       # sign in with the Google account of the NEW English channel
```
Once the channel exists, put its handle in `config.yaml` → `channel.youtube_handle: "@yourhandle"`
(adds a subscribe link to the Instagram/Facebook captions).

**6. Start it**
- Running 24/7: `./deploy/install-service.sh`
- Running only at night (laptop): see [SETUP_GUIDE.md section 7b](SETUP_GUIDE.md#7b-running-it-only-at-night-laptop-night-shift),
  or simply leave `uv run thoma daemon` running overnight.

Go to **"After moving"** below.

---

## B. Windows with Docker Desktop

**1. Once:** Docker Desktop installed and set to start at sign-in, PC never sleeps when plugged in,
Git for Windows installed. See [SETUP_GUIDE.md: Docker](SETUP_GUIDE.md#the-easy-way-docker-recommended-for-windows-and-mac).

**2. Get the code**, in PowerShell:
```powershell
git clone https://github.com/thomasjoseph3/yt-exp.git thoma-studio
cd thoma-studio
```
Download `thoma-backup-<date>.tar.gz` from Google Drive into this `thoma-studio` folder.

**3. Unpack the backup and put each piece in place** (Windows 10/11 has `tar` built in):
```powershell
mkdir restore
tar -xzf thoma-backup-<date>.tar.gz -C restore
copy restore\env .env
mkdir data, out, secrets -Force
copy restore\studio.db data\
robocopy restore\out out /E
if (Test-Path restore\config) { robocopy restore\config secrets /E }
Remove-Item restore -Recurse -Force
```

**4. Two extra keys for Docker.** A container can't open a browser to log in, so add these to
`.env` (`notepad .env`):
- `QODER_PERSONAL_ACCESS_TOKEN=` from qoder.com/account/integrations
- `CLAUDE_CODE_OAUTH_TOKEN=` run `claude setup-token` on any computer with Claude Code and paste what it prints

**5. YouTube:** put the `youtube_client.json` file (from the YouTube setup steps in SETUP_GUIDE.md)
at `secrets\youtube_client.json`.

**6. Build, check, sign in, start:**
```powershell
docker compose build
docker compose run --rm studio thoma status      # should list #12 ... #21 as "ready"
docker compose run --rm studio thoma plan
docker compose run --rm studio thoma test-llm    # qoder and claude should say OK
docker compose run --rm --service-ports studio thoma auth-youtube
docker compose up -d
```

---

## After moving (both routes)

1. On Telegram, send **/status** and **/plan**. You should see the same videos and the week calendar.
   If the bot doesn't answer, the studio isn't running yet (step 6).
2. Your review list, waiting on Telegram:
   - **#13-17** (RAG / embeddings / OKF Shorts) and **#18** (RAG vs OKF long video), written by Claude Opus:
     `/approve` the ones you like. Approved scripts become the standard Qoder copies.
   - **#19** tokens and **#21** NotebookLM, written by Qoder.
     #21 has one line to change: `/fix 21 remove "I learned that the hard way" in scene 12`.
   - Reject **#12** (old sound mix) and **#20** (filler about what the website doesn't say):
     `/reject 12 old audio`, `/reject 20 talks about what the website does not say`.
3. **Until Google approves the YouTube API audit**, uploads stay private. The bot tells you each slot
   time; set it in the YouTube Studio app: the video → Visibility → Schedule.
4. The weekly rhythm: leave the studio running one night and it makes the whole week (3 long + 7 Shorts,
   about 6 hours). Approve on your phone whenever you like; each approved video takes the next free slot.

## Working on the code from the new computer

Open the `thoma-studio` folder in Claude Code or Qoder. They read `AGENTS.md` and `docs/memory/`
(all the decisions so far: voice speed, simple language, the schedule, the quality loop, what's
pending), so you can carry on where we left off. Just say what you want.

Open questions waiting for you (from the last session):
- **Malayalam version of the long videos** for @mallumonks: your own voice (you record the Malayalam
  script, scene by scene) or an AI voice?
- **Your own cloned voice** for Thoma: does the computer have an NVIDIA graphics card? And a 1-2 minute
  recording of you talking.

## If something didn't come across

| What you see | Fix |
|---|---|
| `status` shows no videos | `data/studio.db` is missing: copy `studio.db` from the backup into `data/` |
| Videos listed, but sending/approving says "file not found" | the `out/` folders are missing: copy them from the backup's `out/` into `out/` |
| `test-llm`: qoder FAILED | Linux: run `qodercli` and `/login` again. Docker: check `QODER_PERSONAL_ACCESS_TOKEN` in `.env` |
| Telegram silent | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` missing from `.env`: check the `env` file in the backup |
| `auth-youtube` says the client file is missing | redo the YouTube setup steps; the file goes to `~/.config/thoma-studio/` (Linux) or `secrets\` (Docker) |
