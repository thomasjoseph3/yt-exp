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
  {"type":"keep"}       (same visual stays; use when the line continues the previous graphic)
  {"type":"takeaway","text":"<=90 chars, with *highlight*"}   (last scene only)

Make it look like a proper animated tech explainer: mostly diagrams, steps, compares and
analogies; a title or bigtext only to open or to land a punchline; code only when it helps.
Change the visual every 1-3 lines. Node labels should be words Thoma actually says, so they
appear on screen as he says them."""

STOP = set("the a an and or of to in on for is are it its this that with as by be at from your you".split())


@lru_cache
def icon_names() -> list[str]:
    return sorted(p.stem for p in ICON_DIR.glob("*.svg"))


@lru_cache
def icon_svg(name: str) -> str:
    return (ICON_DIR / f"{name}.svg").read_text()


def fix_icon(name) -> str:
    name = str(name or "").strip().lower().replace(" ", "-").replace("_", "-")
    names = icon_names()
    if name in names:
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
    if v.get("type") == "steps":
        v["items"] = [({"text": x} if isinstance(x, str) else {**x, "icon": fix_icon(x["icon"]) if x.get("icon") else None})
                      for x in v.get("items") or []]
    return v


def icons_used(visuals) -> set[str]:
    found = {"sparkles", "bell", "box", "check", "x", "cpu", "coffee"}
    for v in visuals:
        for key in ("icon",):
            if v.get(key):
                found.add(v[key])
        for n in v.get("nodes", []) + v.get("items", []):
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
        t = min(max(t, floor), end - 0.4)
        times.append(t)
        floor = t + 0.3
    return times
