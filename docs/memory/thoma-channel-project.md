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
- Thoma is a small original purple imp mascot (amber horns, tail, glasses, cyan stylus) in the bottom-right corner, inspired by Balarama's Luttappi but not a copy. User rejected the earlier big teacher presenter and the chalkboard look.
- Visual style: ByteMonk-like animated diagrams, Fireship pace.
- Voice: Gemini TTS via AI Studio keys (GEMINI_API_KEY + GEMINI_API_KEY_2), one continuous take, faster-whisper word alignment, target 165 wpm. Fallbacks: Chirp HD (capped below free tier), local Kokoro. Free tier is ~10 requests/day per model per key, so it rotates models/keys.
- IG/FB are manual: Telegram sends the original-quality file + caption. Telegram bot @mallu_monksbot is connected (token + chat ID in .env).
- Schedule: 1 long (06:30 IST, US prime time) + 2 Shorts (07:30, 19:30) daily; laptop runs at night; Shorts ≤59 s; long videos kept 14 days; Shorts deleted after publishing.
- AI-tool videos lane (~35% Shorts, 25% long) with affiliate links from config `ai_tools.affiliates`.
- Runs on Linux laptop (SSD nearly full, ~7 GB free) or Windows PC via Docker Desktop (Dockerfile + docker-compose.yml, image built and tested 2026-10-26).

State at 2026-10-26 end of session:
- Working and tested: Qoder + Claude writers, Gemini voice, Telegram, Docker render, AI-tools lane, scheduler dry-run.
- NOT done: YouTube OAuth sign-in (user must do Google Cloud steps), install-service, YouTube API audit request, Meta API.
- Pending fixes the user interrupted before they were applied: raise Short word limit 165→175 in writer.FORMATS; add "topic already has video '<title>', take a different angle" to the writer brief. The new natural-voice Short has not yet been produced end to end or sent to Telegram.
- Ideas offered but not built: niche weighting toward high-RPM sub-niches (AI tools, money-tech, security, cloud) and an 8-minute deep-dive long format for mid-roll ads.

User goal: 10k subscribers in 3 months and real second income; see [[thoma-owner-profile]]. Related: [[use-own-judgment]], [[natural-voice-required]], [[background-long-jobs]].
