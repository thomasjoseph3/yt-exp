---
name: thoma-channel-project
description: "\"Thoma Explains\" automated YouTube/IG/FB studio in \"ollama yt/erp crm\" (repo github.com/thomasjoseph3/yt-exp): architecture, owner decisions, current state and open tasks"
metadata:
  node_type: memory
  type: project
  originSessionId: 9bbeade5-5cd3-4463-92ef-be1207f2f7f5
  modified: 2026-10-26T12:40:06.600Z
---

Started 2026-10-26. Python studio (`thoma/`, CLI `uv run thoma ...`), docs in README.md, SETUP_GUIDE.md, STRATEGY.md, AGENTS.md (+ .qoder/rules for Qoder).

Pipeline: ideas (IBM Technology, ByteMonk, Fireship YouTube feeds + Product Hunt AI feed + assets/evergreen_topics.txt + assets/ai_tools.txt) → research (transcript or tool website) → script by Qoder CLI, Claude as backup → code gates + LLM review → voice → GSAP/HTML scenes rendered frame by frame in headless Chromium → ffmpeg → Telegram approval → YouTube upload with publishAt (night-shift scheduling).

Owner decisions (don't reverse without asking):
- Only Qoder or Claude write content. No Ollama/Gemini/Groq for scripts. User uses Qoder (qoder.com), not Qodo.
- Thoma is a small original purple imp mascot (amber horns, tail, glasses, cyan stylus, rides a glowing spear) in the bottom-right corner, inspired by Balarama's Luttappi but not a copy. User rejected the earlier big teacher presenter and the chalkboard look.
- Visual style: ByteMonk-like animated diagrams, Fireship pace.
- Voice: Gemini TTS via AI Studio keys (GEMINI_API_KEY + GEMINI_API_KEY_2), one continuous take, faster-whisper word alignment, target 165 wpm. Fallbacks: Chirp HD (capped below free tier), local Kokoro. Free tier is ~10 requests/day per model per key, so it rotates models/keys.
- IG/FB are manual: Telegram sends the original-quality file + caption. Telegram bot @mallu_monksbot is connected (token + chat ID in .env).
- Schedule (owner agreed 2026-10-27, to avoid looking mass-produced): 3 long a week Tue/Thu/Sat at 06:30 IST (add a 4th day once quality holds) + 2 Shorts daily (07:30, 19:30); laptop runs at night; Shorts ≤59 s; long videos kept 14 days; Shorts deleted after publishing.
- AI-tool videos lane (~35% Shorts, 25% long) with affiliate links from config `ai_tools.affiliates`.
- Runs on Linux laptop (SSD nearly full, ~7 GB free) or Windows PC via Docker Desktop (Dockerfile + docker-compose.yml, image built and tested 2026-10-26).

State at 2026-10-26 end of session:
- Working and tested: Qoder + Claude writers, Gemini voice, Telegram, Docker render, AI-tools lane, scheduler dry-run.
- NOT done: YouTube OAuth sign-in (user must do Google Cloud steps), install-service, YouTube API audit request, Meta API.
- Ideas offered but not built: niche weighting toward high-RPM sub-niches (AI tools, money-tech, security, cloud) and an 8-minute deep-dive long format for mid-roll ads.

Update 2026-10-27 (owner asked for ByteMonk-like richer animation, more natural voice, concept/debate topics):
- New concept visuals in stage.js + visuals.SPEC: tokens, predict (next-word bars), vectors (embedding map),
  network (neural net with flowing signal), chat (with "MADE UP!" hallucination stamp). Sample:
  assets/samples/short_llm_think.json.
- character.md has a "mission" section (10k subs in 3 months, revenue, hooks/open loops/comments, no bait).
- New Short format "debate": chosen automatically when the topic is a yes/no question ("Does/Is/Will/Can ...").
- gemini_style rewritten toward a calm, confident engineer-explainer delivery (still brisk, 165 wpm).
- 10 new debate/concept topics appended to assets/evergreen_topics.txt (newest are picked first).
- Pending fixes from 2026-10-26 (175-word Short limit, "take a different angle" brief) are already in writer.py.
- Owner asked (2026-10-27) for Thoma to ride a spear like Luttappi: he now sits on a glowing amber/cyan
  single-point tech spear (deliberately not a trident, to stay original), flies in at the start, swoops at cuts.
- Retention editing: cuts rotate slide/zoom-punch/whip/pop, light flash on some cuts, punch-in + shake on
  "wow" moods, bouncier captions.
- Long videos are now 8-9 min (1340-1600 words) so mid-roll ads are possible; 5+ chapters, re-hooks.
- Scripts include pinned_comment; Telegram gets an "UPLOAD PACK" (title, description, tags, thumbnail,
  pinned comment) for manual upload; config channel.youtube_handle adds a subscribe link once set.
- A video never mixes voice engines (narrate() pins the first chunk's engine).
- Owner is setting up their personal laptop (2026-10-27) and will do the YouTube OAuth there.
- Owner feedback loop: Telegram `/fix <id> <what to change>` -> writer.revise() changes only those scenes,
  voice takes are cached per chunk (out/<id>/takes) so only changed chunks are re-voiced; works for
  ready/approved/failed/rejected videos. Visual looks rotate per video (render.THEMES: midnight, ocean,
  ember, matrix); Thoma and branding never change.
- Source channels: feeds sometimes 404; ideas._rss falls back to reading the channel's videos + Shorts pages.
  Transcripts are fetched when an idea is used (writer.research), turned into neutral notes.

User goal: 10k subscribers in 3 months and real second income; see [[thoma-owner-profile]]. Related: [[use-own-judgment]], [[natural-voice-required]], [[background-long-jobs]].
