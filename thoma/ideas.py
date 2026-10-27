"""Idea queue: mine source channels for topics, plus an evergreen backlog.

Source videos are used only as topic signals (title + description). Thoma's
scripts are written from scratch, and writer.py blocks copied phrasing.
"""
import difflib
import logging
import re
import time
import xml.etree.ElementTree as ET

import httpx

from . import db, llm
from .config import ASSETS, cfg, secret

log = logging.getLogger("thoma.ideas")
NS = {"a": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/",
      "yt": "http://www.youtube.com/xml/schemas/2015"}

TRIAGE_SYSTEM = """You plan topics for "Thoma Explains", an EDUCATION channel about AI for complete
beginners: how AI works, new AI models and updates, new AI technology, AI security issues (prompt
injection, deepfakes, voice-clone scams, data leaks, jailbreaks) and AI news, always explained so a
10th-standard student understands what happened and the concept behind it. You get titles and
descriptions of videos from other tech channels. For each, decide if its subject can become an
original beginner explainer of ONE clear concept (e.g. a release about a new database -> "What is a
vector database?"; a security incident -> "How do AI voice scams work?"). fit=false for podcasts,
round-ups that cover many things, interviews, opinion pieces, product ads, and memes.
ai=true if the topic is about AI (or a security issue involving AI); other tech is allowed but less
wanted. news=true if it is about something that just happened and gets stale within a week.
Reply as JSON:
{"items":[{"ref":"<ref>","fit":true,"ai":true,"news":false,"topic":"short plain topic, e.g. What is RAG?",
"angle":"one everyday analogy Thoma could use"}]}"""


TOOLS_TRIAGE = """You pick AI tools for "Thoma Explains", a channel for beginners: students, office
workers, small business owners, creators. You get new AI tools (name + tagline). fit=true only for
tools a normal person could actually use to save time or do something new (writing, studying,
slides, video, images, meetings, research, automation, simple coding). fit=false for tools only
for developers' infrastructure, crypto, adult, gambling, vague "AI platform" pitches, and clones
of well-known tools with nothing new. Reply as JSON:
{"items":[{"ref":"<ref>","fit":true,"topic":"<Tool name>: what it does, e.g. 'Gamma: AI that makes slide decks'",
"angle":"the everyday problem it solves"}]}"""

TOOL_SOURCES = ("AI tools", "tool-evergreen")


def is_tool(idea) -> bool:
    return idea is not None and idea["source"] in TOOL_SOURCES


def tool_site(idea) -> str:
    for line in (idea["source_text"] or "").splitlines():
        if line.startswith("website: "):
            return line[9:].strip()
    return ""


def _tools_feed(url: str) -> list[dict]:
    """New AI tools from Product Hunt's AI feed (Atom)."""
    import html
    import re
    r = httpx.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 ThomaStudio"})
    r.raise_for_status()
    items = []
    for e in ET.fromstring(r.text).findall("a:entry", NS):
        content = html.unescape(e.findtext("a:content", default="", namespaces=NS))
        tagline = re.sub(r"<[^>]+>", " ", content.split("Discussion")[0])
        link = re.search(r'href="(https://www\.producthunt\.com/r/p/[^"]+)"', content)
        items.append({
            "ref": "ph:" + e.findtext("a:id", namespaces=NS).rsplit("/", 1)[-1],
            "title": e.findtext("a:title", namespaces=NS),
            "text": " ".join(tagline.split()) + (f"\nwebsite: {link.group(1)}" if link else ""),
        })
    return items


def _channel_page(channel_id: str, per_tab: int = 8) -> list[dict]:
    """Latest videos and Shorts read from the channel's public pages (when the feed is down)."""
    items, ua = [], {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", "Accept-Language": "en"}
    for tab in ("videos", "shorts"):
        page = httpx.get(f"https://www.youtube.com/channel/{channel_id}/{tab}", headers=ua, timeout=30,
                         follow_redirects=True).text
        for vid in list(dict.fromkeys(re.findall(r'"videoId":"([\w-]{11})"', page)))[:per_tab]:
            o = httpx.get("https://www.youtube.com/oembed", params={"url": f"https://www.youtube.com/watch?v={vid}",
                          "format": "json"}, timeout=20)
            if o.status_code == 200:
                items.append({"ref": vid, "title": o.json()["title"], "text": ""})
    return items


def _rss(channel_id: str) -> list[dict]:
    """The channel's feed; YouTube's feeds fail now and then, so fall back to the channel pages."""
    r = None
    for _ in range(3):
        r = httpx.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", timeout=30)
        if r.status_code == 200:
            break
        time.sleep(3)
    if r.status_code != 200:
        log.info("feed for %s returned %s, reading the channel page instead", channel_id, r.status_code)
        return _channel_page(channel_id)
    items = []
    for e in ET.fromstring(r.text).findall("a:entry", NS):
        items.append({
            "ref": e.findtext("yt:videoId", namespaces=NS),
            "title": e.findtext("a:title", namespaces=NS),
            "text": e.findtext("media:group/media:description", default="", namespaces=NS),
        })
    return items


def _backfill(channel_id: str, pages: int) -> list[dict]:
    """Older uploads through the YouTube Data API (needs YOUTUBE_API_KEY)."""
    key, items, token = secret("YOUTUBE_API_KEY"), [], None
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY is not set in .env")
    for _ in range(pages):
        params = {"part": "snippet", "playlistId": "UU" + channel_id[2:], "maxResults": 50, "key": key}
        if token:
            params["pageToken"] = token
        r = httpx.get("https://www.googleapis.com/youtube/v3/playlistItems", params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for it in data["items"]:
            s = it["snippet"]
            items.append({"ref": s["resourceId"]["videoId"], "title": s["title"], "text": s["description"]})
        token = data.get("nextPageToken")
        if not token:
            break
    return items


def _priority(verdict: dict, base: int) -> int:
    """AI topics first (the channel's focus), and fresh AI news before it goes stale; other tech last."""
    if "ai" not in verdict:  # e.g. the AI-tools triage, which doesn't classify
        return base
    if not verdict["ai"]:
        return max(base - 2, 0)
    return base + (2 if verdict.get("news") else 0)


def _store(source: str, items: list[dict], priority: int, system: str = TRIAGE_SYSTEM) -> int:
    with db.conn() as c:
        known = {r[0] for r in c.execute("SELECT source_ref FROM ideas")}
    fresh = [i for i in items if i["ref"] not in known]
    with db.conn() as c:
        topics = [r[0].lower() for r in c.execute("SELECT topic FROM ideas WHERE status='new'")]
    added = 0
    for chunk in (fresh[i:i + 15] for i in range(0, len(fresh), 15)):
        listing = "\n\n".join(f"ref: {i['ref']}\ntitle: {i['title']}\ndescription: {i['text'][:400]}" for i in chunk)
        verdicts = {v["ref"]: v for v in llm.ask_json(system, listing, "triage").get("items", [])}
        with db.conn() as c:
            for i in chunk:
                v = verdicts.get(i["ref"], {"fit": False})
                topic = v.get("topic", "").lower()
                if v.get("fit") and any(difflib.SequenceMatcher(None, topic, t).ratio() > 0.85 for t in topics):
                    v["fit"] = False  # same topic already queued from another channel
                topics.append(topic)
                c.execute(
                    "INSERT OR IGNORE INTO ideas (source, source_ref, source_title, source_text, topic, angle,"
                    " status, priority, created) VALUES (?,?,?,?,?,?,?,?,?)",
                    (source, i["ref"], i["title"], i["text"], v.get("topic", ""), v.get("angle", ""),
                     "new" if v.get("fit") else "rejected", _priority(v, priority), db.now()))
                added += bool(v.get("fit"))
    return added


def transcript(idea) -> str:
    """Fetch the source video's English transcript (YouTube sources only). Empty on failure."""
    if not idea["source_ref"] or idea["source"] == "evergreen":
        return ""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        fetched = YouTubeTranscriptApi().fetch(idea["source_ref"], languages=["en", "en-US", "en-GB"])
        text = " ".join(snippet.text for snippet in fetched)
    except Exception as e:
        log.info("no transcript for %s: %s", idea["source_ref"], str(e)[:120])
        text = ""
    with db.conn() as c:
        c.execute("UPDATE ideas SET transcript=? WHERE id=?", (text, idea["id"]))
    return text


def top_explainers(topic: str, n: int = 3) -> list[dict]:
    """The most-watched YouTube videos on a topic, with transcripts: how proven explainers teach it.
    Used to learn structure and what kind of example makes it click; never to copy (writer.gates)."""
    import json
    query = re.sub(r"https?://\S+", "", topic).strip() + " explained"
    try:
        page = httpx.get("https://www.youtube.com/results", params={"search_query": query}, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", "Accept-Language": "en"}).text
        data = json.loads(re.search(r"var ytInitialData = (\{.*?\});</script>", page).group(1))
    except Exception as e:
        log.info("search for top explainers failed: %s", e)
        return []
    found = []

    def walk(o):
        if isinstance(o, dict):
            v = o.get("videoRenderer")
            if v:
                views = re.sub(r"\D", "", (v.get("viewCountText") or {}).get("simpleText") or "") or "0"
                found.append({"ref": v["videoId"], "title": v["title"]["runs"][0]["text"], "views": int(views)})
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(data)
    out = []
    from youtube_transcript_api import YouTubeTranscriptApi
    for v in sorted(found[:12], key=lambda v: -v["views"]):
        try:
            fetched = YouTubeTranscriptApi().fetch(v["ref"], languages=["en", "en-US", "en-GB"])
        except Exception:
            continue
        v["transcript"] = " ".join(s.text for s in fetched)
        out.append(v)
        if len(out) == n:
            break
    log.info("top explainers for %r: %s", topic[:60], [f"{v['title']} ({v['views']:,} views)" for v in out])
    return out


def refresh(backfill_pages: int = 0) -> int:
    added = 0
    for ch in cfg()["sources"]["youtube_channels"]:
        items = _backfill(ch["channel_id"], backfill_pages) if backfill_pages else _rss(ch["channel_id"])
        # New uploads are timely, so they jump the queue; back-catalogue does not.
        added += _store(ch["name"], items, priority=1 if backfill_pages else 3)
    tools = cfg().get("ai_tools", {})
    if tools.get("enabled"):
        try:
            added += _store("AI tools", _tools_feed(tools["feed"]), priority=2, system=TOOLS_TRIAGE)
        except httpx.HTTPError as e:
            log.warning("AI tools feed unavailable: %s", e)
        added += seed_tools()
    added += seed_evergreen()
    db.set_kv("ideas_refreshed", db.now())
    log.info("ideas refreshed: %d new", added)
    return added


def seed_evergreen() -> int:
    """Topics beginners search for forever. Used when the source feed is dry."""
    added = 0
    with db.conn() as c:
        for line in (ASSETS / "evergreen_topics.txt").read_text().splitlines():
            topic = line.strip()
            if topic and not topic.startswith("#"):
                cur = c.execute(
                    "INSERT OR IGNORE INTO ideas (source, source_ref, topic, status, priority, created)"
                    " VALUES ('evergreen', ?, ?, 'new', 0, ?)", ("ev:" + topic.lower(), topic, db.now()))
                added += cur.rowcount
    return added


def seed_tools() -> int:
    """Well-known AI tools (assets/ai_tools.txt): evergreen 'how to use' topics."""
    added = 0
    with db.conn() as c:
        for line in (ASSETS / "ai_tools.txt").read_text().splitlines():
            if "|" not in line or line.lstrip().startswith("#"):
                continue
            name, url = (x.strip() for x in line.split("|", 1))
            cur = c.execute(
                "INSERT OR IGNORE INTO ideas (source, source_ref, source_title, source_text, topic, status, priority,"
                " created) VALUES ('tool-evergreen', ?, ?, ?, ?, 'new', 1, ?)",
                ("tool:" + name.lower(), name, f"website: {url}", f"How to use {name}", db.now()))
            added += cur.rowcount
    return added


def add_topic(topic: str) -> int:
    """An owner request jumps the queue: it is used for the next video of either kind."""
    with db.conn() as c:
        return c.execute("INSERT INTO ideas (source, source_ref, topic, status, priority, created)"
                         " VALUES ('owner', ?, ?, 'new', 9, ?)", (f"owner:{db.now()}:{topic.strip().lower()}", topic.strip(), db.now())).lastrowid


def next_idea(kind: str):
    """Best unused idea for a short (max 2 shorts per idea) or a long video.

    Owner requests always come first. Otherwise a share of videos (ai_tools.share) is about AI
    tools and the rest are concept explainers; if one lane is empty the other is used."""
    import random
    used = "long_made = 0" if kind == "long" else "shorts_made < 2"
    order = " ORDER BY priority DESC, (shorts_made + long_made) ASC, id DESC LIMIT 1"
    tools = cfg().get("ai_tools", {})
    want_tool = tools.get("enabled") and random.random() < tools.get("share", {}).get(kind, 0)
    lanes = ["source IN ('AI tools','tool-evergreen')", "source NOT IN ('AI tools','tool-evergreen')"]
    with db.conn() as c:
        owner = c.execute(f"SELECT * FROM ideas WHERE status='new' AND {used} AND source='owner'{order}").fetchone()
        if owner:
            return owner
        for lane in (lanes if want_tool else lanes[::-1]):
            idea = c.execute(f"SELECT * FROM ideas WHERE status='new' AND {used} AND {lane}{order}").fetchone()
            if idea:
                return idea
    return None
