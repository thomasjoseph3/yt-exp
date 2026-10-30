"""The visual vocabulary: what the LLM may ask for, and how each visual lines up with narration.

Every visual type here has a builder of the same name in assets/web/stage.js.
To add a new type: write the builder there, then add it to SPEC and elements() here.
"""
import difflib
import re
from functools import lru_cache

from .config import ASSETS

ICON_DIR = ASSETS / "web/vendor/lucide/icons"

# A short, tech-friendly list the LLM picks from (any Lucide name also works).
ICONS = """brain cpu database server cloud globe lock key shield shield-check user users bot message-square
search file-text files book-open library code terminal git-branch github layers box boxes package network
share-2 workflow zap rocket gauge timer clock hard-drive memory-stick microchip wifi router smartphone laptop
monitor image video mic camera eye lightbulb sparkles wand-sparkles target trophy chart-line chart-bar
trending-up dollar-sign coins shopping-cart mail bell calendar map-pin car bus truck house building factory
store coffee utensils chef-hat pizza book graduation-cap school pencil clipboard-list list-checks check x
circle-alert triangle-alert bug wrench settings filter shuffle repeat refresh-cw arrow-right link plug puzzle
scale binary hash table fingerprint scan-face user-check heart thumbs-up smile hand flame droplet compass
flag gift backpack briefcase newspaper megaphone gamepad-2 waypoints route split merge container cog
activity scroll-text quote languages""".split()

SPEC = """Each scene has a "visual": the animated graphic on screen while Thoma says that line.
Keep on-screen text SHORT (it is a picture, not a transcript). Wrap 1-3 words in *asterisks* to
highlight them. "icon" is a name from this list: """ + ", ".join(ICONS) + """

Visual types:
  {"type":"title","text":"<=45 chars","sub":"optional <=60","icon":"..."}            opening / section title
  {"type":"bigtext","text":"<=70 chars punchy statement with *highlight*","sub":"optional"}
  {"type":"stat","value":"e.g. 70% or 1,000,000 or 3x","label":"<=50 chars what it means"}
  {"type":"diagram","heading":"optional <=40","layout":"row|stack|grid|hub|cycle",
     "nodes":[{"id":"a","label":"<=18 chars","icon":"...","sub":"optional <=28"}, ...2-6 nodes],
     "edges":[{"from":"a","to":"b","label":"optional <=14"}],      (omit edges for an automatic chain)
     "highlight":"optional node id to pulse at the end"}
     row = left-to-right pipeline, stack = top-to-bottom, hub = first node in the centre,
     cycle = loop, grid = a set of related things (no arrows)
  {"type":"steps","heading":"<=40","items":[{"text":"<=40 chars","icon":"optional"}, ...2-5]}
  {"type":"compare","heading":"<=40","left":{"label":"<=20","icon":"...","items":["<=30", ...<=4]},"right":{same}}
  {"type":"analogy","left":{"label":"everyday thing <=26","icon":"..."},"right":{"label":"the tech <=26","icon":"..."},"note":"optional <=60"}
  {"type":"code","heading":"optional","lang":"python|javascript|bash|sql|json","lines":["<=48 chars", ...<=10],"output":["optional terminal output lines"]}
  {"type":"tokens","text":"<=60 chars sentence","tokens":["optional","pieces"],"label":"optional word Thoma says when it splits, default tokens"}
     the sentence splits into coloured token chips with their ID numbers (how an LLM reads text)
  {"type":"predict","prompt":"<=70 chars unfinished sentence","options":[{"word":"<=14","p":62}, ...2-5],"pick":0,"label":"optional <=60"}
     next-word prediction: probability bars fill up, then the picked word drops into the prompt
  {"type":"vectors","heading":"optional","groups":[{"label":"<=14","items":["<=12", ...2-5]}, ...1-4],"query":"optional <=14","near":0}
     embedding space: words as dots, similar meanings cluster; the query lands next to group "near"
  {"type":"network","heading":"optional","layers":[3,5,5,2],"input":"<=18","middle":"<=22","output":"<=18"}
     a neural network: input -> hidden layers -> output, with signals flowing through
  {"type":"chat","bot":"optional name","messages":[{"from":"user|bot","text":"<=80 chars","flag":"wrong|right|none","note":"optional stamp <=16"}, ...1-4]}
     a chat window; bot replies type out; flag "wrong" stamps a hallucination, "right" a sourced answer
  How-it-works visuals (machines, vehicles, devices, real technology):
  {"type":"parts","object":"<=24 the thing","icon":"car|rocket|plane|satellite|bot|smartphone|brain|...","heading":"optional <=40",
     "parts":[{"label":"<=18","sub":"optional <=26","icon":"..."}, ...2-6]}
     the machine big in the middle; a callout line draws out to each part as Thoma names it
  {"type":"scan","mode":"radar|lidar|camera|signal","icon":"car-top (a car seen from above) or any icon","center":"<=16",
     "targets":[{"label":"<=14","icon":"...","note":"optional <=12, e.g. 12 m"}, ...1-5]}
     top-down sensor view: a sweeping beam (radar/lidar point cloud), a forward camera cone, or radio waves;
     each target gets a detection box and tag when Thoma names it. For anything that senses or signals
  {"type":"zoom","levels":[{"label":"<=22","icon":"...","sub":"optional <=40"}, ...2-4]}
     dive inside: car -> computer -> chip; each level grows out of the one before it
  {"type":"layers","heading":"optional","items":[{"label":"<=20","sub":"optional <=30","icon":"optional"}, ...2-5]}
     an exploded stack of slabs, top to bottom (battery cell layers, a screen, a wing section)
  {"type":"path","from":"<=14","to":"<=14","stops":["<=14", ...0-3],"icon":"car|plane|rocket|...","note":"optional <=60"}
     a route on a map; the vehicle drives it as Thoma names each point (journeys, signal paths, flight paths)
  {"type":"timeline","heading":"optional","events":[{"when":"<=10, e.g. 2008","label":"<=26"}, ...2-6],"now":optional index}
     a line with a glowing marker that travels to each event as it is said (history, what happens in order)
  {"type":"bars","heading":"<=40","unit":"optional, e.g. km","items":[{"label":"<=16","value":123,"note":"optional"}, ...2-6],"highlight":optional index}
     real numbers compared: bars grow and the values count up. Only numbers from the research notes
  Real photos and the news (photos come from free photo libraries, checked and credited automatically):
  {"type":"photo","query":"2-5 search words naming the REAL thing","show":"what the photo must show, <=80 chars",
     "caption":"optional <=60 chars with *highlight*","tag":"optional <=14, e.g. THE CLAIM, 2024, THE CEO"}
     a full-screen real photograph with a slow pan. query names something photographed often: a famous product
     ('Nvidia H100', 'Tesla Cybertruck'), a public figure ('Jensen Huang'), a place or building ('Microsoft
     headquarters'), or a kind of scene ('data center server racks', 'students in a classroom'). Never an idea
     ('AI bubble', 'future of work'): no photo of that exists, use an animated visual instead
  {"type":"photos","heading":"optional <=40","items":[{"query":"...","show":"...","label":"<=24"}, ...2-3]}
     2-3 real photos side by side, revealed as Thoma names each (the two sides of a fight, products compared)
  {"type":"headlines","heading":"optional <=40","items":[{"source":"outlet, e.g. Reuters","date":"e.g. Oct 2026",
     "text":"<=80 chars: what the story reported, in your own words"}, ...1-3]}
     news cards pop in as Thoma names each story. Only stories in the research notes, with their real outlet and date
  {"type":"quote","text":"<=140 chars","who":"<=30 name","when":"optional <=24, e.g. 'on CNBC, Oct 2026'",
     "query":"optional photo search for that person, e.g. 'Sam Altman'"}
     a real quote, word for word as it appears in the research notes. Never invent, merge or tidy a quote
  {"type":"keep"}       (same visual stays; use when the line continues the previous graphic)
  {"type":"takeaway","text":"<=90 chars, with *highlight*"}   (last scene only)

Make it look like a proper animated tech explainer (think Fireship pace, ByteMonk diagrams):
SHOW the mechanism, don't just name it. For AI topics use the concept visuals: tokens for how a model
reads text, predict for next-word guessing, vectors for embeddings/semantic search/RAG retrieval,
network for neural nets/training, chat for what a chatbot does (and hallucinations). Use at least
one concept visual when the topic is about how AI works. For machines and real technology, use the how-it-works
visuals: parts to show what it is made of, scan for sensing, zoom to go inside, layers for stacked parts, path
for journeys, timeline for history or order of events, bars for real numbers. Real photos make it feel real:
whenever Thoma names a real product, person, company, place or event, show it with a photo (long videos: at
least 3, one of them in the first 30 seconds), news stories with headlines, and what someone said with a quote;
then go back to animations to explain how it works. Otherwise mostly diagrams, steps, compares and
analogies; a title or bigtext to open or to land a punchline; a stat for a striking number; code only when it helps. Change the visual every 1-2
sentences (every 4-10 seconds) so the screen never sits still. Node labels and list items should
be words Thoma actually says, so they appear on screen as he says them."""

MAX_GAP = 2.5  # seconds: a new element appears at least this often
STOP = set("the a an and or of to in on for is are it its this that with as by be at from your you".split())


@lru_cache
def icon_names() -> list[str]:
    return sorted(p.stem for p in ICON_DIR.glob("*.svg"))


@lru_cache
def icon_svg(name: str) -> str:
    f = ICON_DIR / f"{name}.svg"
    return f.read_text() if f.exists() else ""  # e.g. car-top, which stage.js draws itself


def fix_icon(name) -> str:
    name = str(name or "").strip().lower().replace(" ", "-").replace("_", "-")
    names = icon_names()
    if name in names or name == "car-top":  # car-top: drawn by stage.js (a car seen from above)
        return name
    close = difflib.get_close_matches(name, names, n=1, cutoff=0.6)
    return close[0] if close else "sparkles"


def normalize(v: dict) -> dict:
    """Make LLM output safe to render: known icons, list shapes, string labels."""
    v = dict(v or {"type": "keep"})
    if "icon" in v:
        v["icon"] = fix_icon(v["icon"])
    if v.get("type") == "diagram":
        nodes = []
        for i, n in enumerate(v.get("nodes") or []):
            n = {"label": n} if isinstance(n, str) else dict(n)
            n.setdefault("id", str(i))
            n["id"] = str(n["id"])
            n["icon"] = fix_icon(n.get("icon", "box"))
            nodes.append(n)
        v["nodes"] = nodes[:6]
        v["edges"] = [{**e, "from": str(e.get("from")), "to": str(e.get("to"))} for e in v.get("edges") or []
                      if isinstance(e, dict)]
        if v.get("highlight") is not None:
            v["highlight"] = str(v["highlight"])
    for side in ("left", "right"):
        if isinstance(v.get(side), dict) and "icon" in v[side]:
            v[side]["icon"] = fix_icon(v[side]["icon"])
        elif isinstance(v.get(side), str):
            v[side] = {"label": v[side]}
    if v.get("type") == "predict":
        opts = [{"word": o} if isinstance(o, str) else dict(o) for o in v.get("options") or []][:5]
        for o in opts:
            o["word"] = str(o.get("word", ""))
            try:
                o["p"] = float(str(o.get("p", 0)).rstrip("%"))
            except ValueError:
                o["p"] = 0.0
        v["options"] = opts
        try:
            v["pick"] = min(max(int(v.get("pick", 0)), 0), max(len(opts) - 1, 0))
        except (TypeError, ValueError):
            v["pick"] = 0
    if v.get("type") == "vectors":
        v["groups"] = [({"label": g, "items": []} if isinstance(g, str) else
                        {"label": str(g.get("label", "")), "items": [str(x) for x in g.get("items") or []][:5]})
                       for g in v.get("groups") or []][:4]
        try:
            v["near"] = min(max(int(v.get("near", 0)), 0), max(len(v["groups"]) - 1, 0))
        except (TypeError, ValueError):
            v["near"] = 0
    if v.get("type") == "chat":
        v["messages"] = [({"from": "user", "text": m} if isinstance(m, str) else dict(m)) for m in v.get("messages") or []][:4]
    for key, cap in (("parts", 6), ("targets", 5), ("levels", 4), ("events", 6)):
        if key in v:
            v[key] = [({"label": x} if isinstance(x, str) else
                       {**x, "label": str(x.get("label", "")), **({"icon": fix_icon(x["icon"])} if x.get("icon") else {})})
                      for x in v.get(key) or []][:cap]
    if v.get("type") == "bars":
        items = []
        for x in v.get("items") or []:
            x = {"label": x} if isinstance(x, str) else dict(x)
            try:
                x["value"] = float(re.sub(r"[^0-9.\-]", "", str(x.get("value", 0))) or 0)
            except ValueError:
                x["value"] = 0.0
            if x["value"] == int(x["value"]):
                x["value"] = int(x["value"])
            items.append(x)
        v["items"] = items[:6]
    if v.get("type") == "layers":
        v["items"] = [({"label": x} if isinstance(x, str) else
                       {**x, "label": str(x.get("label", "")), **({"icon": fix_icon(x["icon"])} if x.get("icon") else {})})
                      for x in v.get("items") or []][:5]
    if v.get("type") == "path":
        v["stops"] = [str(x) for x in v.get("stops") or []][:3]
    if v.get("type") == "photos":
        v["items"] = [({"query": x, "label": x} if isinstance(x, str) else dict(x)) for x in v.get("items") or []][:3]
    if v.get("type") == "headlines":
        v["items"] = [({"text": x} if isinstance(x, str) else dict(x)) for x in v.get("items") or []][:3]
    if v.get("type") == "steps":
        v["items"] = [({"text": x} if isinstance(x, str) else {**x, "icon": fix_icon(x["icon"]) if x.get("icon") else None})
                      for x in v.get("items") or []]
    return v


def icons_used(visuals) -> set[str]:
    found = {"sparkles", "bell", "box", "check", "x", "cpu", "coffee", "bot", "circle-dot", "circle-alert", "car", "image"}
    for v in visuals:
        for key in ("icon",):
            if v.get(key):
                found.add(v[key])
        for n in (v.get("nodes", []) + v.get("items", []) + v.get("parts", []) + v.get("targets", [])
                  + v.get("levels", []) + v.get("events", [])):
            if isinstance(n, dict) and n.get("icon"):
                found.add(n["icon"])
        for side in ("left", "right"):
            if isinstance(v.get(side), dict) and v[side].get("icon"):
                found.add(v[side]["icon"])
    return found


def elements(v: dict) -> tuple[list[str], bool]:
    """Labels in reveal order (must match stage.js), and whether to space them evenly."""
    t = v.get("type")
    if t == "title":
        return [v.get("text", ""), v.get("text", ""), v.get("sub", "")], False
    if t == "bigtext":
        return [v.get("text", ""), v.get("sub", "")], False
    if t == "stat":
        return [v.get("value", ""), v.get("label", "")], False
    if t == "diagram":
        return [n["label"] for n in v.get("nodes", [])], False
    if t == "steps":
        return [i["text"] for i in v.get("items", [])], False
    if t == "compare":
        return [v.get("left", {}).get("label", ""), v.get("right", {}).get("label", "")], False
    if t == "analogy":
        return [v.get("left", {}).get("label", ""), v.get("right", {}).get("label", ""), v.get("note", "")], False
    if t == "code":
        return list(v.get("lines", [])) + (["output"] if v.get("output") else []), True
    if t == "takeaway":
        return [v.get("text", "")], False
    if t == "tokens":
        return [v.get("text", ""), v.get("label") or "tokens"], False
    if t == "predict":
        opts = [o.get("word", "") for o in v.get("options", [])]
        return [v.get("prompt", "")] + opts + [opts[v.get("pick", 0)] if opts else ""], False
    if t == "vectors":
        return [g.get("label", "") for g in v.get("groups", [])] + ([v["query"]] if v.get("query") else []), False
    if t == "network":
        return [v.get("input") or "input", v.get("middle") or "layers", v.get("output") or "output"], False
    if t == "chat":
        return [m.get("text", "") for m in v.get("messages", [])], False
    if t == "parts":
        return [v.get("object") or ""] + [p["label"] for p in v.get("parts", [])], False
    if t == "scan":
        return [v.get("center") or ""] + [x["label"] for x in v.get("targets", [])], False
    if t in ("zoom",):
        return [x["label"] for x in v.get("levels", [])], False
    if t == "timeline":
        return [f"{e.get('when', '')} {e['label']}" for e in v.get("events", [])], False
    if t in ("layers", "bars"):
        return [x["label"] for x in v.get("items", [])], False
    if t == "photo":
        return [v.get("caption") or v.get("tag") or ""], False
    if t == "photos":
        return [x.get("label") or x.get("query", "") for x in v.get("items", [])], False
    if t == "headlines":
        return [x.get("text", "") for x in v.get("items", [])], False
    if t == "quote":
        return [v.get("text", ""), v.get("who", "")], False
    if t == "path":
        return [x for x in [v.get("from"), *v.get("stops", []), v.get("to")] if x], False
    return [], True


def _keywords(label: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", label.lower()) if len(w) > 2 and w not in STOP]


def reveal_times(v: dict, words: list[tuple[str, float, float]], start: float, end: float) -> list[float]:
    """When each element appears: when Thoma first says one of its words, else spread evenly."""
    labels, even = elements(v)
    n = len(labels)
    if not n:
        return []
    window = min(0.55 * (end - start), 0.9 * n)
    evenly = [start + 0.2 + window * k / n for k in range(n)]
    if even:
        return evenly
    spoken = [(re.sub(r"[^a-z0-9]", "", w.lower()), s) for w, s, _ in words]
    times, floor = [], start + 0.15
    for k, label in enumerate(labels):
        hit = None
        for kw in _keywords(label):
            hit = next((s for w, s in spoken if s >= floor - 0.05 and (w == kw or (len(kw) > 4 and w.startswith(kw[:5])))), None)
            if hit is not None:
                break
        t = hit - 0.25 if hit is not None else evenly[k]
        t = min(t, start + 0.8 + k * MAX_GAP)  # never leave the screen waiting long for a late word
        t = min(max(t, floor), end - 0.4)
        times.append(t)
        floor = t + 0.3
    return times
