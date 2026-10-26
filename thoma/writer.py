"""Idea -> research notes -> checked script JSON.

The LLM writes, plain code checks (gates), a second LLM pass reviews accuracy
and tone, and anything that fails goes back to the writer with the reasons.
"""
import difflib
import json
import logging
import re
from pathlib import Path

from . import db, llm, visuals

log = logging.getLogger("thoma.writer")
CHARACTER = (Path(__file__).parent / "character.md").read_text()

FORMATS = {
    "short": {"words": (100, 175), "target": "130-155", "scenes": (7, 12), "max_per_visual": 28, "signoff": "thoma out", "spec": (
        "A vertical Short/Reel of 45-59 seconds (100-155 spoken words), part of the series '<topic> in 60 "
        "seconds'. Scene 1 is the hook in under 12 words: a surprising question or fact about what the viewer "
        "will understand. No greeting, no self-introduction. One concept only: one analogy, one diagram, one "
        "'here's the trick' moment. The last line lands the takeaway, ends with 'Thoma out!', and should flow "
        "back into the hook so the Short loops naturally.")},
    "long": {"words": (650, 850), "target": "700-800", "scenes": (20, 34), "max_per_visual": 32, "signoff": "thoma out", "spec": (
        "A 16:9 tutorial of about 5 minutes (650-850 spoken words). Scene 1 is the hook (what the viewer will "
        "understand and why it matters). Scene 2: 'I'm Thoma, your friendly neighbourhood tech imp. Let's poke at "
        "<topic>.' Then: the analogy, the real explanation step by step with diagrams, one concrete example (code "
        "if it is a coding topic), one common misconception, where it shows up in real life, and the takeaway. "
        "Mark 4-6 section starts with \"chapter\": \"<=30 chars\" on that scene (YouTube chapters). "
        "The last line ends with 'Stay curious. Thoma out!'")},
}

# Short formats rotate so the channel never feels like one template (config short_formats).
SHORT_FORMATS = {
    "explainer": "Format: explainer. Teach the one concept so a beginner truly gets it: hook, analogy, "
                 "how it really works (diagram), the 'here's the trick' moment, takeaway.",
    "myth": "Format: myth vs fact. Open by stating a popular belief about the topic as if true, then flip "
            "it ('...except that's not how it works'). Use a compare visual for myth vs reality, then the real "
            "explanation. Title like 'No, <thing> doesn't <myth>'.",
    "guess": "Format: can you guess? Open with a question the viewer tries to answer ('Guess how many... / "
             "What happens when...'), say 'take a guess', then reveal with a stat or "
             "bigtext visual and explain why. End by asking them to comment their guess before the sign-off.",
    "tool": "Format: AI tool spotlight. Hook with the specific everyday problem THIS tool solves, in your own "
            "words (never a generic line). Say what the tool is in one line, then how to use it in 3 simple steps (a steps or "
            "diagram visual), who it's great for, and one honest limitation. Mention price only if the research "
            "notes state it, phrased 'as of <month year>'. Never invent features. It must feel like a friend's "
            "tip, not an advert. Title like '<Tool>: the AI that <does X> (in 60 seconds)'.",
    "news": "Format: fresh news, explained. Start from what just happened (from the research notes, stating "
            "only what the notes support), then explain the underlying concept a beginner needs to understand "
            "it. Title like '<news thing>, explained in 60 seconds'.",
}

SCRIPT_SHAPE = """Reply with JSON only:
{"title":"<=70 chars. Short: '<Topic> in 60 seconds'. Long: '<Topic> explained in 5 minutes' or 'What is <Topic>? (explained simply)'. Plain search words first.",
 "description":"3-5 sentences: what the viewer learns, plain and helpful, no hashtags, no timestamps",
 "tags":["10-15 search tags people really type, most specific first"],
 "hashtags":["3-5 hashtags without #"],
 "thumb_text":"2-5 BIG words for the thumbnail, one *highlighted*, <=30 chars, e.g. 'RAG in *5 minutes*'",
 "thumb_icon":"one icon name",
 "scenes":[{"say":"what Thoma says, 1-2 natural spoken sentences, <=40 words","mood":"talk","visual":{...}}]}
mood is one of: talk, point, think, wow, laugh, wave (wave only in the first or last scene).
Use think before a question, wow on a surprising fact, laugh right after a joke.
In "say" you may use one <laugh> per video after a joke; no other tags, and no pauses."""

TOOL_LONG = ("This video is a hands-on tutorial on an AI tool: what it is, then how to use it for 2-3 real "
             "everyday tasks step by step (steps and diagram visuals), what it is good and bad at, one or two "
             "alternatives in a line, and pricing only as stated in the research notes, with the month and year. "
             "Never invent features. Helpful and honest, never an advert.")

TOOL_RESEARCH_SYSTEM = """You prepare research notes about an AI tool for a beginner tutorial, using ONLY the
text from the tool's own website given below. Extract: what it does in one line, who it's for, the main
features, how a beginner would start, whether a free plan exists and prices (only if stated, with the exact
wording), and any limits mentioned. If something is not on the page, write "unknown" - never guess.
Reply as JSON: {"notes": ["...", "..."], "beginner_questions": ["...", "..."]}"""

RESEARCH_SYSTEM = """You prepare research notes for a beginner tech explainer. From the source
material, extract what is true and useful: key concepts, how it works step by step, concrete
numbers or examples, common misconceptions, and anything time-sensitive (versions, dates).
Write neutral notes in your own words, never copy sentences. Reply as JSON:
{"notes": ["...", "..."], "beginner_questions": ["what a beginner would ask", "..."]}"""

REVIEW_SYSTEM = """You are a strict editor for a beginner tech channel. Check the script for:
1. accuracy: anything false, misleading or outdated about the technology;
2. clarity: any term used before it is explained, jargon a curious 15-year-old wouldn't know (in speech
   or on-screen text), or a jump a beginner cannot follow;
3. tone: anything condescending, hype-y, or salesy;
4. visuals: a visual that does not match what is said in that scene.
Only list real problems, each pointing at the scene number. Reply as JSON:
{"ok": true|false, "problems": ["scene 3: ...", ...]}"""

GREETINGS = re.compile(r"^\W*(hi|hello|hey|welcome|namaste|what's up)\b", re.I)
TYPES = {"title", "bigtext", "stat", "diagram", "steps", "compare", "analogy", "code", "keep", "takeaway"}


def words(script) -> int:
    return sum(len(s["say"].split()) for s in script["scenes"])


def _ngrams(text, n=7):
    t = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(t[i:i + n]) for i in range(len(t) - n + 1)}


def _tags_len(tags):
    return len(",".join(f'"{t}"' if " " in t else t for t in tags))


def gates(script: dict, kind: str, idea) -> list[str]:
    """Checks in plain code. Every returned string is a blocker sent back to the writer."""
    p, f = [], FORMATS[kind]
    scenes = script.get("scenes") or []
    if not scenes:
        return ["no scenes"]
    n = words(script)
    lo, hi = f["words"]
    if not lo <= n <= hi:
        per_scene = ", ".join(f"{i}:{len(sc.get('say', '').split())}" for i, sc in enumerate(scenes, 1))
        change = f"cut at least {n - hi}" if n > hi else f"add at least {lo - n}"
        p.append(f"total spoken words is {n}, allowed {lo}-{hi}: {change} words. Words per scene now: "
                 f"{per_scene}. Shorten the longest scenes; don't just drop the ending.")
    if not f["scenes"][0] <= len(scenes) <= f["scenes"][1]:
        p.append(f"{len(scenes)} scenes; must be {f['scenes'][0]}-{f['scenes'][1]}")
    title = script.get("title", "")
    if not 10 <= len(title) <= 70:
        p.append(f"title is {len(title)} chars; must be 10-70")
    tags = script.get("tags", [])
    if len(tags) < 8 or _tags_len(tags) > 450:
        p.append("need 8-15 tags, under 450 characters in total")
    if kind == "long" and not 3 <= len(script.get("thumb_text", "")) <= 34:
        p.append("thumb_text must be 2-5 words, <=30 chars")
    if kind == "long" and sum(1 for s in scenes if s.get("chapter")) < 3:
        p.append("mark at least 3 section starts with \"chapter\"")
    if GREETINGS.match(scenes[0]["say"]):
        p.append("scene 1 opens with a greeting; open on the hook instead")
    if (scenes[0].get("visual") or {}).get("type") == "keep":
        p.append("scene 1 visual cannot be 'keep'")
    if (scenes[-1].get("visual") or {}).get("type") != "takeaway":
        p.append("last scene visual must be type 'takeaway'")
    if f["signoff"] not in scenes[-1]["say"].lower():
        p.append("the last line must end with the sign-off 'Thoma out!'")
    kinds = []
    for i, s in enumerate(scenes, 1):
        if len(s.get("say", "").split()) > 40:
            p.append(f"scene {i}: say is over 40 words, split it")
        v = s.get("visual") or {}
        t = v.get("type")
        kinds.append(t)
        if t not in TYPES:
            p.append(f"scene {i}: unknown visual type {t!r}")
        elif t == "diagram" and not 2 <= len(v.get("nodes") or []) <= 6:
            p.append(f"scene {i}: a diagram needs 2-6 nodes")
        elif t == "steps" and not 2 <= len(v.get("items") or []) <= 5:
            p.append(f"scene {i}: steps needs 2-5 items")
        elif t == "code" and not v.get("lines"):
            p.append(f"scene {i}: code needs lines")
        for key, lim in (("text", 90), ("heading", 44), ("sub", 64), ("label", 54)):
            if len(str(v.get(key, ""))) > lim:
                p.append(f"scene {i}: visual {key} is over {lim} chars")
        for node in v.get("nodes") or []:
            if isinstance(node, dict) and len(node.get("label", "")) > 22:
                p.append(f"scene {i}: node label '{node['label']}' over 22 chars")
    run, start = 0, 1
    for i, s in enumerate(scenes, 1):  # words spoken over one visual (keep scenes extend it)
        if (s.get("visual") or {}).get("type") != "keep":
            run, start = 0, i
        run += len(s.get("say", "").split())
        if run > f["max_per_visual"]:
            p.append(f"scenes {start}-{i}: one visual covers {run} spoken words; change the visual at least "
                     f"every {f['max_per_visual']} words (about 10 seconds) so the screen keeps moving")
            break
    rich = sum(1 for k in kinds if k in ("diagram", "steps", "compare", "analogy", "code", "stat"))
    if rich < (2 if kind == "short" else 6):
        p.append("too few real visuals: use more diagrams, steps, compares, analogies")
    # Never reuse the source channel's wording.
    if idea is not None:
        source = (idea["source_text"] or "") + " " + (idea["transcript"] or "")
        narration = " ".join(s["say"] for s in scenes)
        copied = _ngrams(narration) & _ngrams(source)
        if copied:
            p.append(f"narration copies source wording: {sorted(copied)[:2]}; rephrase in Thoma's own words")
    # Don't repeat ourselves.
    with db.conn() as c:
        past = c.execute("SELECT title, script FROM videos WHERE kind=? AND script IS NOT NULL"
                         " ORDER BY id DESC LIMIT 40", (kind,)).fetchall()
    for row in past:
        if difflib.SequenceMatcher(None, row["title"].lower(), title.lower()).ratio() > 0.85:
            p.append(f"title is almost the same as an earlier video: {row['title']!r}")
            break
    hook = " ".join(scenes[0]["say"].lower().split()[:4])
    for row in past[:5]:
        old = json.loads(row["script"])["scenes"][0]["say"].lower().split()[:4]
        if hook == " ".join(old):
            p.append("hook starts the same way as a recent video; vary the opening")
            break
    return p


def recent_hooks(kind: str) -> list[str]:
    with db.conn() as c:
        rows = c.execute("SELECT script FROM videos WHERE kind=? AND script IS NOT NULL"
                         " ORDER BY id DESC LIMIT 5", (kind,)).fetchall()
    return [json.loads(r["script"])["scenes"][0]["say"] for r in rows]


def _website_text(url: str) -> str:
    """Readable text of a tool's website (follows Product Hunt's redirect to the real site)."""
    import html as htmlmod
    if not url:
        return ""
    try:
        import httpx
        r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 ThomaStudio"})
        page = re.sub(r"(?is)<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", r.text)
        text = htmlmod.unescape(re.sub(r"<[^>]+>", " ", page))
        return f"Website: {r.url}\n" + " ".join(text.split())[:15000]
    except Exception as e:
        log.info("could not read %s: %s", url, e)
        return ""


def research(idea) -> str:
    """Neutral notes from the source video's transcript (cached on the idea)."""
    if idea["research"]:
        return idea["research"]
    from . import ideas
    if ideas.is_tool(idea):
        page = _website_text(ideas.tool_site(idea))
        material = f"Tool: {idea['source_title']}\nTagline: {(idea['source_text'] or '').splitlines()[0]}\n\n{page}"
        system = TOOL_RESEARCH_SYSTEM
    else:
        transcript = idea["transcript"] or ideas.transcript(idea)
        material = f"Title: {idea['source_title'] or idea['topic']}\n{idea['source_text'] or ''}\n\n{transcript or ''}"
        system = RESEARCH_SYSTEM
    out = llm.ask_json(system, material[:24000] + f"\n\nTopic for our video: {idea['topic']}", "research")
    notes = "\n".join(f"- {n}" for n in out.get("notes", []))
    if out.get("beginner_questions"):
        notes += "\nBeginner questions to answer:\n" + "\n".join(f"- {q}" for q in out["beginner_questions"])
    with db.conn() as c:
        c.execute("UPDATE ideas SET research=? WHERE id=?", (notes, idea["id"]))
    return notes


def pick_short_format(idea) -> str:
    """Weighted rotation from config, never the same format twice in a row; 'news' only for fresh ideas.
    AI tool ideas always use the 'tool' format."""
    import random
    from . import ideas
    from .config import cfg
    if ideas.is_tool(idea):
        return "tool"
    weights = dict(cfg().get("short_formats", {"explainer": 1}))
    if idea["source"] in ("evergreen", "owner") or (idea["priority"] or 0) < 3:
        weights.pop("news", None)
    with db.conn() as c:
        last = c.execute("SELECT script FROM videos WHERE kind='short' AND script IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    if last and len(weights) > 1:
        weights.pop(json.loads(last["script"]).get("format"), None)
    return random.choices(list(weights), weights=list(weights.values()))[0]


def write(idea, kind: str) -> dict:
    from datetime import date
    from . import ideas
    fmt = pick_short_format(idea) if kind == "short" else ("tool-tutorial" if ideas.is_tool(idea) else "tutorial")
    spec = FORMATS[kind]["spec"] + ("\n" + SHORT_FORMATS[fmt] if kind == "short" else "")
    if fmt == "tool-tutorial":
        spec += "\n" + TOOL_LONG
    spec += f"\nToday's date: {date.today():%B %Y}."
    system = f"{CHARACTER}\n\n# Format\n{spec}\n\n{visuals.SPEC}\n\n{SCRIPT_SHAPE}"
    lo, hi = FORMATS[kind]["words"]
    brief = (f"Topic: {idea['topic']}\nWord budget: aim for {FORMATS[kind]['target']} spoken words in total "
             f"(hard limits {lo}-{hi}). Count them before replying.\n")
    if idea["angle"]:
        brief += f"Suggested analogy (use it or find a better one): {idea['angle']}\n"
    if idea["source_title"]:
        brief += (f"Inspired by the video '{idea['source_title']}'. Use it only to know what people are "
                  "curious about; do not follow its structure or wording.\n")
    notes = research(idea)
    if notes:
        brief += f"\nResearch notes (facts to rely on; explain them your own way):\n{notes}\n"
    with db.conn() as c:
        earlier = [r[0] for r in c.execute("SELECT title FROM videos WHERE idea_id=? AND title != ''", (idea["id"],))]
    if earlier:
        brief += ("\nThis topic already has a video: " + "; ".join(f"'{t}'" for t in earlier) +
                  ". Take a clearly different angle, hook and title.\n")
    hooks = recent_hooks(kind)
    if hooks:
        brief += "\nRecent hooks (do NOT open the same way):\n" + "\n".join(f"- {h}" for h in hooks) + "\n"

    script, problems, reviewed = None, [], False
    for attempt in range(5):
        prompt = brief
        if script is not None:
            prompt += (f"\nYour previous draft:\n{json.dumps(script, ensure_ascii=False)}\n\n"
                       "Fix ALL of these problems and return the full corrected script:\n"
                       + "\n".join(f"- {x}" for x in problems)
                       + f"\nKeep the total spoken words between {lo} and {hi} (count them).")
        script = llm.ask_json(system, prompt, f"write-{kind}")
        problems = gates(script, kind, idea)
        if problems:
            log.info("draft %d failed gates: %s", attempt + 1, problems)
            continue
        script["format"] = fmt
        if reviewed:
            return script
        review = llm.ask_json(REVIEW_SYSTEM, json.dumps(script, ensure_ascii=False), "review")
        reviewed = True
        problems = review.get("problems", []) if not review.get("ok", True) else []
        if not problems:
            return script
        log.info("review asked for fixes: %s", problems)
    raise ValueError("script failed checks after 5 drafts: " + "; ".join(problems))
