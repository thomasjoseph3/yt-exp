# Thoma Studio — guide for coding agents (Qoder, Claude Code, any other)

An automated channel, **Thoma Explains**: Thoma, a small comic tech imp in the corner of the screen,
explains AI and tech to beginners over ByteMonk/Fireship-style animations. Strategy: STRATEGY.md. The studio makes a ~5-minute 16:9 tutorial every day (YouTube + Facebook) and 2 Shorts
a day (YouTube Shorts + Instagram Reels + Facebook Reels), and runs 24/7 as one Python process.

**Read `docs/memory/` first**: the owner's decisions, what's done and what's pending. Update it when a decision changes.

## How it works (one line per step)
1. `ideas.py` reads the YouTube feeds of IBM Technology, ByteMonk and Fireship (config.yaml → sources)
   and Product Hunt's AI feed; an LLM keeps what can become one beginner video. Backlogs:
   `assets/evergreen_topics.txt` (concepts) and `assets/ai_tools.txt` (well-known AI tools).
   `ai_tools.share` sets how many videos are about AI tools (facts come from the tool's own website).
2. `writer.py` fetches the source transcript, turns it into neutral research notes, writes Thoma's
   script (scenes = narration + a visual), runs code gates, then an LLM review. Failures loop back.
3. `voice.py` voices the whole script as one continuous take (Gemini TTS; each model/key has ~10 free
   requests a day, so it rotates models and keys; Chirp and local Kokoro are backups), speeds slow takes up
   to `target_wpm`, then finds every word's timing with a local faster-whisper aligner so visuals and
   captions land on the right word. render.py masters the voice and ducks the music.
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
thoma/notify.py          Telegram messages, preview videos, /approve /reject /fix /publish /short /long /topic /pause /resume /status /plan
assets/web/              stage.html/css/js (scene builders incl. AI concept visuals: tokens, predict, vectors, network, chat), mascot.js (Thoma: moods talk/point/think/wow/laugh/wave),
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
| `plan` | the coming week, slot by slot: which video goes out when, and what is still missing |
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
- Shorts run 60-120 s (up to 178 s if the topic truly needs it; render.py refuses longer).

## Quality loop: Qoder writes, Claude checks (owner's decision, 2026-10-27)
- `config.yaml` → `llm.roles`: Qoder researches and writes, Claude reviews every script (the "student test" plus
  accuracy). Claude's notes go back to Qoder for the rewrite.
- Every review is logged. `uv run thoma lessons` shows each writer's first-check pass rate and the recent catches.
  The last few catches are also put into every new brief automatically.
- Scripts the owner approves are saved to `assets/examples/<kind>/` and shown to the writer as the standard to match.
  The RAG vs OKF series was written by Claude Opus (`make ... --llm claude-opus`) to set that bar.
- Owner verdicts and `/fix` notes go into every brief (`writer.owner_feedback`).
- Popular explainers are used for STRUCTURE only: `research()` turns the most-watched ones into a beat sheet
  plus fresh examples of our own. Never their words or examples (owner asked to reword top transcripts; declined,
  YouTube's reused-content rule blocks monetization).
- Code gates for the catches that kept coming back: jargon and acronyms must be listed in `terms` and explained
  where first said (`_term_problems`); diagram/vector labels must be spoken (`_label_problems`).
- **When the same catch keeps coming back, fix it at the source**: tighten `thoma/character.md`, the format spec
  in `writer.FORMATS`/`SHORT_FORMATS`, or add a code gate in `writer.gates`/`writer.repair`. Then check that
  `thoma lessons` improves over the next videos.

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
