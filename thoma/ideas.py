"""Idea queue: mine source channels for topics, plus an evergreen backlog.

Source videos are used only as topic signals (title + description). Thoma's
scripts are written from scratch, and writer.py blocks copied phrasing.
"""
import difflib
import logging
import xml.etree.ElementTree as ET

import httpx

from . import db, llm
from .config import ASSETS, cfg, secret

log = logging.getLogger("thoma.ideas")
NS = {"a": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/",
      "yt": "http://www.youtube.com/xml/schemas/2015"}

TRIAGE_SYSTEM = """You plan topics for "Thoma Explains", a channel that teaches AI, software,
cloud, security and how tech works to complete beginners. You get titles and
descriptions of videos from other tech channels. For each, decide if its subject
can become an original beginner explainer of ONE clear concept (e.g. a release
about a new database -> "What is a vector database?"; a security incident ->
"What is a supply-chain attack?"). fit=false for podcasts, round-ups that cover
many things, interviews, opinion pieces, product ads, and memes. Reply as JSON:
{"items":[{"ref":"<ref>","fit":true,"topic":"short plain topic, e.g. What is RAG?",
"angle":"one everyday analogy Thoma could use"}]}"""


def _rss(channel_id: str) -> list[dict]:
    r = httpx.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", timeout=30)
    r.raise_for_status()
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


def _store(source: str, items: list[dict], priority: int) -> int:
    with db.conn() as c:
        known = {r[0] for r in c.execute("SELECT source_ref FROM ideas")}
    fresh = [i for i in items if i["ref"] not in known]
    with db.conn() as c:
        topics = [r[0].lower() for r in c.execute("SELECT topic FROM ideas WHERE status='new'")]
    added = 0
    for chunk in (fresh[i:i + 15] for i in range(0, len(fresh), 15)):
        listing = "\n\n".join(f"ref: {i['ref']}\ntitle: {i['title']}\ndescription: {i['text'][:400]}" for i in chunk)
        verdicts = {v["ref"]: v for v in llm.ask_json(TRIAGE_SYSTEM, listing, "triage").get("items", [])}
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
                     "new" if v.get("fit") else "rejected", priority, db.now()))
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


def refresh(backfill_pages: int = 0) -> int:
    added = 0
    for ch in cfg()["sources"]["youtube_channels"]:
        items = _backfill(ch["channel_id"], backfill_pages) if backfill_pages else _rss(ch["channel_id"])
        # New uploads are timely, so they jump the queue; back-catalogue does not.
        added += _store(ch["name"], items, priority=1 if backfill_pages else 3)
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


def add_topic(topic: str) -> int:
    """An owner request jumps the queue: it is used for the next video of either kind."""
    with db.conn() as c:
        return c.execute("INSERT INTO ideas (source, source_ref, topic, status, priority, created)"
                         " VALUES ('owner', ?, ?, 'new', 9, ?)", ("owner:" + db.now(), topic.strip(), db.now())).lastrowid


def next_idea(kind: str):
    """Best unused idea for a short (max 2 shorts per idea) or a long video."""
    used = "long_made = 0" if kind == "long" else "shorts_made < 2"
    with db.conn() as c:
        return c.execute(
            f"SELECT * FROM ideas WHERE status='new' AND {used}"
            " ORDER BY priority DESC, (shorts_made + long_made) ASC, id DESC LIMIT 1").fetchone()
