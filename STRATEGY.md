# Thoma Explains: growth and income plan

**Goal: reach YouTube monetization within 3 months — before the bar rises on 1 Feb 2027.** This plan is
honest about what that takes, and is now grounded in our first real numbers.

## Where we are now (7 Nov 2026)
First 5 videos are live. Channel: **5 subscribers, 241 total views.** Early, but there is already signal:

| Views | Length | Title | Type |
|--:|--|--|--|
| **112** | 1:38 | How do self-driving cars see? | Short |
| 54 | 1:36 | AI hallucinations: why better data can't fix them | Short |
| 38 | 1:44 | NotebookLM: one file into four shapes | Short |
| 19 | 4:26 | Is the AI bubble about to pop? | Long |
| 18 | 9:59 | RAG vs OKF: how AI agents get their knowledge | Long |

**What the data says (n=5, so leads not laws):**
1. **Shorts out-reach long videos ~5×.** With a tiny subscriber base, the Shorts feed is our only real
   distribution. Shorts are the growth engine; long videos are the watch-hour/retention play for later.
2. **The real-world "how does it physically work" angle won by 2×** (self-driving cars). This validates
   the niche broadening to cars/drones/robots + the AI inside. It is now our lead content type (the idea
   triage flags `realworld` topics and ranks them highest; `visuals.py` uses more real photos on them).
3. **Engagement is near-zero (1 comment).** Normal at launch — we need volume and a reason to comment.

**The hard truth about the 3-month target.** Full ad monetization (1,000 subs + 4,000 watch-hours OR
10M Shorts views in 90 days) from 5 subs in <3 months is a long shot — most channels take 6–18 months.
The *achievable* milestone before 1 Feb 2027 is the **early / fan-funding tier (500 subs + 3,000
watch-hours or 3M Shorts views)**, with a real shot at full monetization only if one or two Shorts break
out. So: optimise relentlessly for Shorts reach now, and bank watch-hours with bingeable long videos.

## The rules of the game (researched October 2026)

**Monetization (YouTube Partner Program)**
- **Ad revenue tier:** 1,000 subscribers **and** either 4,000 public watch hours in 12 months, or
  10 million Shorts views in 90 days. You get 55% of ad revenue on long videos and 45% on Shorts.
- **Early tier (no ad revenue):** 500 subscribers, 3 uploads in 90 days, and 3,000 watch hours or
  3M Shorts views. This unlocks memberships, Super Thanks and shopping.
- ⚠️ **Deadline: from 1 February 2027 the bar doubles** to 8,000 watch hours or 20M Shorts views.
  Applying before then is worth a lot, so the first 3 months matter.
- **Watch hours from Shorts don't count** toward the 4,000. Those hours come from **long videos**.

**What it pays.** Tech and education are among the better-paying topics, but where viewers live matters:
- Indian viewers on long videos: roughly ₹80–120 per 1,000 views (estimates).
- US, UK and Canadian viewers pay several times more.
- Shorts pay very little everywhere: about ₹0.1–1 per 1,000 views in India.
- **Shorts bring subscribers; long videos bring money.**

**The biggest risk: YouTube's "inauthentic content" rule** (since July 2025). YouTube removes
monetization from, and has terminated, faceless channels that look mass-produced:
- synthetic voice over generic visuals
- the same template every time
- very high upload frequency
- little real insight

In January 2026 it terminated channels with 35M subscribers combined. Our channel has an AI voice
and automation, so **we must look and feel like a real, caring creator**. That shapes everything below.

## Honest expectations (milestones to monetization)

The target is **monetization eligibility before 1 Feb 2027**, not a vanity subscriber count. Most new
channels take far longer, so this is a stretch that depends on at least one Short breaking out. Plan:

| By the end of | Target | What it unlocks |
|---|---|---|
| Month 1 (early Dec) | 150–500 subs; learn which Shorts hooks land | Direction |
| Month 2 (early Jan) | 500 subs + 3 uploads + 3,000 watch-hrs **or** 3M Shorts views | **Early / fan-funding tier** |
| Month 3 (by 31 Jan) | push for 1,000 subs + 4,000 watch-hrs / 10M Shorts views | **Full ad monetization** |

If only the early tier is reached by 31 Jan, that still beats the Feb-1 threshold hike and unlocks
memberships + Super Thanks. Full ads can follow right after. Track the real numbers with
`uv run thoma analytics` every week and let them overrule this table.

Money in months 1–3 will be small (a few thousand rupees at most). Real income starts after
monetization and grows with the back catalogue, because good explainers keep getting found for years.

## How we beat the "inauthentic" risk (non-negotiable)
1. **You stay in the loop.** Review every video on Telegram (`mode: approve`) for at least the
   first month. Reject anything wrong or bland. The studio already fact-checks with a second AI pass.
2. **A real character with a point of view.** Thoma has a personality, jokes, opinions and a
   catchphrase. Original animated visuals, not stock footage.
3. **Variety, not a template.** Rotating Short formats (explainer, myth vs fact, "can you guess",
   fresh news), different hooks every time (checked automatically), and different visuals per topic.
4. **Quality over quantity.** 3 long videos a week (Tue/Thu/Sat, a 4th once quality holds) + 2 Shorts a day. If any video is weak, skip
   the slot rather than post filler.
5. **Be a creator, not a machine.** Reply to comments yourself (5 minutes a day), pin a helpful
   comment on each video, and post a Community post once a week ("what should Thoma explain next?").
6. **Disclose AI properly.** The studio sets YouTube's "altered or synthetic content" flag and adds
   a disclosure line to every description.

## The growth engine
- **Lead with real-world "how does it actually work".** Our best video by far. Cars, self-driving, EVs,
  drones, robots, rockets, cameras, wearables — and the AI inside them. These make strong Shorts hooks
  ("How does a self-driving car *see*?") and they use real photos for the hook, diagrams for the
  mechanism. The triage now ranks these topics highest; the backlog (`assets/evergreen_topics.txt`) is
  stocked with them. Aim for roughly half of Shorts in this lane.
- **Two supporting topic lanes.**
  - *Fresh:* when IBM Technology, Fireship or ByteMonk cover something new, Thoma explains the
    underlying concept within a day, while people are searching for it.
  - *Evergreen:* "What is an API / Docker / RAG" topics that get searched for years and build watch hours.
- **Shorts → long funnel.** Each day's Shorts are on the same topic as that day's long video. In
  YouTube Studio, set each Short's **"Related video"** to the long one. This is the single best
  subscriber converter.
- **Playlists as courses.** "AI from zero", "How the internet works", "Security basics". Binge-watching
  is what builds 4,000 hours.
- **Packaging.** Thumbnails get 2–5 huge words, one highlighted, plus Thoma's surprised face. Titles
  put the search words first. If a video's click-through rate is under 4% after 48 hours, change the
  thumbnail and title (that's allowed and works).
- **Posting times.** Long video at 06:30 IST, which is 8 pm in New York (US prime time, higher ad
  rates). Shorts at 07:30 and 19:30 IST, for Indian commuting and evening viewing. After 2 weeks,
  tune these from Studio → Analytics → Audience.
- **Cross-posting.** Every Short also goes to Instagram Reels and Facebook (from Telegram), which
  brings more people who later search for Thoma on YouTube.

## Extra income streams (start these early; they don't need monetization)
1. **AI tool videos + affiliate links** (from month 1). About a third of Shorts and a quarter of long
   videos are AI-tool spotlights and "how to use" tutorials (new launches from Product Hunt plus
   well-known tools like NotebookLM, Gamma, Perplexity). Many AI tools pay 20–30% recurring commission.
   Sign up for their affiliate programmes, put your links in `ai_tools.affiliates` in `config.yaml`, and
   every video that mentions the tool gets the link and a disclosure in its description. Facts and
   prices come only from the tool's own website, with the date. Honest reviews keep trust (and the
   channel safe).
2. **A free cheat sheet or "AI basics" PDF** in exchange for an email address. That builds an
   audience you own.
3. **Sponsorships** around 5k–10k subscribers: tech and edtech brands pay small education channels
   ₹5k–50k per mention.
4. **Memberships** at the early tier (500 subs): bonus videos, early access.

## The weekly review (30 minutes, every Sunday)
Look at YouTube Studio:
- **Shorts:** "Viewed vs swiped away". Above 70% is good; below 60% means weak hooks.
- **Long videos:** average percentage viewed. Above 40% at 5 minutes is good. Where do people drop?
- **Click-through rate:** above 5% is good.
- **Top 3 topics by views:** make more of those.

Then tell Qoder what you saw ("security topics do 3x better", "people leave at 0:20", "more Shorts
like #14") and it adjusts topics, hooks or pacing in `config.yaml`, `thoma/character.md` or `thoma/writer.py`.

## Sources
YouTube Partner Program requirements 2026 (vidiq.com, air.io), the February 2027 YPP change
(ppc.land), the inauthentic content policy and the January 2026 enforcement (techtimes.com,
newmoneymatrix.org, lenspov.com), RPM estimates (upgrowth.in, bosswallah.com, collabpals.com).
All third-party figures are estimates; trust your own YouTube Studio numbers once you have them.
