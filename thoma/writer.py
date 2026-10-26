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
    "short": {"words": (85, 140), "scenes": (5, 9), "spec": (
        "A vertical Short/Reel of 35-55 seconds (85-140 spoken words). Scene 1 is the hook: a surprising "
        "question or everyday situation in under 12 words, no greeting, no self-introduction. One concept "
        "only, explained with one analogy and one diagram. End with the takeaway scene and 'See you at the board.'")},
    "long": {"words": (650, 850), "scenes": (16, 30), "spec": (
        "A 16:9 tutorial of about 5 minutes (650-850 spoken words). Scene 1 is the hook (a question or "
        "everyday situation), scene 2 is 'I'm Thoma, and today we're drawing out <topic>.' Then: the analogy, "
        "the real explanation step by step with diagrams, one concrete example (code if it is a coding topic), "
        "one common misconception, where it is used in real life, and the takeaway. Mark 4-6 section starts "
        "with \"chapter\": \"<=30 chars\" on that scene (YouTube chapters). The last line ends with "
        "'Chalk it up, and I'll see you at the board.'")},
}

SCRIPT_SHAPE = """Reply with JSON only:
{"title":"<=70 chars, the plain search phrase first, e.g. 'What is RAG? Retrieval Augmented Generation Explained'",
 "description":"3-5 sentences: what the viewer learns, plain and helpful, no hashtags, no timestamps",
 "tags":["10-15 search tags people really type, most specific first"],
 "hashtags":["3-5 hashtags without #"],
 "thumb_text":"2-5 BIG words for the thumbnail, one *highlighted*, <=30 chars, e.g. 'RAG in *5 minutes*'",
 "thumb_icon":"one icon name",
 "scenes":[{"say":"what Thoma says, 1-3 short sentences, <=55 words","pose":"talk","visual":{...}}]}
pose is one of: talk, point (at the visual), think, wave (first or last scene only)."""

RESEARCH_SYSTEM = """You prepare research notes for a beginner tech explainer. From the source
material, extract what is true and useful: key concepts, how it works step by step, concrete
numbers or examples, common misconceptions, and anything time-sensitive (versions, dates).
Write neutral notes in your own words, never copy sentences. Reply as JSON:
{"notes": ["...", "..."], "beginner_questions": ["what a beginner would ask", "..."]}"""

REVIEW_SYSTEM = """You are a strict editor for a beginner tech channel. Check the script for:
1. accuracy: anything false, misleading or outdated about the technology;
2. clarity: any term used before it is explained, or a jump a beginner cannot follow;
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
    if not f["words"][0] <= n <= f["words"][1]:
        p.append(f"total spoken words is {n}; must be {f['words'][0]}-{f['words'][1]}")
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
    if "see you at the board" not in scenes[-1]["say"].lower():
        p.append("last line must end with the sign-off '... see you at the board.'")
    kinds = []
    for i, s in enumerate(scenes, 1):
        if len(s.get("say", "").split()) > 55:
            p.append(f"scene {i}: say is over 55 words, split it")
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


def research(idea) -> str:
    """Neutral notes from the source video's transcript (cached on the idea)."""
    if idea["research"]:
        return idea["research"]
    from . import ideas
    transcript = idea["transcript"] or ideas.transcript(idea)
    material = f"Title: {idea['source_title'] or idea['topic']}\n{idea['source_text'] or ''}\n\n{transcript or ''}"
    out = llm.ask_json(RESEARCH_SYSTEM, material[:24000] + f"\n\nTopic for our video: {idea['topic']}", "research")
    notes = "\n".join(f"- {n}" for n in out.get("notes", []))
    if out.get("beginner_questions"):
        notes += "\nBeginner questions to answer:\n" + "\n".join(f"- {q}" for q in out["beginner_questions"])
    with db.conn() as c:
        c.execute("UPDATE ideas SET research=? WHERE id=?", (notes, idea["id"]))
    return notes


def write(idea, kind: str) -> dict:
    system = f"{CHARACTER}\n\n# Format\n{FORMATS[kind]['spec']}\n\n{visuals.SPEC}\n\n{SCRIPT_SHAPE}"
    lo, hi = FORMATS[kind]["words"]
    brief = f"Topic: {idea['topic']}\nWord budget: {lo}-{hi} spoken words in total across all scenes.\n"
    if idea["angle"]:
        brief += f"Suggested analogy (use it or find a better one): {idea['angle']}\n"
    if idea["source_title"]:
        brief += (f"Inspired by the video '{idea['source_title']}'. Use it only to know what people are "
                  "curious about; do not follow its structure or wording.\n")
    notes = research(idea)
    if notes:
        brief += f"\nResearch notes (facts to rely on; explain them your own way):\n{notes}\n"
    hooks = recent_hooks(kind)
    if hooks:
        brief += "\nRecent hooks (do NOT open the same way):\n" + "\n".join(f"- {h}" for h in hooks) + "\n"

    script, problems, reviewed = None, [], False
    for attempt in range(4):
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
        if reviewed:
            return script
        review = llm.ask_json(REVIEW_SYSTEM, json.dumps(script, ensure_ascii=False), "review")
        reviewed = True
        problems = review.get("problems", []) if not review.get("ok", True) else []
        if not problems:
            return script
        log.info("review asked for fixes: %s", problems)
    raise ValueError("script failed checks after 4 drafts: " + "; ".join(problems))
