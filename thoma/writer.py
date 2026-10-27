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
    # Shorts may run up to 3 minutes; most topics need 60-90 s. Length follows what the topic needs.
    "short": {"words": (110, 300), "target": "150-220 (only go past 220 if the topic truly needs it)", "scenes": (7, 22),
              "max_per_visual": 28, "signoff": "thoma out", "spec": (
        "A vertical Short/Reel, usually 60-90 seconds (150-220 spoken words at a relaxed pace); up to 2 minutes "
        "(300 words) only when the idea can't be made clear in less. Never pad. "
        "Scene 1 is the hook in under 12 words: a surprising question or fact about what the viewer "
        "will understand. No greeting, no self-introduction. One concept only; if it is abstract, carry it with one "
        "simple everyday example from start to end. One diagram, one 'here's the trick' moment. The last line lands the takeaway, ends with 'Thoma out!', and should flow "
        "back into the hook so the Short loops naturally.")},
    # 8+ minutes: YouTube only allows mid-roll ads from 8:00, which roughly doubles what a video earns.
    "long": {"words": (1340, 1600), "target": "1400-1500", "scenes": (45, 85), "max_per_visual": 32, "signoff": "thoma out", "spec": (
        "A 16:9 deep-dive of 8-9 minutes (1400-1500 spoken words; it must not be shorter, mid-roll ads need 8:00). "
        "Scene 1-2 is the hook: what the viewer will finally understand, why it matters to them, and an open "
        "loop ('by the end you'll know why ...'). Scene 3: 'I'm Thoma, your friendly neighbourhood tech imp. Let's "
        "poke at <topic>.' Then 5-7 chapters that build on each other: the everyday analogy, the real mechanism "
        "step by step SHOWN with concept visuals and diagrams (every abstract step gets a simple everyday example; "
        "skip it where the thing is already concrete), a concrete worked example (code if it is a coding "
        "topic), the common misconception, what it means in real life and what's new in the field, then the "
        "takeaway. Every 60-90 seconds re-hook the viewer with a new question or twist ('but here's where it gets "
        "weird...'). Around the middle, one natural line inviting people to subscribe for a new explainer every "
        "day (never 'smash the like button'). Pay off the opening loop near the end. Mark 6-9 section starts "
        "with \"chapter\": \"<=30 chars\" on that scene (YouTube chapters). "
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
            "tip, not an advert. Title like '<Tool>: the AI that <does X>'.",
    "debate": "Format: the big debate, settled with facts. Open with the question people argue about, in "
              "plain words (scene 1, a compare visual of the two camps). Then SHOW what is really happening "
              "inside, step by step, with concept visuals (tokens / predict / vectors / network / chat), so the "
              "viewer can judge for themselves. Give Thoma's honest verdict based only on established facts, and "
              "say clearly where experts still disagree. Never invent quotes, studies or numbers; say 'some "
              "researchers' unless the notes name them. Last line: ask which side they're on in the comments, "
              "then the sign-off. Title is the debate question, e.g. 'Does ChatGPT actually think?'",
    "news": "Format: fresh news, explained. Start from what just happened (from the research notes, stating "
            "only what the notes support), then explain the underlying concept a beginner needs to understand "
            "it. Title like '<news thing>, explained simply'.",
}

SCRIPT_SHAPE = """Reply with JSON only:
{"title":"<=70 chars. Short: a curiosity question or '<Topic>, explained simply'. Long: '<Topic> explained in 5 minutes' or 'What is <Topic>? (explained simply)'. Plain search words first.",
 "description":"3-5 sentences. The first sentence repeats the main search words naturally (it shows in search results). Then what the viewer learns, plain and helpful, no hashtags, no timestamps",
 "tags":["10-15 search tags people really type, most specific first"],
 "hashtags":["3-5 hashtags without #"],
 "thumb_text":"2-5 BIG words for the thumbnail, one *highlighted*, <=30 chars, e.g. 'RAG in *5 minutes*'",
 "thumb_icon":"one icon name",
 "pinned_comment":"one short question viewers will want to answer (their opinion or guess), pinned as the first comment",
 "terms":[{"term":"embedding","scene":6,"plain":"the exact plain words Thoma uses in that scene to explain it"}],
 "scenes":[{"say":"what Thoma says, 1-2 natural spoken sentences, <=40 words","mood":"talk","visual":{...}}]}
mood is one of: talk, point, think, wow, laugh, wave (wave only in the first or last scene).
Use think before a question, wow on a surprising fact, laugh right after a joke.
"terms" lists EVERY technical word or acronym the narration uses (model, token, RAG, API, ...), with the scene
that explains it in plain words: the scene where it is first said, or the very next one. Fewer terms is better:
if a plain phrase works ("a program trained on lots of text"), say that instead of the term.
Keep one word for one thing all video long (don't switch "pages" to "chunks" to "cards").
In "say" you may use one <laugh> per video after a joke; no other tags, and no pauses."""

TOOL_LONG = ("This video is a hands-on tutorial on an AI tool: what it is, then how to use it for 2-3 real "
             "everyday tasks step by step (steps and diagram visuals), what it is good and bad at, one or two "
             "alternatives in a line, and pricing only as stated in the research notes, with the month and year. "
             "Never invent features. Helpful and honest, never an advert.")

TOOL_RESEARCH_SYSTEM = """You prepare research notes about an AI tool for a beginner tutorial. Facts about the
tool (what it does, who it's for, features, free plan and prices with the exact wording, limits) come ONLY from
the official website text. The material may also include transcripts of the most-watched tutorials of this
tool: use them to learn how people really use it (the real steps, useful tips, what beginners get stuck on,
which uses viewers love), and turn the structure of the best one into a beat sheet: the steps in order,
each described by the job it does for the viewer, never by its words. If a fact is in neither, leave it
out completely: never note what is missing or "unknown", and never guess. Write in your own words.
Reply as JSON: {"notes": ["...", "..."], "teaching": ["what makes it click for beginners", "..."],
 "beat_sheet": ["1. hook: ...", "..."], "beginner_questions": ["...", "..."]}"""

RESEARCH_SYSTEM = """You prepare research notes for a beginner tech explainer. From the source
material, extract what is true and useful: key concepts, how it works step by step, concrete
numbers or examples, common misconceptions, and anything time-sensitive (versions, dates).
The material may also include transcripts of the most-watched YouTube explainers on this topic. Study
HOW they make it click for ordinary viewers: the order they explain things in, the kind of everyday
example they lean on, and where viewers usually get confused. Write that down as teaching notes, and
turn the structure of the best one into a beat sheet: the steps in order, each described by the job it
does for the viewer ("hook: a problem everyone has had", "show what goes wrong without it"), never by
its words or its example. Then suggest everyday examples of our own that fit those beats and are
DIFFERENT from the ones the popular videos use.
Write everything in your own words, never copy sentences. Reply as JSON:
{"notes": ["...", "..."], "teaching": ["what makes this click for beginners: order, kind of example, pitfalls", "..."],
 "beat_sheet": ["1. hook: ...", "2. ...", "..."],
 "fresh_examples": ["an everyday situation a 10th-standard student knows, that carries the idea", "..."],
 "beginner_questions": ["what a beginner would ask", "..."]}"""

REVIEW_SYSTEM = """You are a strict editor for a beginner tech channel. Check the script for:
1. accuracy: anything false, misleading or outdated about the technology;
2. the student test: imagine a 10th-standard student who has never coded hears this once. Write what
   they would tell a friend the video said (student_summary). List every line they would not understand
   or would need to hear twice, every term used before it is explained, and every abstract sentence that
   needs a concrete example. If an abstract idea (how something works inside) has no simple everyday
   example, say so; don't ask for an example where the line is already concrete (a real tool, a real news event);
3. consistency: a line that contradicts an earlier one, or one thing called by different names;
4. tone: anything condescending, hype-y, or salesy;
5. visuals: a visual that does not match what is said in that scene, or things on screen never mentioned.
Only list real problems, each pointing at the scene number. Reply as JSON:
{"student_summary": "...", "ok": true|false, "problems": ["scene 3: ...", ...]}"""

# "Does AI think?", "Will AI replace...", "Is ChatGPT...": questions people argue about.
DEBATE = re.compile(r"^\W*(do|does|did|is|are|can|could|will|would|should)\b(?!.*\bwhat is\b)", re.I)
GREETINGS = re.compile(r"^\W*(hi|hello|hey|welcome|namaste|what's up)\b", re.I)
TYPES = {"title", "bigtext", "stat", "diagram", "steps", "compare", "analogy", "code", "keep", "takeaway",
         "tokens", "predict", "vectors", "network", "chat"}
CONCEPT = {"tokens", "predict", "vectors", "network", "chat"}
# Words a 10th-standard student won't know. Each must be listed in script["terms"] with the scene that
# explains it in plain words, at most one scene after it is first said (the hook gets 3 scenes).
JARGON = ["neural network", "context window", "vector database", "training data", "fine-tuning", "fine-tune",
          "open source", "open-source", "model", "token", "embedding", "vector", "parameter", "weights",
          "dataset", "algorithm", "inference", "chunk", "retrieval", "agent", "database", "latency",
          "benchmark", "protocol", "framework", "metadata", "schema", "markdown", "api"]
KNOWN_ACRONYMS = {"AI", "AIS", "OK", "TV", "PC", "ID", "PDF", "PDFS", "USB", "UPI", "SMS", "GPS", "ATM", "PIN",
                  "CEO", "USA", "UK", "EU", "FAQ", "WIFI"}
STOP = {"the", "and", "for", "your", "you", "with", "from", "this", "that", "not", "one", "all", "are", "new",
        "its", "how", "what", "why", "question", "answer", "user", "bot"}


def _toks(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def _spoken(label, text):
    """Is any real word of an on-screen label said (plurals and -ing forms count)?"""
    words = [w for w in _toks(label) if len(w) >= 3 and w not in STOP]
    heard = {w[:4] for w in _toks(text)}
    return not words or any(w[:4] in heard for w in words)


def _term_problems(script) -> list[str]:
    scenes = script["scenes"]
    listed = {}
    for t in script.get("terms") or []:
        if isinstance(t, dict) and t.get("term"):
            listed[re.sub(r"s$", "", str(t["term"]).lower().strip())] = t
    first = {}
    for i, s in enumerate(scenes, 1):
        low = s.get("say", "").lower()
        for j in JARGON:
            if j not in first and re.search(rf"\b{re.escape(j)}s?\b", low):
                first[j] = i
        for a in re.findall(r"\b[A-Z]{2,5}s?\b", s.get("say", "")):
            if a.upper() not in KNOWN_ACRONYMS:
                first.setdefault(a.rstrip("s").lower(), i)
    out = []
    for term, i in first.items():
        entry = next((e for k, e in listed.items() if term in k or k in term), None)
        if entry is None and any(term in str(e.get("plain", "")).lower() for e in listed.values()):
            continue  # part of another term's explanation ("RAG, short for Retrieval-Augmented Generation")
        late = i + (3 if i == 1 else 1)
        if entry is None:
            out.append(f"scene {i} says '{term}' but never explains it. Explain it in plain words right there "
                       "(or say the plain idea and skip the word), and list it in \"terms\"")
            continue
        try:
            at = int(entry.get("scene"))
        except (TypeError, ValueError):
            at = 0
        plain = entry.get("plain", "")
        if not 1 <= at <= min(late, len(scenes)) or not _spoken(plain, scenes[at - 1].get("say", "")):
            out.append(f"'{term}' is first said in scene {i}; explain it in plain words in that scene "
                       f"(or by scene {late}) and point \"terms\" at the scene that really says it")
    return out


def _label_problems(scenes) -> list[str]:
    """On-screen things the narration never mentions confuse beginners ('what is that box?')."""
    out = []
    for i, s in enumerate(scenes):
        text, j = s.get("say", ""), i + 1
        while j < len(scenes) and (scenes[j].get("visual") or {}).get("type") == "keep":
            text += " " + scenes[j].get("say", "")
            j += 1
        v = s.get("visual") or {}
        if v.get("type") == "diagram":
            labels = [n.get("label", "") for n in v.get("nodes") or [] if isinstance(n, dict)]
        elif v.get("type") == "vectors":
            labels = [" ".join([g.get("label", "")] + list(g.get("items") or []))
                      for g in v.get("groups") or [] if isinstance(g, dict)]
        else:
            continue
        missing = [l for l in labels if not _spoken(l, text)]
        if len(missing) >= 3 or (v.get("type") == "vectors" and len(missing) >= 2):
            out.append(f"scene {i + 1}: the screen shows {missing} but Thoma never mentions them; say what "
                       "they are or drop them from the visual")
    return out


def words(script) -> int:
    return sum(len(s["say"].split()) for s in script["scenes"])


def _ngrams(text, n=7):
    t = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(t[i:i + n]) for i in range(len(t) - n + 1)}


def _tags_len(tags):
    return len(",".join(f'"{t}"' if " " in t else t for t in tags))


def gates(script: dict, kind: str, idea, check_repeats: bool = True) -> list[str]:
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
    if not 3 <= len(script.get("thumb_text", "")) <= 34:  # long: thumbnail; short: cover frame
        p.append("thumb_text must be 2-5 words, <=30 chars")
    if kind == "long" and sum(1 for s in scenes if s.get("chapter")) < 5:
        p.append("mark at least 5 section starts with \"chapter\"")
    if not 20 <= len(script.get("pinned_comment", "")) <= 200:
        p.append("pinned_comment must be one question for viewers, 20-200 chars")
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
        elif t == "tokens" and not 2 <= len(str(v.get("text", "")).split()) <= 10:
            p.append(f"scene {i}: tokens needs a sentence of 2-10 words in text")
        elif t == "predict" and not (v.get("prompt") and 2 <= len(v.get("options") or []) <= 5):
            p.append(f"scene {i}: predict needs a prompt and 2-5 options")
        elif t == "vectors" and not 1 <= len(v.get("groups") or []) <= 4:
            p.append(f"scene {i}: vectors needs 1-4 groups")
        elif t == "chat" and not 1 <= len(v.get("messages") or []) <= 4:
            p.append(f"scene {i}: chat needs 1-4 messages")
        for m in v.get("messages") or []:
            if isinstance(m, dict) and len(str(m.get("text", ""))) > 90:
                p.append(f"scene {i}: chat message over 90 chars")
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
        if run > f["max_per_visual"] + 8:
            p.append(f"scenes {start}-{i}: one visual covers {run} spoken words; change the visual at least "
                     f"every {f['max_per_visual']} words (about 10 seconds) so the screen keeps moving")
            break
    p += _term_problems(script) + _label_problems(scenes)
    rich = sum(1 for k in kinds if k in CONCEPT | {"diagram", "steps", "compare", "analogy", "code", "stat"})
    if rich < (2 if kind == "short" else 14):
        p.append("too few real visuals: use more diagrams, steps, compares, analogies")
    # Never reuse the source channel's wording.
    if idea is not None:
        source = (idea["source_text"] or "") + " " + (idea["transcript"] or "")
        narration = " ".join(s["say"] for s in scenes)
        copied = _ngrams(narration) & _ngrams(source)
        if copied:
            p.append(f"narration copies source wording: {sorted(copied)[:2]}; rephrase in Thoma's own words")
    if not check_repeats:  # a revision of this same video naturally matches itself
        return p
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


def repair(script: dict) -> dict:
    """Fix mechanical slips in code instead of spending a whole LLM rewrite on them."""
    for s in script.get("scenes") or []:
        v = s.get("visual") or {}
        t = v.get("type")
        if t in ("row", "stack", "grid", "hub", "cycle", "flow", "pipeline"):  # a layout name used as a type
            v["type"], v["layout"] = "diagram", t if t in ("row", "stack", "grid", "hub", "cycle") else "row"
        elif t not in TYPES:
            v.clear()
            v.update({"type": "bigtext", "text": " ".join(s.get("say", "").split()[:8])})
        if v.get("type") == "diagram":
            for n in v.get("nodes") or []:
                if isinstance(n, dict) and len(n.get("label", "")) > 22:
                    n["label"] = n["label"][:21].rsplit(" ", 1)[0]
        s["visual"] = v
    return script


EXAMPLES = Path(__file__).parent.parent / "assets/examples"


def save_example(script: dict, kind: str, vid: int) -> None:
    """An approved script becomes a reference the writer must match (newest 3 per kind are kept)."""
    d = EXAMPLES / kind
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{vid:04d}.json").write_text(json.dumps(script, indent=1, ensure_ascii=False))
    for old in sorted(d.glob("*.json"))[:-3]:
        old.unlink()


def example(kind: str) -> str:
    files = sorted((EXAMPLES / kind).glob("*.json"))
    if not files:
        return ""
    s = json.loads(files[-1].read_text())
    keep = {k: s[k] for k in ("title", "scenes") if k in s}
    return ("\n\n# A script the owner approved\nMatch its clarity, pace, use of one running example and visual "
            "variety. Do NOT reuse its topic, wording or examples.\n" + json.dumps(keep, ensure_ascii=False))


def log_review(script: dict, kind: str, topic: str, review: dict) -> None:
    """Every check is kept, so recurring mistakes show up in `thoma lessons` and in the next brief."""
    items = db.get_kv("review_log", [])
    items.append({"at": db.now(), "kind": kind, "topic": topic[:80], "writer": script.get("writer"),
                  "reviewer": llm.last_provider, "ok": not review.get("problems") or review.get("ok", False),
                  "problems": review.get("problems", []), "student": review.get("student_summary", "")})
    db.set_kv("review_log", items[-200:])


def recent_catches(kind: str, limit: int = 8) -> str:
    items = [p for i in db.get_kv("review_log", []) if i["kind"] == kind for p in i["problems"]]
    return "\n".join(f"- {p[:220]}" for p in items[-limit:])


def lessons_report() -> str:
    items = db.get_kv("review_log", [])
    if not items:
        return "No checks logged yet."
    out = ["First-check pass rate by writer:"]
    for w in sorted({i["writer"] or "?" for i in items}):
        mine = [i for i in items if (i["writer"] or "?") == w]
        out.append(f"  {w:<12} {sum(i['ok'] for i in mine)}/{len(mine)} scripts passed with no problems")
    out.append("\nMost recent catches (newest last):")
    out += [f"  [{i['writer']}->{i['reviewer']}] {i['topic'][:40]}: {p[:200]}" for i in items[-15:] for p in i["problems"]]
    return "\n".join(out)


def owner_feedback(limit: int = 12) -> str:
    """Recent owner notes: what they rejected or asked to fix, and why (pipeline.remember_feedback)."""
    items = [i for i in db.get_kv("owner_feedback", []) if i.get("note") or i["verdict"] == "rejected"][-limit:]
    notes: dict[str, list[str]] = {}  # same note on several videos -> one line
    for i in items:
        notes.setdefault(i["note"] or "no reason given", []).append(f"{i['verdict']} '{i['title']}'")
    return "\n".join(f"- {'; '.join(videos)}: {note}" for note, videos in notes.items())


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
    tool = ideas.is_tool(idea)
    # the most-watched explainers (tutorials, for a tool) teach how to make it click
    top = ideas.top_explainers(f"{idea['source_title']} tutorial" if tool else idea["topic"])
    popular = "\n\n".join(f"Popular {'tutorial' if tool else 'explainer'} '{v['title']}' ({v['views']:,} views), "
                           f"transcript:\n{v['transcript'][:5000]}" for v in top)
    if tool:
        page = _website_text(ideas.tool_site(idea))
        transcript = idea["transcript"] or ""
        material = (f"Tool: {idea['source_title']}\nTagline: {(idea['source_text'] or '').splitlines()[0]}\n\n"
                    f"Official website:\n{page[:14000]}\n\n{popular}")
        system = TOOL_RESEARCH_SYSTEM
    else:
        transcript = idea["transcript"] or ("" if idea["source"] == "owner" else ideas.transcript(idea))
        # links in the owner's idea ("/short this new tool https://...") are read as source material
        pages = "\n\n".join(_website_text(u) for u in re.findall(r"https?://\S+", idea["topic"])[:3])
        material = (f"Title: {idea['source_title'] or idea['topic']}\n{idea['source_text'] or ''}\n\n{(transcript or '')[:9000]}"
                    f"\n\n{pages[:8000]}\n\n{popular}")
        system = RESEARCH_SYSTEM
    if top:  # the copy check (gates) compares the script against these too
        with db.conn() as c:
            c.execute("UPDATE ideas SET transcript=? WHERE id=?",
                      ((transcript or "") + "\n\n" + " ".join(v["transcript"] for v in top), idea["id"]))
    out = llm.ask_json(system, material[:32000] + f"\n\nTopic for our video: {idea['topic']}", "research")
    notes = "\n".join(f"- {n}" for n in out.get("notes", []))
    if out.get("teaching"):
        notes += ("\nHow the most-watched explainers make this click (learn from it; find your OWN example, "
                  "never reuse their wording):\n" + "\n".join(f"- {t}" for t in out["teaching"]))
    if out.get("beat_sheet"):
        notes += ("\nBeat sheet: the order that worked in the most-watched explainers. Follow it, in your own "
                  "words and with your own example:\n" + "\n".join(f"- {b}" for b in out["beat_sheet"]))
    if out.get("fresh_examples"):
        notes += "\nExample ideas of our own (pick one, or a better one):\n" + "\n".join(f"- {e}" for e in out["fresh_examples"])
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
    if DEBATE.match(idea["topic"]):
        return "debate"
    weights = dict(cfg().get("short_formats", {"explainer": 1}))
    if idea["source"] in ("evergreen", "owner") or (idea["priority"] or 0) < 3:
        weights.pop("news", None)
    with db.conn() as c:
        last = c.execute("SELECT script FROM videos WHERE kind='short' AND script IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    if last and len(weights) > 1:
        weights.pop(json.loads(last["script"]).get("format"), None)
    return random.choices(list(weights), weights=list(weights.values()))[0]


REVISE_RULES = """# Editing a finished video
The owner watched this video and asked for a change. Apply exactly what they ask, plus anything that
must change to stay consistent (a visual that shows the changed line, the title if it is now wrong).
Keep every other scene's "say" and "visual" EXACTLY as it is, word for word, so the rest of the
recorded voice can be reused. Times like 0:23 refer to the scene times listed. If the owner says
something is factually wrong, fix it so it is correct; never invent facts. Return the full script."""


def revise(script: dict, kind: str, feedback: str, idea=None, times: list | None = None) -> dict:
    """The owner's '/fix 12 <what to change>': change only those scenes, keep the rest identical."""
    fmt = script.get("format")
    spec = FORMATS[kind]["spec"] + ("\n" + SHORT_FORMATS[fmt] if kind == "short" and fmt in SHORT_FORMATS else "")
    system = f"{CHARACTER}\n\n# Format\n{spec}\n\n{visuals.SPEC}\n\n{SCRIPT_SHAPE}\n\n{REVISE_RULES}"
    listing = "\n".join(f"scene {i} ({int(a // 60)}:{int(a % 60):02}-{int(b // 60)}:{int(b % 60):02}): {s['say']}"
                         for i, (s, (a, b)) in enumerate(zip(script["scenes"], times or []), 1))
    prompt = (f"Owner's request: {feedback}\n\nWhen each scene is spoken:\n{listing}\n\n"
              f"Current script:\n{json.dumps(script, ensure_ascii=False)}")
    for attempt in range(3):
        new = llm.ask_json(system, prompt, f"revise-{kind}")
        problems = gates(new, kind, idea, check_repeats=False)
        if not problems:
            new["format"] = fmt
            return new
        log.info("revision %d failed gates: %s", attempt + 1, problems)
        prompt += "\n\nYour last version had these problems, fix them too:\n" + "\n".join(f"- {x}" for x in problems)
    raise ValueError("revision failed checks: " + "; ".join(problems))


def write(idea, kind: str) -> dict:
    from datetime import date
    from . import ideas
    fmt = pick_short_format(idea) if kind == "short" else ("tool-tutorial" if ideas.is_tool(idea) else "tutorial")
    spec = FORMATS[kind]["spec"] + ("\n" + SHORT_FORMATS[fmt] if kind == "short" else "")
    if fmt == "tool-tutorial":
        spec += "\n" + TOOL_LONG
    spec += f"\nToday's date: {date.today():%B %Y}."
    system = f"{CHARACTER}\n\n# Format\n{spec}\n\n{visuals.SPEC}\n\n{SCRIPT_SHAPE}{example(kind)}"
    lo, hi = FORMATS[kind]["words"]
    brief = (f"Topic: {idea['topic']}\nWord budget: aim for {FORMATS[kind]['target']} spoken words in total "
             f"(hard limits {lo}-{hi}). Count them before replying.\n")
    if idea["angle"]:
        brief += f"Suggested analogy (use it or find a better one): {idea['angle']}\n"
    if idea["source_title"]:
        brief += (f"Inspired by the video '{idea['source_title']}'. Use it only to know what people are "
                  "curious about; never reuse its wording or examples.\n")
    notes = research(idea)
    with db.conn() as c:  # research may have stored more source text for the copy check
        idea = c.execute("SELECT * FROM ideas WHERE id=?", (idea["id"],)).fetchone()
    if notes:
        brief += f"\nResearch notes (facts to rely on; explain them your own way):\n{notes}\n"
    with db.conn() as c:
        earlier = [r[0] for r in c.execute("SELECT title FROM videos WHERE idea_id=? AND title != ''", (idea["id"],))]
    if earlier:
        brief += ("\nThis topic already has a video: " + "; ".join(f"'{t}'" for t in earlier) +
                  ". Take a clearly different angle, hook and title.\n")
    catches = recent_catches(kind)
    if catches:
        brief += f"\nMistakes the checker caught in recent drafts. Don't make them:\n{catches}\n"
    lessons = owner_feedback()
    if lessons:
        brief += f"\nThe channel owner's feedback on earlier videos. Learn from it; don't repeat these mistakes:\n{lessons}\n"
    hooks = recent_hooks(kind)
    if hooks:
        brief += "\nRecent hooks (do NOT open the same way):\n" + "\n".join(f"- {h}" for h in hooks) + "\n"

    script, problems, reviewed = None, [], False
    deadline = 5  # drafts allowed; a review's fixes always get 2 more
    for attempt in range(8):
        if attempt >= deadline:
            break
        prompt = brief
        if script is not None:
            prompt += (f"\nYour previous draft:\n{json.dumps(script, ensure_ascii=False)}\n\n"
                       "Fix ALL of these problems and return the full corrected script:\n"
                       + "\n".join(f"- {x}" for x in problems)
                       + f"\nThe draft has {words(script)} spoken words; keep it between {lo} and {hi}. Fixes "
                       "must not grow the script: when you add an explanation, cut the same number of words "
                       "elsewhere, and change only the scenes the problems name.")
        script = repair(llm.ask_json(system, prompt, f"write-{kind}"))
        script["writer"] = llm.last_provider
        problems = gates(script, kind, idea)
        if problems:
            log.info("draft %d failed gates: %s", attempt + 1, problems)
            continue
        script["format"] = fmt
        if reviewed:
            return script
        review = llm.ask_json(REVIEW_SYSTEM, json.dumps(script, ensure_ascii=False), "review")
        log_review(script, kind, idea["topic"], review)
        reviewed = True
        deadline = max(deadline, attempt + 3)
        problems = review.get("problems", []) if not review.get("ok", True) else []
        if not problems:
            return script
        log.info("review asked for fixes: %s (student heard: %s)", problems, review.get("student_summary", ""))
    raise ValueError("script failed checks: " + "; ".join(problems))
