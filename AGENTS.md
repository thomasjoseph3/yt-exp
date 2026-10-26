# Thoma Studio — guide for coding agents (Qoder, Claude Code, any other)

An automated channel, **Thoma Explains**: Thoma, a small comic tech imp in the corner of the screen,
explains AI and tech to beginners over ByteMonk/Fireship-style animations. Strategy: STRATEGY.md. The studio makes a ~5-minute 16:9 tutorial every day (YouTube + Facebook) and 2 Shorts
a day (YouTube Shorts + Instagram Reels + Facebook Reels), and runs 24/7 as one Python process.

## How it works (one line per step)
1. `ideas.py` reads the YouTube feeds of IBM Technology, ByteMonk and Fireship (config.yaml → sources)
   and Product Hunt's AI feed; an LLM keeps what can become one beginner video. Backlogs:
   `assets/evergreen_topics.txt` (concepts) and `assets/ai_tools.txt` (well-known AI tools).
   `ai_tools.share` sets how many videos are about AI tools (facts come from the tool's own website).
2. `writer.py` fetches the source transcript, turns it into neutral research notes, writes Thoma's
   script (scenes = narration + a visual), runs code gates, then an LLM review. Failures loop back.
3. `voice.py` speaks it (Google Chirp 3 HD, local Kokoro as backup) and adds synthesized SFX; render.py
   masters the voice and ducks the music (assets/music, CC BY, credited in descriptions).
4. `render.py` loads `assets/web/stage.html` in headless Chromium, seeks the GSAP timeline to every
   frame, screenshots it and pipes frames to ffmpeg. Thoma the imp is SVG, drawn by `assets/web/mascot.js`.
5. `pipeline.py` sends it to the owner on Telegram, and once approved (or right away in `mode: auto`)
   uploads it with the next free slot as its release time (YouTube `publishAt`), so the machine only
   needs to be on before the slot, e.g. overnight. Plans `plan_ahead_hours` ahead.
6. `cli.py daemon` runs `pipeline.tick()` every 15 minutes, forever.

## Map
```
config.yaml              all settings: LLM provider chain, sources, schedule, platforms, voice
.env                     secrets (never commit, never print). Template: .env.example
thoma/character.md       Thoma's bible; sent with every writing prompt
thoma/llm.py             ask_json(): tries providers in order, benches failing ones for 60 min
thoma/ideas.py           feeds -> ideas table; transcript()
thoma/writer.py          research -> script -> gates -> review
thoma/visuals.py         visual types the LLM may use (SPEC), icon names, narration-synced reveal times
thoma/voice.py           TTS, word timings, SFX
thoma/render.py          prepare() / preview() / render() / thumbnail()
thoma/pipeline.py        make(), slots(), schedule(), publish_due(), tick(): the scheduler
thoma/publish/           youtube.py (OAuth, resumable upload, thumbnail, captions), meta.py (FB + IG)
thoma/notify.py          Telegram messages, preview videos, /approve /reject /pause /resume /status
assets/web/              stage.html/css/js (scene builders), mascot.js (Thoma: moods talk/point/think/wow/laugh/wave),
                         thumb.html, vendor (GSAP, highlight.js, Lucide icons)
assets/music/            background tracks (downloaded by deploy/setup.sh)
assets/samples/          hand-written scripts for testing the renderer without an LLM
data/studio.db           SQLite: ideas, videos, uploads, kv. data/studio.log is the log
out/<id>-<kind>/         per video: script.json, voice.wav, captions.srt, timeline.json, mp4, thumbnail.jpg
```

## Commands (`uv run thoma <cmd>`)
| Command | What it does |
|---|---|
| `status` | queue, ideas left, which LLM providers are cooling down |
| `test-llm` | checks every provider in config.yaml |
| `ideas [--backfill N]` | pull new topics (backfill needs YOUTUBE_API_KEY) |
| `topic "What is Docker?"` | owner's topic request; used for the next video |
| (config) `ai_tools.affiliates` | owner's affiliate links; added to descriptions of videos that mention the tool, with a disclosure |
| `make short\|long [--idea ID] [--script file.json]` | write + render one video now |
| `preview <script.json> short\|long [--at 2,10]` | still PNGs in out/preview/ — use this to check visual changes, it takes seconds |
| `approve ID` / `reject ID` / `publish ID` | owner actions |
| `tick` / `daemon` | one scheduler pass / run forever |
| `voices` | the same line in each candidate voice (out/voices/), to pick `voice.google_voice` |
| `auth-youtube` | one-time YouTube sign-in |

## Rules
- **Nothing goes public without the owner's approval** while `publish.mode` is `approve`. Don't switch to `auto` unless the owner says so.
- **Growth and monetization rules are in STRATEGY.md**: quality over quantity (YouTube's inauthentic-content policy), varied formats, owner in the loop.
- **Never copy source channels.** They are topic and fact sources only. Keep the 7-gram copy gate in `writer.gates()`; never reuse their visuals, audio or code.
- **Thoma's look and voice are fixed.** Don't change `mascot.js` shapes/colours or the chosen voice unless the owner asks; consistency is the brand. He is an original design: never make him resemble an existing comic character.
- **Checks live in code** (`writer.gates`). If the owner changes a rule about scripts, change the gate and the prompt together.
- **Only Qoder or Claude write content** (owner's rule). Every model call goes through `llm.ask_json()`; don't add other LLM providers (Gemini is used only for the voice).
- Secrets stay in `.env` and `~/.config/thoma-studio/`. Never log or print them.
- After editing anything visual, run `uv run thoma preview assets/samples/short_rag.json short` (and `long`) and look at the PNGs before saying it works.
- Shorts must stay under 60 s (render.py speeds the voice up a little, then refuses).

## Adding a new visual type (the most common job)
1. `assets/web/stage.js`: add `B.mytype = (scene, v, box, R, start, end, portrait) => { ... }`.
   `R[i]` is the time element i should appear; add tweens with `tl.fromTo(..., R[i])`; for continuous motion push a function onto `tickers`.
2. `thoma/visuals.py`: describe it in `SPEC` (so the LLM can use it) and list its elements in `elements()` in the same order as `R`.
3. `thoma/writer.py`: add the type name to `TYPES`.
4. Add a scene using it to a sample script and run `preview`.

## Running the channel day to day (what an agent on duty does)
1. `uv run thoma status` — anything `failed`? Read the error in `data/studio.log` and fix the cause.
2. Videos `ready` wait for the owner. Owner approves on Telegram (`/approve 12`) or `uv run thoma approve 12`.
3. Upload rows with status `failed` are retried automatically each tick; persistent ones usually mean an expired token (YouTube: re-run `auth-youtube`; Meta: refresh META_PAGE_TOKEN).
4. If all LLM providers are cooling down, the studio simply waits; check `test-llm`.
