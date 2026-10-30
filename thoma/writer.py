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
    # Owner (2026-10-30): every video 5 minutes at most. 560-700 words is about 3:45-4:40 at 150 wpm.
    "long": {"words": (560, 700), "target": "620-680", "scenes": (24, 50), "max_per_visual": 32, "signoff": "thoma out", "spec": (
        "A 16:9 explainer of 4-5 minutes (620-680 spoken words; never under 560, and never over 700: the owner caps every video at 5 minutes, so every line must earn its place). "
        "Scene 1-2 is the hook: what the viewer will finally understand, why it matters to them, and an open "
        "loop ('by the end you'll know why ...'). Scene 3: 'I'm Thoma, your friendly neighbourhood tech imp. Let's "
        "poke at <topic>.' Then 4-5 chapters that build on each other: the everyday analogy, the real mechanism "
        "step by step SHOWN with concept visuals and diagrams (every abstract step gets a simple everyday example; "
        "skip it where the thing is already concrete), a concrete worked example (code if it is a coding "
        "topic), the common misconception, what it means in real life and what's new in the field, then the "
        "takeaway. Every 45-60 seconds re-hook the viewer with a new question or twist ('but here's where it gets "
        "weird...'). Around the middle, one natural line inviting people to subscribe for a new explainer every "
        "day (never 'smash the like button'). Pay off the opening loop near the end. Mark 4-6 section starts "
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
    "debate-teaser": "Format: the Short that leads to our full debate video (named in the brief). Open on the "
                     "single most surprising real fact of the fight (a photo or headlines visual), give each side's best "
                     "argument in one line each (a compare visual), then one fact that makes it harder to decide. "
                     "Attribute every claim; never state an accusation as fact. Ask which side the viewer is on, then "
                     "one natural line sending them to the full video, e.g. 'Both sides, with the real numbers, are in "
                     "the full video linked on this Short.' Title: the debate question.",
    "teaser": "Format: the Short that leads to our full video (named in the brief). Pick the ONE most surprising "
              "part of how it works and explain it completely, so the Short makes sense on its own: the hook "
              "(the first beats of the hook blueprint squeezed into 3-5 seconds), that one mechanism shown with "
              "visuals (parts, scan, zoom, layers or a diagram), then the 'here's the trick' moment. Don't reuse "
              "the full video's opening line. Just before the sign-off, one natural line sending viewers to the "
              "full video, e.g. 'The whole machine, piece by piece, is in the full video linked on this Short.' "
              "Title: a curiosity question about that one part.",
}

# Long "how does it really work?" videos about real machines and technology (ideas.is_how).
HOW_LONG = (
    "A 16:9 'how does it really work?' video of 4-5 minutes (620-680 spoken words; never under 560, and never "
    "over 700: the owner caps every video at 5 minutes, so every line must earn its place). For a 10th-standard student: every step is plain words plus the running "
    "example, never engineering talk.\n"
    "THE HOOK decides whether anyone watches. Open with the hook blueprint from the research notes, beat by "
    "beat, in the same order and at about the same timing (2.5 spoken words per second), in your own words. "
    "It follows the playbook of the best explainer channels: (a) scene 1, under 12 words: start in the middle "
    "of the most surprising real moment or fact, stated plainly, so the screen and the first words grab at "
    "once; (b) the question every viewer now has, in their own words; (c) the twist: why the obvious answer is "
    "wrong or not the whole story; (d) the promise: exactly what they'll understand by the end, left as an open "
    "loop you pay off later. The hook runs about as long as the blueprint's (under 30 seconds, about 70 words, "
    "without one), then the explanation starts. "
    "Never 'in this video', 'today we'll', a greeting or the channel name first. "
    "Thoma introduces himself in ONE short line ('I'm Thoma, and I love poking at machines.') only after the "
    "promise, never in scene 1 or 2.\n"
    "Then 4-5 tight chapters that build on each other: (1) the big picture in one everyday sentence; (2) the main "
    "parts, shown with a 'parts' visual; (3) how the parts work together, step by step, following ONE running "
    "example (the angle in the brief) through every step: say what happens to it at each stage, and show it "
    "with scan, zoom, layers, path, bars, timeline or diagram visuals; (4) the hardest problem and why it is "
    "hard, and what is real today versus promised or hype, with dates and who said it ('Tesla says...', "
    "'in the October 2026 demo...'), plus a myth and the truth; (5) the takeaway. Real numbers with units where "
    "the notes give them (stat or bars). Every 45-60 seconds re-hook with a new question or twist. Around the "
    "middle, one natural line inviting people to subscribe for more 'how it really works' videos. Pay off the "
    "opening promise near the end. Mark 4-6 section starts with \"chapter\": \"<=30 chars\". Never invent specs, "
    "dates, prices or quotes: if the notes don't say it, don't say it. The last line ends with 'Stay curious. "
    "Thoma out!'")

# Long "the big debate" videos about tech controversies (ideas.is_debate): researched from news on every side.
DEBATE_LONG = (
    "A 16:9 'the big tech debate' video of 4-5 minutes (620-680 spoken words; never under 560, and never over "
    "700: the owner caps every video at 5 minutes, so every line must earn its place). The viewer should finish able to judge the fight for themselves, and "
    "come back for the next one. For a 10th-standard student: plain words, every technical idea through one "
    "everyday example.\n"
    "THE HOOK: open with the hook blueprint from the research notes, beat by beat, in your own words: (a) scene 1, "
    "under 12 words: the sharpest REAL moment of the story (a number, a move, a claim), stated plainly, shown with "
    "a photo or headlines; (b) the question everyone is now asking; (c) the twist: why it is not as simple as either "
    "side says; (d) the promise: by the end they'll be able to decide for themselves. Under 30 seconds. Never "
    "'in this video', 'today we'll', a greeting or the channel name first. Thoma introduces himself in ONE short "
    "line only after the promise.\n"
    "Then 5 tight chapters: (1) what actually happened, in order, with dates and who did what (headlines, timeline, "
    "photos of the real people, products and places); (2) the tech underneath, explained simply: the thing a "
    "viewer must understand to judge the fight, SHOWN with diagrams and concept visuals and one running example "
    "(this is what makes us different from news channels); (3) the case FOR and the case AGAINST, each in its "
    "strongest honest form, with who makes it and their best evidence, and what the numbers actually say "
    "(bars, stat), including what nobody knows yet; (4) what it means for the viewer's own life, job or money "
    "(no financial advice: never say buy, sell or invest); (5) Thoma's verdict: an honest "
    "lean based only on the evidence, saying clearly what would change his mind; then ask viewers which side "
    "they are on in the comments. Use a compare visual for the two sides. Every 45-60 seconds re-hook with a new "
    "question or twist. Around the middle, one natural line inviting people to subscribe for a new tech debate "
    "every week. Pay off the opening promise near the end. Mark 4-6 section starts with \"chapter\": \"<=30 "
    "chars\".\n"
    "FAIRNESS AND FACTS (the channel's reputation and monetization depend on it): every claim comes from the "
    "research notes and is attributed ('Reuters reported in October...', 'the company says...', 'critics like "
    "... argue...'). An accusation is never stated as fact: say who accused whom of what, and the reply if the "
    "notes have one. Quotes only word for word from the notes. No insults, no mocking real people, no guesses "
    "about anyone's motives, no conspiracy talk. Funny is fine; unfair is not. The last line ends with 'Stay "
    "curious. Thoma out!'")

SCRIPT_SHAPE = """Reply with JSON only:
{"title":"<=70 chars. Short: a curiosity question or '<Topic>, explained simply'. Long: '<Topic> explained in 5 minutes' or 'What is <Topic>? (explained simply)'. Plain search words first.",
 "description":"3-5 sentences. The first sentence repeats the main search words naturally (it shows in search results). Then what the viewer learns, plain and helpful, no hashtags, no timestamps",
 "tags":["10-15 search tags people really type, most specific first"],
 "hashtags":["3-5 hashtags without #"],
 "thumb_text":"2-5 BIG words for the thumbnail, one *highlighted*, <=30 chars, e.g. 'RAG in *5 minutes*'",
 "thumb_icon":"one icon name",
 "pinned_comment":"one short question viewers will want to answer (their opinion or guess), pinned as the first comment",
 "terms":[{"term":"embedding","scene":6,"plain":"the exact plain words Thoma uses in that scene to explain it"}],
 "scenes":[{"say":"what Thoma says, 1-2 natural spoken sentences, <=40 words","mood":"talk","visual":{...}},
           {"say":"...","mood":"think","chapter":"<=30 chars, long videos only: on the FIRST scene of each section","visual":{...}}]}
"say" is ONLY the words Thoma speaks: no stage directions, no [brackets], no "Chapter:" labels, no sound effects.
The screen shows OUR animations plus real still photos (photo, photos and quote visuals), never video clips or sound
from events or other videos. So never say "watch this clip", "listen to that sound", "look at this footage", "count it
down with the room": tell what happened ("on stage, the car drove up a ramp and...") while a photo or animation shows it.
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

HOOK_STUDY = """The material may include the OPENING minute of the most-watched videos on this topic, with
timestamps. Study how the most-watched one hooks viewers: what it says or shows in the first 3 seconds, when
it names the topic, when it makes its promise ("by the end you'll know..."), when the presenter introduces
themselves (or never does), and when the real explanation starts. Write that down as "hook_blueprint": its
beats in order, each with its time range and the JOB the beat does, never its words or its example, e.g.
"0-4s: a real, surprising moment stated as plain fact", "4-10s: the question every viewer now has",
"10-18s: the promise of what they'll understand by the end". Then write "hook_example": opening lines for
OUR video that follow those beats exactly, in plain words, with our own example. Also compare the other
openings: if most of them share a move (start on the result, a bold claim, a "you've been told X, but..."),
note it in the blueprint. Hooks that work: start in the middle of the most surprising moment, name the
viewer's question, add a twist (the obvious answer is wrong), promise a clear payoff, all in under 30
seconds. No "in this video", no greeting, no channel name first."""

RESEARCH_JSON = """Write everything in your own words, never copy sentences. Reply as JSON:
{"notes": ["...", "..."], "teaching": ["what makes this click for beginners: order, kind of example, pitfalls", "..."],
 "beat_sheet": ["1. hook: ...", "2. ...", "..."],
 "fresh_examples": ["an everyday situation a 10th-standard student knows, that carries the idea", "..."],
 "beginner_questions": ["what a beginner would ask", "..."],
 "hook_blueprint": ["0-4s: ...", "..."], "hook_example": "..."}"""

HOW_RESEARCH_SYSTEM = """You prepare research notes for a beginner "how does it really work?" video about a
real machine or technology. The material is web pages (Wikipedia, recent news articles) and transcripts of
the most-watched YouTube explainers. Extract what is true: the main parts it is made of and what each one
does, how they work together step by step, real numbers with units, what is real today versus only promised
(with dates and who claimed it), what is still hard or unsolved, and common myths. A claim from a news story
is a fact only as "<who> said/showed on <date>"; when sources disagree, note both. Leave out anything you
are unsure of.
Study HOW the popular explainers make it click for ordinary viewers: the order they explain things in, the
kind of everyday example they lean on, and where viewers usually get confused. Turn the structure of the best
one into a beat sheet: the steps in order, each described by the job it does for the viewer, never by its
words or its example. Suggest everyday examples of our own that are DIFFERENT from theirs.
""" + HOOK_STUDY + "\n" + RESEARCH_JSON

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
""" + HOOK_STUDY + "\n" + RESEARCH_JSON

DEBATE_RESEARCH_SYSTEM = """You prepare research notes for a beginner video about a tech controversy: a fight
people argue about. The material is web pages (Wikipedia, recent news articles from several outlets, each with
its outlet and date) and transcripts of the most-watched YouTube videos on it. Extract what is true:
- what actually happened, in order, each event with its date and outlet ("Reuters, Oct 21 2026: ...");
- the technology underneath that a beginner must understand to judge the fight, step by step;
- the strongest case FOR and the strongest case AGAINST, each with who makes it and their best evidence;
- real numbers with units and where they come from; what nobody knows yet;
- exact quotes worth showing, copied word for word from an article with who said it and where
  ("QUOTE: \"...\" - name, outlet, date"); never shorten, merge or tidy a quote;
- the real people, companies, products and places involved (they will be shown as photos).
An accusation is a fact only as "<who> accused <whom> of <what> (<outlet>, <date>)", with the reply if there is
one. When sources disagree, note both. Leave out anything you are unsure of.
Study how the most-watched videos make it gripping and clear: the order they tell the story in, where viewers
get confused. Turn the structure of the best one into a beat sheet (the job of each beat, never its words).
""" + HOOK_STUDY + "\n" + RESEARCH_JSON

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
6. facts: every number, date, name and claim must be supported by the research notes (they may be newer than
   what you know; trust them over your memory). Flag anything the notes don't support, and any line where
   Thoma claims he was somewhere, filmed something or speaks as another person.
7. fairness, for anything controversial: both sides in their strongest honest form, every accusation
   attributed (never stated as fact), quotes word for word from the notes, no insults or guesses about
   motives, no financial advice, and a verdict that follows from the evidence shown.
8. photos: a photo/photos/quote visual whose "query" or "show" doesn't match what is said in that scene.
Only list real problems, each pointing at the scene number. Reply as JSON:
{"student_summary": "...", "ok": true|false, "problems": ["scene 3: ...", ...]}"""

# "Does AI think?", "Will AI replace...", "Is ChatGPT...": questions people argue about.
DEBATE = re.compile(r"^\W*(do|does|did|is|are|can|could|will|would|should)\b(?!.*\bwhat is\b)", re.I)
GREETINGS = re.compile(r"^\W*(hi|hello|hey|welcome|namaste|what's up)\b", re.I)
TYPES = {"title", "bigtext", "stat", "diagram", "steps", "compare", "analogy", "code", "keep", "takeaway",
         "tokens", "predict", "vectors", "network", "chat", "parts", "scan", "zoom", "layers", "path", "timeline", "bars"}
CONCEPT = {"tokens", "predict", "vectors", "network", "chat"}
MACHINE = {"parts", "scan", "zoom", "layers", "path", "timeline", "bars"}  # how-it-works visuals
REAL = {"photo", "photos", "headlines", "quote"}  # real photos and the news (images.py finds the photos)
TYPES |= REAL
# Words a 10th-standard student won't know. Each must be listed in script["terms"] with the scene that
# explains it in plain words, at most one scene after it is first said (the hook gets 3 scenes).
JARGON = ["neural network", "context window", "vector database", "training data", "fine-tuning", "fine-tune",
          "open source", "open-source", "model", "token", "embedding", "vector", "parameter", "weights",
          "dataset", "algorithm", "inference", "chunk", "retrieval", "agent", "database", "latency",
          "benchmark", "protocol", "framework", "metadata", "schema", "markdown", "api",
          # how-it-works topics
          "lidar", "qubit", "superposition", "entanglement", "electrolyte", "anode", "cathode", "electrode",
          "neuron", "aerodynamic", "propulsion", "actuator", "latency", "bandwidth", "phased array"]
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


def _explain_by(i: int, say: str) -> int:
    """The last scene where a term first said in scene i may still be explained. A list ("cameras, radar
    and lidar") is a preview: each item is then explained in turn, so it gets a few scenes."""
    if i == 1:
        return 4
    return i + (6 if say.count(",") >= 2 or re.search(r",? and \w+[.!?]?$", say.split(".")[0]) and say.count(",") else 1)


def _term_problems(script, skip=frozenset()) -> list[str]:
    scenes = script["scenes"]
    listed = {}
    for t in script.get("terms") or []:
        if isinstance(t, dict) and t.get("term"):
            listed[re.sub(r"s$", "", str(t["term"]).lower().strip())] = t
    first = {}
    for i, s in enumerate(scenes, 1):
        low = s.get("say", "").lower()
        for j in JARGON:
            if j in skip:
                continue
            if j not in first and re.search(rf"\b{re.escape(j)}s?\b", low):
                first[j] = i
        for a in re.findall(r"(?<![\w-])[A-Z]{2,5}s?(?![\w-])", s.get("say", "")):  # not names like I-PACE
            if a.upper() not in KNOWN_ACRONYMS:
                first.setdefault(a.rstrip("s").lower(), i)
    out = []
    for term, i in first.items():
        entry = next((e for k, e in listed.items() if term in k or k in term), None)
        if entry is None and any(term in str(e.get("plain", "")).lower() for e in listed.values()):
            continue  # part of another term's explanation ("RAG, short for Retrieval-Augmented Generation")
        late = _explain_by(i, scenes[i - 1].get("say", ""))
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
        elif v.get("type") == "parts":
            labels = [n.get("label", "") for n in v.get("parts") or [] if isinstance(n, dict)]
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


def _quote_problems(i: int, v: dict, idea) -> list[str]:
    """A quote on screen must be real: word for word in the research notes, with who said it."""
    text = re.sub(r"[*\"“”]", "", str(v.get("text", "")))
    if not (text and v.get("who")):
        return [f"scene {i}: a quote needs text and who"]
    q = re.findall(r"[a-z0-9']+", text.lower())
    notes = re.findall(r"[a-z0-9']+", ((idea["research"] if idea is not None else "") or "").lower())
    if not notes:
        return []
    run = max((b.size for b in difflib.SequenceMatcher(None, q, notes, autojunk=False).get_matching_blocks()), default=0)
    if run < 0.85 * len(q):
        return [f"scene {i}: the quote '{text[:60]}' is not word for word in the research notes; use an exact quote "
                "from the notes or say it as a plain attributed sentence instead"]
    return []


def _photo_problems(scenes, kinds, kind: str, idea) -> list[str]:
    """Real photos where the topic is real (owner, 2026-10-30), but animations still carry the explaining."""
    from . import ideas
    photos = sum(1 for s in scenes if (s.get("visual") or {}).get("type") in ("photo", "photos")
                 or ((s.get("visual") or {}).get("type") == "quote" and (s.get("visual") or {}).get("query")))
    shown = [k for k in kinds if k != "keep"]
    real = sum(1 for k in shown if k in REAL)
    debate, how = ideas.is_debate(idea), ideas.is_how(idea)
    need = (3 if debate or how else 0 if ideas.is_tool(idea) else 1) if kind == "long" else (1 if debate or how else 0)
    p = []
    if photos < need:
        p.append(f"only {photos} real photos; this video needs at least {need}: show the real products, people, "
                 "places and events with photo or photos visuals (one in the first 30 seconds)")
    if kind == "long" and debate and "headlines" not in kinds:
        p.append("a debate video shows the news it is about: add a headlines visual with the real outlets and dates")
    if kind == "long" and debate and "compare" not in kinds:
        p.append("a debate video needs a compare visual for the two sides")
    if shown and real > 0.4 * len(shown):
        p.append(f"{real} of {len(shown)} visuals are photos or news cards; animations must do most of the explaining "
                 "(at most 40% real photos), so SHOW how it works with diagrams and concept visuals")
    return p


def ideas_is_how(idea) -> bool:
    from . import ideas
    return ideas.is_how(idea)


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
    if kind == "long" and sum(1 for s in scenes if s.get("chapter")) < 4:
        p.append("mark at least 4 section starts with \"chapter\"")
    if not 20 <= len(script.get("pinned_comment", "")) <= 200:
        p.append("pinned_comment must be one question for viewers, 20-200 chars")
    if GREETINGS.match(scenes[0]["say"]):
        p.append("scene 1 opens with a greeting; open on the hook instead")
    if any(re.search(r"\bin (this|today's) video\b|\btoday,? (we|i)('re| are|'ll| will)\b", s.get("say", ""), re.I)
           for s in scenes[:3]):
        p.append("the hook says 'in this video' / 'today we'll'; start on the surprising moment instead")
    if len(scenes[0].get("say", "").split()) > 14:
        p.append("scene 1 is the hook's first line: 14 words at most")
    if kind == "long" and any(re.search(r"\bi'?m thoma\b", s.get("say", ""), re.I) for s in scenes[:2]):
        p.append("Thoma introduces himself in scene 1-2; open on the hook and introduce him after the promise")
    if (scenes[0].get("visual") or {}).get("type") == "keep":
        p.append("scene 1 visual cannot be 'keep'")
    if (scenes[-1].get("visual") or {}).get("type") != "takeaway":
        p.append("last scene visual must be type 'takeaway'")
    if f["signoff"] not in scenes[-1]["say"].lower():
        p.append("the last line must end with the sign-off 'Thoma out!'")
    kinds = []
    for i, s in enumerate(scenes, 1):
        if re.search(r"[\[\]]|^\W*chapter\b", s.get("say", ""), re.I):
            p.append(f"scene {i}: 'say' must be only the spoken words: no [stage directions] or 'Chapter:' labels")
        if re.search(r"\b(we|i) (shot|filmed|recorded|were there|was there)\b|\b(shot on a phone|raw clip|this clip|"
                     r"this footage|listen to (that|this)|watch (this|it) (happen|again)|count it down|even standing there)\b",
                     s.get("say", ""), re.I):
            p.append(f"scene {i}: we only show our own animation, never real footage, and Thoma wasn't there; "
                     "tell what happened instead of 'watch/listen to this clip'")
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
        elif t == "parts" and not 2 <= len(v.get("parts") or []) <= 6:
            p.append(f"scene {i}: parts needs 2-6 parts")
        elif t == "scan" and not 1 <= len(v.get("targets") or []) <= 5:
            p.append(f"scene {i}: scan needs 1-5 targets")
        elif t == "zoom" and not 2 <= len(v.get("levels") or []) <= 4:
            p.append(f"scene {i}: zoom needs 2-4 levels")
        elif t == "layers" and not 2 <= len(v.get("items") or []) <= 5:
            p.append(f"scene {i}: layers needs 2-5 items")
        elif t == "path" and not (v.get("from") and v.get("to")):
            p.append(f"scene {i}: path needs from and to")
        elif t == "timeline" and not 2 <= len(v.get("events") or []) <= 6:
            p.append(f"scene {i}: timeline needs 2-6 events")
        elif t == "bars" and not 2 <= len(v.get("items") or []) <= 6:
            p.append(f"scene {i}: bars needs 2-6 items with numeric values")
        elif t == "photo" and not (v.get("query") and v.get("show")):
            p.append(f"scene {i}: a photo needs 'query' (search words naming the real thing) and 'show'")
        elif t == "photos" and not 2 <= len([x for x in v.get("items") or [] if isinstance(x, dict) and x.get("query")]) <= 3:
            p.append(f"scene {i}: photos needs 2-3 items, each with a query")
        elif t == "headlines" and not (1 <= len(v.get("items") or []) <= 3
                                       and all(isinstance(x, dict) and x.get("source") and x.get("text") for x in v["items"])):
            p.append(f"scene {i}: headlines needs 1-3 items, each with source and text")
        elif t == "quote":
            p += _quote_problems(i, v, idea)
        for m in v.get("messages") or []:
            if isinstance(m, dict) and len(str(m.get("text", ""))) > 90:
                p.append(f"scene {i}: chat message over 90 chars")
        for key, lim in (("text", 90), ("heading", 44), ("sub", 64), ("label", 54)):
            if len(str(v.get(key, ""))) > lim:
                p.append(f"scene {i}: visual {key} is over {lim} chars")
        for node in v.get("nodes") or []:
            if isinstance(node, dict) and len(node.get("label", "")) > 22:
                p.append(f"scene {i}: node label '{node['label']}' over 22 chars")
    run, start, limit = 0, 1, f["max_per_visual"] + 8
    for i, s in enumerate(scenes, 1):  # words spoken over one visual (keep scenes extend it)
        v = s.get("visual") or {}
        if v.get("type") != "keep":
            run, start = 0, i
            # visuals that reveal 3+ elements as Thoma speaks keep moving on their own for longer
            limit = f["max_per_visual"] + 8 + (14 if len(visuals.elements(visuals.normalize(v))[0]) >= 3 else 0)
        run += len(s.get("say", "").split())
        if run > limit:
            p.append(f"scenes {start}-{i}: one visual covers {run} spoken words; change the visual at least "
                     f"every {f['max_per_visual']} words (about 10 seconds) so the screen keeps moving")
            break
    how = idea is not None and ideas_is_how(idea)
    p += _term_problems(script, {"model"} if how else frozenset()) + _label_problems(scenes)  # a car "model"
    rich = sum(1 for k in kinds if k in CONCEPT | MACHINE | REAL | {"diagram", "steps", "compare", "analogy", "code", "stat"})
    if rich < (2 if kind == "short" else 9):
        p.append("too few real visuals: use more diagrams, steps, compares, analogies")
    if how:
        machine = sum(1 for k in kinds if k in MACHINE)
        if machine < (1 if kind == "short" else 6):
            p.append(f"only {machine} how-it-works visuals; a 'how does it work' video should SHOW the machine: use "
                     f"parts, scan, zoom, layers, path, timeline or bars at least {1 if kind == 'short' else 6} times")
    p += _photo_problems(scenes, kinds, kind, idea)
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
        # other topics only: a rewrite of this topic's own video (validator notes) matches itself
        past = c.execute("SELECT title, script FROM videos WHERE kind=? AND script IS NOT NULL AND idea_id IS NOT ?"
                         " ORDER BY id DESC LIMIT 40", (kind, idea["id"] if idea else None)).fetchall()
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
    if isinstance(script.get("scenes"), list):  # a scene with no narration (a writer slip) is dropped
        script["scenes"] = [s for s in script["scenes"] if isinstance(s, dict) and isinstance(s.get("say"), str)
                            and s["say"].strip()]
    for s in script.get("scenes") or []:
        v = s.get("visual") if isinstance(s.get("visual"), dict) else {}
        for key, lim in (("text", 90), ("heading", 44), ("sub", 64), ("label", 54)):  # on-screen text that won't fit
            while isinstance(v.get(key), str) and len(v[key]) > lim and " " in v[key]:
                v[key] = v[key].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"
        # "Chapter: The suction secret. To understand..." -> chapter field + the spoken part
        m = re.match(r"\W*chapter\s*\d*\s*[:\-]\s*(.{2,40}?)[.!?](?=\s|$)\s*(.*)", s.get("say", ""), re.I | re.S)
        if m:
            s.setdefault("chapter", m.group(1).strip()[:30])
            s["say"] = m.group(2).strip() or s["say"]
        v = s.get("visual") or {}
        m = re.match(r"\W*chapter\s*\d*\s*[:\-]\s*(.{2,40})", str(v.get("text", "")), re.I)
        if v.get("type") == "title" and m:
            s.setdefault("chapter", m.group(1).strip()[:30])
            v["text"] = m.group(1).strip()
        if s.get("chapter") is True or s.get("chapter") == "":
            s.pop("chapter")
    # the hook's first line is short: a long scene 1 splits after its first sentence (or two, if still short)
    first = (script.get("scenes") or [{}])[0]
    sentences = re.split(r"(?<=[.!?])\s+", first.get("say", "").strip())
    if len(first.get("say", "").split()) > 14 and len(sentences) > 1:
        k = 1
        while k + 1 < len(sentences) and len(" ".join(sentences[:k + 1]).split()) <= 14:
            k += 1
        if len(" ".join(sentences[:k]).split()) <= 14:
            first["say"] = " ".join(sentences[:k])
            script["scenes"].insert(1, {"say": " ".join(sentences[k:]), "mood": first.get("mood", "talk"),
                                        "visual": {"type": "keep"}})
    # a scene over 40 words is split at the sentence break nearest its middle; the visual carries on
    scenes = []
    for s in script.get("scenes") or []:
        sentences = re.split(r"(?<=[.!?])\s+", s.get("say", "").strip())
        if len(s.get("say", "").split()) > 40 and len(sentences) > 1:
            half = len(s["say"].split()) / 2
            counts = [len(" ".join(sentences[:k]).split()) for k in range(1, len(sentences))]
            k = min(range(len(counts)), key=lambda j: abs(counts[j] - half)) + 1
            first = {**s, "say": " ".join(sentences[:k])}
            rest = {"say": " ".join(sentences[k:]), "mood": "talk", "visual": {"type": "keep"}}
            scenes += [first, rest]
        else:
            scenes.append(s)
    if scenes:
        script["scenes"] = scenes
    # a 'keep' that would hold one visual too long becomes a big line of its own words instead
    run, limit = 0, 36  # Shorts' limit; longs allow 40
    for s in scenes:
        v = s.get("visual") or {}
        n = len(s.get("say", "").split())
        if v.get("type") != "keep":
            run = 0
            limit = 36 + (14 if len(visuals.elements(visuals.normalize(v))[0]) >= 3 else 0)
        elif run + n > limit:
            line = min(re.split(r"(?<=[.!?])\s+", s["say"].strip()), key=len)
            while len(line) > 66:
                line = line.rsplit(" ", 1)[0].rstrip(",;:") + "…"
            s["visual"] = {"type": "bigtext", "text": line}
            run = 0
        run += n
    # point each term at the scene that really explains it (writers often number it off by a few)
    for t in script.get("terms") or []:
        if not isinstance(t, dict) or not t.get("term"):
            continue
        word = re.sub(r"s$", "", str(t["term"]).lower().strip())
        said = [i for i, s in enumerate(scenes, 1) if re.search(rf"\b{re.escape(word)}s?\b", s.get("say", "").lower())]
        if said:
            first = said[0]
            near = [i for i in range(first, min(_explain_by(first, scenes[first - 1].get("say", "")), len(scenes)) + 1)
                    if _spoken(t.get("plain", ""), scenes[i - 1].get("say", ""))]
            if near:
                t["scene"] = near[0]
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
                           f"transcript:\n{v['transcript'][:5000]}" for v in top[:3])
    openings = "\n\n".join(f"OPENING MINUTE of '{v['title']}' ({v['views']:,} views):\n{v['opening'][:1500]}"
                           for v in top if v.get("opening"))
    if ideas.is_debate(idea):
        transcript = ""
        web, sources = ideas.debate_research(idea["topic"], idea["angle"] or "")
        db.set_kv(f"sources:{idea['id']}", sources)  # the video's "Sources" list in the description
        story = ""
        if idea["source"] == "debate-news":
            story = f"The news story that started it: {idea['source_title']}\n{idea['source_text'] or ''}\n\n"
        material = (f"Topic: {idea['topic']}\n\n{story}{openings}\n\nWeb sources:\n{web[:26000]}\n\n{popular}")
        system = DEBATE_RESEARCH_SYSTEM
    elif ideas.is_how(idea):
        transcript = ""
        material = (f"Topic: {idea['topic']}\n\n{openings}\n\nWeb sources:\n{ideas.web_research(idea['topic'])[:20000]}"
                    f"\n\n{popular}")
        system = HOW_RESEARCH_SYSTEM
    elif tool:
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
                    f"\n\n{pages[:8000]}\n\n{openings}\n\n{popular}")
        system = RESEARCH_SYSTEM
    if top:  # the copy check (gates) compares the script against these too
        with db.conn() as c:
            c.execute("UPDATE ideas SET transcript=? WHERE id=?",
                      ((transcript or "") + "\n\n" + " ".join(v["transcript"] for v in top), idea["id"]))
    out = llm.ask_json(system, material[:45000] + f"\n\nTopic for our video: {idea['topic']}", "research")
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
    if out.get("hook_blueprint"):
        notes += ("\nHook blueprint: how the most-watched video on this topic opens. Open OUR video with these "
                  "same beats, in this order and at about this timing (2.5 spoken words per second), in your own "
                  "words. Copy the JOB of each beat, never its content: Thoma is a narrator explaining footage and "
                  "facts, he was never at the event, never filmed anything and never speaks as the people in the "
                  "source videos (no 'we shot this', 'I was there'):\n" + "\n".join(f"- {b}" for b in out["hook_blueprint"]))
        if out.get("hook_example"):
            notes += f"\nA first try at our opening (improve it, keep the beats): {out['hook_example']}"
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
    if ideas.is_how(idea):
        return "teaser"
    if ideas.is_debate(idea) and _long_video(idea):
        return "debate-teaser"
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


PATCH_RULES = """Reply with a PATCH, not the whole script. JSON only:
{"edits": [{"scene": <n of the scene to change>, "new": [<0 or more full scene objects that replace it>]}, ...],
 "terms": [<the full corrected terms list, only if it changes>],
 "<any other top-level field that changes, e.g. title>": "..."}
Every scene you don't list stays exactly as it is. "new" with one scene rewrites it; with two or more it splits or
adds scenes there; empty deletes it. To add words, expand thin scenes or add new ones where an idea needs more
explaining; to cut, shorten or merge wordy ones. Count your word changes against the budget."""


def apply_patch(script: dict, patch: dict) -> dict:
    """Apply a writer's patch ({"edits": [{"scene": n, "new": [...]}], ...}); a full script is taken as is."""
    if "edits" not in patch and isinstance(patch.get("scenes"), list):
        return {**script, **patch}  # a whole script back: keep any top-level field it left out
    new, scenes = dict(script), list(script["scenes"])
    edits = [e for e in patch.get("edits") or [] if isinstance(e, dict) and str(e.get("scene", "")).isdigit()]
    for e in sorted(edits, key=lambda e: -int(e["scene"])):  # from the end, so numbers stay valid
        i = int(e["scene"]) - 1
        if 0 <= i < len(scenes):
            scenes[i:i + 1] = [{k: v for k, v in x.items() if k != "n"} for x in e.get("new") or []
                               if isinstance(x, dict) and x.get("say")]
    new["scenes"] = scenes
    new.update({k: v for k, v in patch.items() if k not in ("edits", "scenes")})
    return new


def _spec(kind: str, fmt: str | None) -> str:
    if kind == "long":
        return {"how-it-works": HOW_LONG, "debate": DEBATE_LONG, "tool-tutorial": FORMATS["long"]["spec"] + "\n" + TOOL_LONG}.get(
            fmt, FORMATS["long"]["spec"])
    return FORMATS["short"]["spec"] + ("\n" + SHORT_FORMATS[fmt] if fmt in SHORT_FORMATS else "")


def _long_video(idea):
    """The newest long video made from this idea (a teaser Short points to it)."""
    with db.conn() as c:
        r = c.execute("SELECT id, script FROM videos WHERE idea_id=? AND kind='long' AND script IS NOT NULL"
                      " AND status NOT IN ('failed','rejected') ORDER BY id DESC LIMIT 1", (idea["id"],)).fetchone()
    return {**json.loads(r["script"]), "id": r["id"]} if r else None


def revise(script: dict, kind: str, feedback: str, idea=None, times: list | None = None) -> dict:
    """The owner's '/fix 12 <what to change>': change only those scenes, keep the rest identical."""
    fmt = script.get("format")
    spec = _spec(kind, fmt)
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
            if script.get("related"):
                new["related"] = script["related"]
            return new
        log.info("revision %d failed gates: %s", attempt + 1, problems)
        prompt += "\n\nYour last version had these problems, fix them too:\n" + "\n".join(f"- {x}" for x in problems)
    raise ValueError("revision failed checks: " + "; ".join(problems))


def write(idea, kind: str, draft: dict | None = None, notes_to_fix: list[str] | None = None) -> dict:
    """Research, write, check and review a script. `draft` continues from an existing script, with
    `notes_to_fix` (e.g. a validator's notes) added to what the code checks find."""
    from datetime import date
    from . import ideas
    how = ideas.is_how(idea)
    if kind == "short":
        fmt = pick_short_format(idea)
    else:
        fmt = ("tool-tutorial" if ideas.is_tool(idea) else "how-it-works" if how else
               "debate" if ideas.is_debate(idea) else "tutorial")
    spec = _spec(kind, fmt)
    spec += f"\nToday's date: {date.today():%B %Y}."
    system = f"{CHARACTER}\n\n# Format\n{spec}\n\n{visuals.SPEC}\n\n{SCRIPT_SHAPE}{example(kind)}"
    lo, hi = FORMATS[kind]["words"]
    brief = (f"Topic: {idea['topic']}\nWord budget: aim for {FORMATS[kind]['target']} spoken words in total "
             f"(hard limits {lo}-{hi}). Count them before replying.\n")
    if idea["angle"] and fmt == "debate":
        brief += f"Sharpest real moment to open with (if the research notes confirm it): {idea['angle']}\n"
    elif idea["angle"] and how:
        brief += (f"Running example (follow it through every step, on screen too): {idea['angle']}\n")
    elif idea["angle"]:
        brief += f"Suggested analogy (use it or find a better one): {idea['angle']}\n"
    full = _long_video(idea) if fmt in ("teaser", "debate-teaser") else None
    if full:
        lines = [s["say"] for s in full["scenes"]]
        chapters = [s["chapter"] for s in full["scenes"] if s.get("chapter")]
        brief += (f"\nOur full video on this topic: '{full['title']}' (chapters: {'; '.join(chapters)}). Its "
                  f"opening line was: '{lines[0]}' (don't reuse it). Keep every fact consistent with it.\n")
    if idea["source_title"]:
        brief += (f"Inspired by the video '{idea['source_title']}'. Use it only to know what people are "
                  "curious about; never reuse its wording or examples.\n")
    notes = research(idea)
    with db.conn() as c:  # research may have stored more source text for the copy check
        idea = c.execute("SELECT * FROM ideas WHERE id=?", (idea["id"],)).fetchone()
    if notes:
        brief += f"\nResearch notes (facts to rely on; explain them your own way):\n{notes}\n"
    with db.conn() as c:
        earlier = [r[0] for r in c.execute("SELECT title FROM videos WHERE idea_id=? AND title != '' AND kind=?",
                                           (idea["id"], kind))]
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
    if draft is not None:
        script = repair(draft)
        problems = list(notes_to_fix or []) + gates(script, kind, idea)
    deadline = 6  # drafts allowed; a review's fixes always get 2 more
    for attempt in range(9):
        if attempt >= deadline:
            break
        if attempt or draft is None or problems:  # a clean draft goes straight to the review
            prompt = brief
            if script is not None:  # fixes come back as a patch: untouched scenes stay word for word
                n = words(script)
                budget = (f"add about {lo - n + 40} words" if n < lo else f"cut about {n - hi + 40} words" if n > hi
                          else "keep the total about the same (add as many words as you cut)")
                numbered = {**{k: v for k, v in script.items() if k not in ("scenes", "writer")},
                            "scenes": [{"n": i, **s} for i, s in enumerate(script["scenes"], 1)]}
                prompt += (f"\nYour previous draft ({n} spoken words, scenes numbered by \"n\"):\n"
                           f"{json.dumps(numbered, ensure_ascii=False)}\n\nFix ALL of these problems:\n"
                           + "\n".join(f"- {x}" for x in problems)
                           + f"\n\nWord budget for this edit: {budget} (the total must end up between {lo} and {hi}).\n"
                           + PATCH_RULES)
            reply = llm.ask_json(system, prompt, f"write-{kind}")
            script = repair(apply_patch(script, reply) if script is not None else reply)
            script["writer"] = llm.last_provider
            problems = gates(script, kind, idea)
            if problems:
                log.info("draft %d failed gates: %s", attempt + 1, problems)
                drafts = Path(__file__).parent.parent / "out/drafts"  # kept for checking what the writer does wrong
                drafts.mkdir(parents=True, exist_ok=True)
                (drafts / f"{idea['id']}-{kind}-{script['writer']}-{attempt + 1}.json").write_text(
                    json.dumps({"problems": problems, "script": script}, indent=1, ensure_ascii=False))
                continue
        script["format"] = fmt
        if full:
            script["related"] = {"video": full["id"], "title": full["title"]}
        if db.get_kv(f"sources:{idea['id']}"):
            script["sources"] = db.get_kv(f"sources:{idea['id']}")
        if reviewed:
            return script
        review = llm.ask_json(REVIEW_SYSTEM, f"Research notes (the only source of facts):\n{notes}\n\nScript:\n"
                              + json.dumps(script, ensure_ascii=False), "review")
        log_review(script, kind, idea["topic"], review)
        reviewed = True
        deadline = max(deadline, attempt + 4)
        problems = review.get("problems", []) if not review.get("ok", True) else []
        if not problems:
            return script
        log.info("review asked for fixes: %s (student heard: %s)", problems, review.get("student_summary", ""))
    raise ValueError("script failed checks: " + "; ".join(problems))
