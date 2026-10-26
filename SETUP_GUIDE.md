# Setting up Thoma Studio on a new computer

This guide walks you through everything you need to get the studio running on a fresh machine,
from the computer itself to the accounts and keys, in the order you'll actually do things.
Set aside about an hour the first time. Most of it is creating accounts and copying keys.

---

## 1. What kind of computer you need

The studio is happiest on **Linux** (Ubuntu or Debian). It runs around the clock, so a machine
that stays on works best: an old laptop or desktop, a small home server, or a cheap cloud VPS.

- **Windows?** Use **Docker Desktop** (next section). That's the easiest. Or install WSL with
  Ubuntu and follow the manual steps inside the Ubuntu terminal.
- **Mac?** Everything works for making videos. The 24/7 background service uses Linux's systemd,
  so on a Mac you'd run `uv run thoma daemon` in a terminal you keep open instead.

**Minimum hardware**

| | Minimum | Comfortable |
|---|---|---|
| CPU | 4 cores | 8 cores (renders twice as fast) |
| RAM | 8 GB | 16 GB |
| Free disk space | 10 GB | 20 GB+ |
| GPU | not needed | not needed |
| Internet | always on | always on |

How the disk space gets used: the app with its browser and voice model is about 1.5 GB, and it
keeps up to 14 days of long videos (roughly 1–1.5 GB). Shorts are deleted once they're on
Telegram and YouTube.

Rendering speed, roughly: a Short takes 3–4 minutes and a 5-minute video takes 15–25 minutes on an
8-core laptop. That's well within a day's schedule.

---

## The easy way: Docker (recommended for Windows and Mac)

If the machine has **Docker Desktop**, you can skip most of this guide. The studio comes as one
container with everything inside it: Python, the animation renderer, Qoder CLI, Claude CLI, the voice
model and the music. Docker restarts it automatically, so it runs 24/7.

**One-time setup on Windows**

1. In Docker Desktop: **Settings → General → "Start Docker Desktop when you sign in"** (on).
2. In Windows: **Settings → System → Power → Screen and sleep → "When plugged in, put my device to
   sleep after: Never"**. A sleeping PC can't make videos.
3. Install **Git for Windows** (git-scm.com), then in PowerShell:
   ```powershell
   git clone https://github.com/thomasjoseph3/yt-exp.git thoma-studio
   cd thoma-studio
   copy .env.example .env
   notepad .env
   ```
4. Fill in `.env` (the keys in section 3 below). Docker needs two sign-in tokens, because you
   can't log in interactively inside a container:
   - `QODER_PERSONAL_ACCESS_TOKEN`: from qoder.com/account/integrations
   - `CLAUDE_CODE_OAUTH_TOKEN` (optional backup writer): run `claude setup-token` on any computer
     where Claude Code is installed, and paste the token it prints.
5. Put the YouTube OAuth file (section 3) at `secrets\youtube_client.json` inside the project folder.
6. Build and sign in to YouTube:
   ```powershell
   docker compose build
   docker compose run --rm --service-ports studio thoma auth-youtube
   ```
   It prints a link. Open it in your browser, sign in with the channel's Google account, and the
   terminal shows `signed in as: <channel name>`.
7. Check it, then start it for good:
   ```powershell
   docker compose run --rm studio thoma test-llm
   docker compose run --rm studio thoma make short
   docker compose up -d
   ```

**Everyday Docker commands**

```powershell
docker compose logs -f                          # watch what it's doing
docker compose run --rm studio thoma status     # queue and errors
docker compose restart                          # after editing config.yaml
docker compose up -d --build                    # after updating the code (git pull)
docker compose down                             # stop it
```

Your videos appear in the `out` folder, and the database and log in `data`, both right inside the
project folder on Windows. Keys and the YouTube sign-in stay on your machine; they're never put into
the image or pushed to GitHub.

The rest of this guide is the manual Linux setup. With Docker, you only need sections 1 and 3
(hardware and keys) and section 8 (day-to-day use).

---

## 2. Software to install

You only need a few things yourself. The setup script installs the rest.

1. **git**, to download the code:
   ```bash
   sudo apt update && sudo apt install -y git curl
   ```
2. **Node.js 20 or newer**, which Qoder CLI needs. The easiest route is nvm:
   ```bash
   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
   source ~/.bashrc && nvm install 20
   ```
3. **Qoder CLI**, the main script writer:
   ```bash
   npm i -g @qoder-ai/qodercli
   qodercli          # opens Qoder; type /login and sign in, then exit
   ```
4. **Claude Code** (optional, the backup script writer), if you want Claude to take over when
   Qoder runs out:
   ```bash
   curl -fsSL https://claude.ai/install.sh | bash
   claude            # sign in once with your Claude account, then exit
   ```

Python, ffmpeg, the headless Chromium browser, the voice model and the music are all handled by
`deploy/setup.sh` in step 4.

---

## 3. Accounts and keys to collect

Collect all of these before you start. Everything here is free unless noted.

### Required

| What | Why | Where to get it |
|---|---|---|
| **Qoder account** | Writes the scripts | qoder.com (your existing plan) |
| **Qoder personal access token** | Lets the 24/7 service use Qoder without you logged in | qoder.com/account/integrations |
| **Gemini API key** (one or two) | Thoma's voice | aistudio.google.com/apikey (free, no card) |
| **Google account that owns the YouTube channel** | Uploading | the channel itself |
| **Telegram bot token + your chat ID** | Approvals, video files, alerts on your phone | Telegram (see below) |

### Optional

| What | Why |
|---|---|
| Claude subscription | Backup script writer |
| Google Cloud Text-to-Speech key | Second voice option (needs a billing card; capped so it stays free) |
| YouTube Data API key | Pulls older videos from the source channels as extra topics |
| Meta (Facebook Page + Instagram professional account) | Fully automatic IG/FB posting instead of posting from Telegram yourself |

### How to get the Telegram bot and chat ID (2 minutes)

1. In Telegram, open **@BotFather**, send `/newbot`, and pick a name. It replies with a **token**
   like `123456:ABC-...`.
2. Open your new bot and send it any message, like "hi".
3. In a browser, open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`.
   Find `"chat":{"id": 123456789` and copy that number. That's your **chat ID**.

### How to set up YouTube uploading (about 15 minutes)

You never give the app your password or a channel ID. You sign in once and choose the channel.

1. Go to **console.cloud.google.com** and create a project (e.g. "Thoma Studio").
2. **APIs & Services → Library**: search for **YouTube Data API v3** and enable it.
3. **OAuth consent screen**: choose External, fill in the app name and your email, and add your Gmail under *Test users*.
   Then click **Publish app**, so your sign-in doesn't expire every 7 days.
4. **Credentials → Create credentials → OAuth client ID → Desktop app**: then **Download JSON**.
5. Keep that file handy; you'll place it in step 5.

Good to know: until Google reviews your project (the free "YouTube API audit" form), uploads made
through the API stay **private**. You'll get the link on Telegram and can make each one public in
the YouTube Studio app with two taps. Apply for the audit once the channel has a few videos.

---

## 4. Install the studio

```bash
git clone https://github.com/thomasjoseph3/yt-exp.git thoma-studio
cd thoma-studio
./deploy/setup.sh
```

The setup script:
- installs `uv` (the Python tool) and the exact Python packages,
- installs the headless Chromium browser that draws the animations (it asks for your password once
  for system libraries),
- downloads Thoma's backup voice model (~120 MB) and the background music,
- creates your `.env` file from the template,
- checks which script writers (Qoder, Claude) are reachable.

**Moving from another machine?** On the old machine run `./deploy/backup.sh` and copy the
`thoma-backup-<date>.tar.gz` file over. Then run `./deploy/setup.sh thoma-backup-<date>.tar.gz`
here instead. That restores your keys, the YouTube sign-in and the history of which topics were
already made, so nothing gets repeated. **Stop the old machine first**
(`systemctl --user disable --now thoma-studio`) so the two never post the same video.

---

## 5. Add your keys

Open `.env` in any editor (`nano .env`) and fill in what you collected:

```bash
QODER_PERSONAL_ACCESS_TOKEN=...
GEMINI_API_KEY=...
GEMINI_API_KEY_2=...          # optional backup key
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Then the YouTube sign-in:

```bash
mkdir -p ~/.config/thoma-studio
mv ~/Downloads/client_secret_*.json ~/.config/thoma-studio/youtube_client.json
uv run thoma auth-youtube
```

A browser opens. Sign in with the Google account that owns the channel. If it has several channels,
pick Thoma's. Google will say "this app isn't verified"; click **Continue**, since it's your own app.
The terminal then prints `signed in as: <channel name>`. Check that it's the right one.

The `.env` file and the YouTube sign-in stay on this machine only. They're excluded from git, so
they never end up on GitHub.

---

## 6. Check that everything works

Run these one by one. Each takes seconds to a few minutes.

```bash
uv run thoma test-llm        # Qoder and/or Claude should say OK
uv run thoma voices          # makes voice samples in out/voices/ — listen to them
uv run thoma preview assets/samples/short_rag.json short   # still frames in out/preview/
uv run thoma ideas           # pulls topics from IBM Technology, ByteMonk and Fireship
uv run thoma make short      # a complete Short, about 3–4 minutes
```

If you set up Telegram, the finished Short arrives on your phone with **/approve** and **/reject**
instructions. Approve it and it goes out at the next posting slot.

---

## 7. Start it for real (24/7)

```bash
./deploy/install-service.sh
```

The studio now runs in the background, restarts itself if it crashes, and keeps running after you
log out. Every 15 minutes it checks for new topics, makes videos when they're due, and posts
uploads approved ones with their release time (by default 2 Shorts and 1 long video a day).

Useful commands:

```bash
journalctl --user -u thoma-studio -f       # watch what it's doing
uv run thoma status                        # what's queued, made, failed
systemctl --user restart thoma-studio      # after changing config.yaml
systemctl --user stop thoma-studio         # stop it
```

---

## 7b. Running it only at night (laptop "night shift")

You don't need the computer on all day. The studio **makes videos ahead and uploads them with a
release time**, and YouTube publishes each one at its slot by itself, even if your laptop is off by then.

How a typical day looks with the default times:
- **21:00**: you plug in the laptop and leave it on. The service starts by itself.
- **Overnight**: it makes tomorrow's long video and Shorts (about 1 hour of work), sends each one
  to Telegram, and uploads it to YouTube with its release time.
- **Morning**: you check Telegram, `/approve` or `/reject`, and switch the laptop off whenever you like.
- **06:30 / 07:30 / 19:30**: YouTube releases them. You post the Reels from Telegram at those times.

It plans 36 hours ahead (`plan_ahead_hours`), so missing a night is fine; the next night catches up.

**In approve mode, approvals happen at night too:** if you approve in the morning while the laptop
is off, the video is uploaded the next time the laptop is on and takes the next free slot. To
review in the morning and still have it go out the same day, either keep the laptop on until you've
approved, or switch to `mode: auto` once you trust the videos. Then everything is scheduled overnight
and you only cancel the rare bad one in the YouTube Studio app.

**Make the laptop behave (Ubuntu), once:**
1. **Settings → Power**: set "Automatic Suspend" to **Off** when plugged in.
2. Keep it running with the lid closed:
   ```bash
   sudo sed -i 's/^#\?HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf
   sudo systemctl restart systemd-logind
   ```
3. The service from step 7 starts on boot by itself; there's nothing to launch.

**Until Google approves your API audit**, YouTube keeps API uploads private and ignores the release
time. The Telegram message tells you the slot. Open the YouTube Studio app, then the video,
**Visibility → Schedule**, and pick that time. Once the audit is approved, set `youtube_audited: true`
in `config.yaml` and this step disappears.

---

## 8. Day-to-day use

Most days you only touch your phone:

- **New video on Telegram**: watch it, reply `/approve 12` or `/reject 12`. A rejected video that was
  already scheduled is pulled back to private.
- **After it's on YouTube**: the bot replies with the caption for Instagram/Facebook. Save the video
  from Telegram and post it from the app with that caption.
- **Want a specific topic?** Send `/topic What is Docker?` and it's next in line.
- **Going on holiday?** `/pause`, then `/resume` later. `/status` shows what's going on.

To change how it works (posting times, how many Shorts, the voice, Thoma's personality), edit
`config.yaml`, or open the folder in Qoder and just ask. Qoder reads `AGENTS.md` and knows the project.

---

## 9. When something goes wrong

| What you see | What to do |
|---|---|
| `test-llm` says Qoder FAIL | Run `qodercli` and `/login` again, or check `QODER_PERSONAL_ACCESS_TOKEN` in `.env` |
| `test-llm` says claude FAIL | Run `claude` once to sign in, or your Claude limit is used up for now (it retries later) |
| Videos stop being made | `uv run thoma status` and the end of `data/studio.log` show why. If both writers are out, it simply waits |
| Voice sounds robotic | Gemini hit its free limit and the local voice took over. It returns to Gemini by itself. A second key from another Google project adds headroom |
| YouTube upload fails with an auth error | Run `uv run thoma auth-youtube` again |
| Uploads are private | Expected until Google's API audit is approved; make them public in YouTube Studio |
| Telegram says "file too big" | Shouldn't happen (big files are shrunk automatically); check `data/studio.log` |
| Disk filling up | Lower `keep_long_days` under `storage:` in `config.yaml` |
| Animations look broken | Run `uv run playwright install --with-deps chromium-headless-shell` again |

If you're stuck, open the project in Qoder or Claude Code and paste the error. `AGENTS.md` gives
them everything they need to help.
