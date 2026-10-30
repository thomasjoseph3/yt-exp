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
- Voice: Gemini TTS via AI Studio keys (GEMINI_API_KEY + GEMINI_API_KEY_2), one continuous take, faster-whisper word alignment, target 150 wpm (owner: 165 was too fast). Fallbacks: Chirp HD (capped below free tier), local Kokoro. Free tier is ~10 requests/day per model per key, so it rotates models/keys.
- IG/FB are manual: Telegram sends the original-quality file + caption. Telegram bot @mallu_monksbot is connected (token + chat ID in .env).
- Schedule (owner agreed 2026-10-27, to avoid looking mass-produced): 3 long a week Tue/Thu/Sat at 06:30 IST (add a 4th day once quality holds) + Shorts daily (now 1 a day, see evening update); laptop runs at night; Shorts up to 3 min (usually 60-90 s); long videos kept 14 days; Shorts deleted after publishing.
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
- SUPERSEDED 2026-10-30: every video is 5 minutes at most (long: 560-700 words, render.py refuses over 5:00). Was: long videos 8-10 min. 5+ chapters, re-hooks.
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
- 2026-10-27: Shorts may run up to 3 min (usually 60-90 s, length follows the topic); research reads the
  3 most-watched YouTube explainers on the topic (ideas.top_explainers) for teaching structure, and the copy
  gate covers their transcripts. Word alignment no longer uses Whisper's initial_prompt (it skipped
  whole stretches and captions drifted by seconds).
- Quality loop (owner, 2026-10-27): Qoder writes, Claude checks (config llm.roles); reviews logged
  (`thoma lessons`); approved scripts become examples (assets/examples); owner verdicts/fix notes feed every
  brief. Claude Opus wrote the RAG-vs-OKF gold series (ideas 229-233 + 185). After the owner reviews it,
  switch back to Qoder and use `thoma lessons` to tighten prompts/gates until Qoder matches it.

Update 2026-10-27 evening:
- Gold series done: Shorts #13-17 + long #18 (Opus, 9:58). Qoder tests: #19 tokens (good), #20 NotebookLM
  (filler about what the site doesn't say; owner should reject), #21 NotebookLM remake (good). All ready on
  Telegram, none approved yet. #12 has the old audio mix: reject.
- Qoder now writes, Claude Sonnet reviews (llm.roles; review falls back to Qoder if Claude is out).
- Schedule changed: 1 Short a day (19:30) + 3 long a week (Tue/Thu/Sat 06:30) = 10 videos/week;
  plan_ahead_hours 168 so one night of the daemon makes the whole week. `/plan` (Telegram) or
  `thoma plan` shows the calendar. Add "07:30" back for 2 Shorts/day once Qoder is reliably good.
- Moving to the owner's personal system: deploy/backup.sh now also packs unpublished videos (out/);
  setup.sh restores them; pipeline.video_file() finds a video by folder name when the DB came from another
  machine. Run the studio on ONE machine only (shared Telegram bot).
- Pending owner answers: Malayalam dub of long videos for @mallumonks (own voice recorded per scene, or AI
  voice?) -> then build a `dub` step (per-scene Malayalam voice, re-timed render, Malayalam title/thumbnail,
  second YouTube sign-in). Voice clone: NVIDIA GPU? + 1-2 min sample.

User goal: 10k subscribers in 3 months and real second income; see [[thoma-owner-profile]]. Related: [[use-own-judgment]], [[natural-voice-required]], [[background-long-jobs]].

Update 2026-10-29 ("how it works" lane, owner request):
- Owner wants videos on how real things work under the hood (self-driving cars, Tesla's flying Roadster...),
  researched on the open web, not only the 3 source channels (those stay for AI/tech tutorials). Strong hooks,
  more professional motion graphics, 10th-standard language, 10 long videos + 10 Shorts linked to them.
- Topics: assets/how_it_works.txt (picked from YouTube demand; first line made first). Ideas source
  'how-it-works', priority 8. research() for them = Wikipedia + Bing News articles (ideas.web_research) + the
  top 3 explainers' transcripts.
- Hooks: research reads the first minute (with timestamps) of the most-watched videos and writes a "hook
  blueprint" (beats, order, timing, job of each beat); the writer must open with those beats in its own words.
  Owner said "do exactly like it": we copy the hook's STRUCTURE and timing, never its words (copy gate stays).
- Formats: writer.HOW_LONG (long, now 4-5 min, Thoma introduces himself only after the hook's promise; gate) and
  SHORT_FORMATS["teaser"] (the Short explains one surprising part and sends viewers to the full video).
  A teaser's script has "related": {video, title}; schedule() puts it after its long video's slot, and the
  upload pack tells the owner to set YouTube Studio -> Short -> Related video (the API can't set it).
- New visuals (stage.js B.parts/scan/zoom/layers/path/timeline/bars + visuals.SPEC); gates require >=6 of them in
  a long how-it-works video, >=1 in its Short. Film grain + vignette, chapter cards on long videos.
- Pipeline: write_video() -> status 'scripted' -> render_video(). `thoma series --n 10 [--no-render]` writes
  the long + teaser per topic, then renders what the voice quota allows; `thoma render` / the daemon's tick
  render the rest later. voice.local_fallback=false: when Gemini TTS quota is out, videos wait (no Kokoro voice).
- Writers: see [[writers-no-opus]].
- 2026-10-29 the old AI videos' files (#13-#21 in out/) were deleted by hand to free disk (DB still says ready).
  Disk is ~3.8 GB free; a long video is ~100 MB.
- 2026-10-29 hooks: research studies the opening minute of the top 5 videos on the topic (full transcripts of the top 3) and writes a hook blueprint. Scripts follow it with the playbook: start mid-moment (scene 1 at most 14 words), the viewer's question, a twist, the promise, all under 30 s. A gate blocks "in this video" / "today we'll" in the first 3 scenes.

Update 2026-10-30 (owner: more videos, proper tech topics, controversy researched into 10-min videos, real images
too, own voice offered; reference: Fireship "Did the AI bubble just pop?"):
- New lane "the big tech debates": assets/debates.txt (14 topics, AI bubble first) + tech news feeds triaged for
  live debates (sources.news_feeds; source 'debate-news', dropped after news_days). writer.DEBATE_LONG: hook ->
  what happened -> the tech underneath -> case for -> case against -> numbers -> what it means for you -> Thoma's
  verdict + comment question. Research: ideas.debate_research (Wikipedia + news from several outlets incl. critics
  and defenders); the articles become a "Sources:" list in the description. Short: SHORT_FORMATS['debate-teaser'].
  Long videos rotate lanes: sources.long_rotation [debate, how, explain]. Owner's own yes/no question topics are
  treated as debates.
- Real photos: visuals photo / photos / headlines / quote (stage.js + visuals.SPEC). thoma/images.py: Wikimedia
  Commons (+ Pexels with PEXELS_API_KEY, Openverse), license filter (images.licenses incl. CC BY-SA), no AI-made
  images, Gemini vision check, cached in out/<id>/img, credits in the description. A photo scene with nothing
  usable becomes bigtext. Gates: long debate/how >= 3 photos, debate needs headlines + compare, photos <= 40% of
  visuals, quotes must be word for word in the research notes. The thumbnail uses the first real photo.
- Owner's voice: voice.record (default [] = off; recommended [long]). Script -> Telegram reading sheet -> owner
  replies with a voice note -> cleaned, pauses shortened, fluffed lines said twice cut (voice.cut_retakes,
  tested on a simulated retake), aligned -> rendered. /ai ID uses the AI voice, /record ID asks again; after
  record_wait_hours the AI voice reads it. A /fix that changes lines asks for a new recording. Description says
  "voiced by the channel's host" instead of "AI voice".
- First debate video (#? "Is the AI bubble about to pop?", idea 257) made 2026-10-30 as the test of the lane.
- 2026-10-30 owner: "keep every video for 5 minutes maximum". Long formats now 560-700 words (~3:45-4:40), 4-6 chapters, re-hook every 45-60 s; render.py limit 5:00; pipeline.rewrite_to_length() rewrites older over-long scripts before rendering. Trade-off told to owner: no mid-roll ads under 8:00.
