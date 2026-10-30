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

DEBATE_TRIAGE = """You pick stories for "Thoma Explains" debate videos: 4-5 minute videos on the tech
fights everyone is arguing about, explained so a 10th-standard student can judge for themselves. You get
headlines and summaries from tech news sites. fit=true only for a live public debate about technology that
ordinary people care about and that will still matter in a month: AI and jobs, AI money and bubbles, big tech
power and lawsuits, privacy and data, AI copyright and artists, safety of self-driving cars and robots,
deepfakes, kids and social media, chips and energy, a company's controversial launch or claim. fit=false for
partisan politics and elections, war, crime stories about private people, health or medical claims, celebrity
gossip, deals and funding rounds with no public debate, product reviews and minor updates.
Reply as JSON:
{"items":[{"ref":"<ref>","fit":true,"topic":"the debate as a plain yes/no question people search, e.g. 'Is the AI bubble about to pop?'",
"angle":"the sharpest real moment of the story, to open the video with"}]}"""

TOOL_SOURCES = ("AI tools", "tool-evergreen")
DEBATE_SOURCES = ("debate", "debate-news")


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


def _news_feed(url: str) -> list[dict]:
    """A news site's RSS/Atom feed: headline + summary per story."""
    import html as htmlmod
    r = httpx.get(url, timeout=30, headers=UA, follow_redirects=True)
    r.raise_for_status()
    items = []
    for block in re.findall(r"(?is)<(?:item|entry)\b.*?</(?:item|entry)>", r.text)[:25]:
        def tag(name):
            m = re.search(rf"(?is)<{name}\b[^>]*>(.*?)</{name}>", block)
            return " ".join(htmlmod.unescape(re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", " ", m.group(1))).split()) if m else ""
        link = tag("link") or (re.search(r'<link[^>]+href="([^"]+)"', block) or [None, ""])[1]
        if tag("title") and link:
            items.append({"ref": "news:" + link[:300], "title": tag("title"),
                          "text": (tag("description") or tag("summary") or tag("content"))[:600] + f"\nlink: {link}"})
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


def top_explainers(topic: str, n: int = 5) -> list[dict]:
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
        # the first minute with timestamps: how a proven video places its hook
        v["opening"] = " ".join(f"[{int(s.start) // 60}:{int(s.start) % 60:02}] {s.text}"
                                for s in fetched if s.start < 60)
        out.append(v)
        if len(out) == n:
            break
    log.info("top explainers for %r: %s", topic[:60], [f"{v['title']} ({v['views']:,} views)" for v in out])
    return out


UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
      "Accept-Language": "en"}


def _page_text(url: str, limit: int = 5000) -> str:
    import html as htmlmod
    try:
        r = httpx.get(url, timeout=25, follow_redirects=True, headers=UA)
        page = re.sub(r"(?is)<(script|style|svg|noscript|nav|header|footer|aside|form)[^>]*>.*?</\1>", " ", r.text)
        paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", page) or [page]
        text = " ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", p)) for p in paras)
        return " ".join(text.split())[:limit]
    except Exception as e:
        log.info("could not read %s: %s", url, str(e)[:100])
        return ""


def news_articles(query: str, n: int = 4, seen: set | None = None) -> list[dict]:
    """Recent news articles on a query (Bing News RSS), with their readable text."""
    import html as htmlmod
    from email.utils import parsedate_to_datetime
    from urllib.parse import parse_qs, urlparse
    seen = seen if seen is not None else set()
    out = []
    try:
        r = httpx.get("https://www.bing.com/news/search", params={"q": query, "format": "rss", "setlang": "en", "mkt": "en-US"},
                      headers=UA, timeout=30)
        items = re.findall(r"<item>(.*?)</item>", r.text, re.S)
    except Exception as e:
        log.info("news search for %r failed: %s", query, e)
        return []
    for item in items:
        if len(out) == n:
            break
        link = htmlmod.unescape(re.search(r"<link>(.*?)</link>", item).group(1))
        link = parse_qs(urlparse(link).query).get("url", [link])[0]
        title = htmlmod.unescape(re.search(r"<title>(.*?)</title>", item).group(1))
        if link in seen or title.lower() in seen:
            continue
        seen |= {link, title.lower()}
        date = (re.search(r"<pubDate>(.*?)</pubDate>", item) or [None, ""])[1]
        try:
            date = f"{parsedate_to_datetime(date):%b %d, %Y}"
        except (TypeError, ValueError):
            date = date[:16]
        outlet = (re.search(r"<News:Source>(.*?)</News:Source>", item) or [None, ""])[1] or urlparse(link).netloc.removeprefix("www.")
        text = _page_text(link, 3500)
        if len(text) > 400:
            out.append({"outlet": htmlmod.unescape(outlet), "title": title, "date": date, "url": link, "text": text})
    return out


def _wikipedia(query: str, n: int = 2, limit: int = 7000) -> list[str]:
    parts = []
    try:
        r = httpx.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
            "action": "query", "list": "search", "srsearch": query, "srlimit": n, "format": "json"})
        for hit in r.json()["query"]["search"]:
            r = httpx.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
                "action": "query", "prop": "extracts", "explaintext": 1, "titles": hit["title"], "format": "json"})
            text = next(iter(r.json()["query"]["pages"].values())).get("extract", "")
            text = re.split(r"\n== (See also|References|External links|Notes) ==", text)[0]
            parts.append(f"Wikipedia, '{hit['title']}':\n{' '.join(text.split())[:limit]}")
    except Exception as e:
        log.info("wikipedia search failed: %s", e)
    return parts


def _article(a: dict) -> str:
    return f"News article '{a['title']}' ({a['outlet']}, {a['date']}):\n{a['text']}"


def web_research(topic: str) -> str:
    """Facts from the open web for 'how it works' topics, which the source channels don't cover:
    Wikipedia for how the thing works, recent news articles for what is new (dated)."""
    query = re.sub(r"https?://\S+|[?!]", "", topic).strip()
    parts = _wikipedia(query) + [_article(a) for a in news_articles(query)]
    log.info("web research for %r: %d sources", topic[:60], len(parts))
    return "\n\n".join(parts)


def debate_research(topic: str, angle: str = "") -> tuple[str, list[dict]]:
    """Both sides of a tech controversy: background (Wikipedia), what happened (recent news), the case
    made by critics and the answer from defenders. Returns the material and the articles used, which
    become the video's 'Sources' list."""
    query = re.sub(r"https?://\S+|[?!]", "", topic).strip()
    query = re.sub(r"^(is|are|does|do|did|will|would|can|could|should)\s+", "", query, flags=re.I)
    seen: set = set()
    articles = news_articles(query, 5, seen)
    for extra in (f"{query} critics warn", f"{query} defenders say", f"{query} experts data"):
        articles += news_articles(extra, 2, seen)
    if angle:
        articles += news_articles(angle[:80], 2, seen)
    parts = _wikipedia(query, 2, 5000) + [_article(a) for a in articles]
    log.info("debate research for %r: %d articles", topic[:60], len(articles))
    return "\n\n".join(parts), [{k: a[k] for k in ("outlet", "title", "date", "url")} for a in articles]


def seed_how_it_works() -> int:
    """'How does X really work?' topics (assets/how_it_works.txt): researched on the open web, each made
    as a long video plus a Short that points to it. They come before the evergreen backlog."""
    added = 0
    with db.conn() as c:  # bottom line first, so the top line gets the newest id and is picked first
        for line in reversed((ASSETS / "how_it_works.txt").read_text().splitlines()):
            topic, _, angle = (x.strip() for x in line.partition("|"))
            if topic and not topic.startswith("#"):
                cur = c.execute(
                    "INSERT OR IGNORE INTO ideas (source, source_ref, topic, angle, status, priority, created)"
                    " VALUES ('how-it-works', ?, ?, ?, 'new', 8, ?)", ("how:" + topic.lower(), topic, angle, db.now()))
                added += cur.rowcount
    return added


def is_how(idea) -> bool:
    return idea is not None and idea["source"] == "how-it-works"


def seed_debates() -> int:
    """The big tech debates (assets/debates.txt): researched from news on every side, each made as a long
    video plus a Short that points to it. First line is made first."""
    added = 0
    with db.conn() as c:
        for line in reversed((ASSETS / "debates.txt").read_text().splitlines()):
            topic, _, angle = (x.strip() for x in line.partition("|"))
            if topic and not topic.startswith("#"):
                cur = c.execute(
                    "INSERT OR IGNORE INTO ideas (source, source_ref, topic, angle, status, priority, created)"
                    " VALUES ('debate', ?, ?, ?, 'new', 8, ?)", ("debate:" + topic.lower(), topic, angle, db.now()))
                added += cur.rowcount
    return added


def is_debate(idea) -> bool:
    """A debate-lane topic, or the owner's own yes/no question ('Is the AI bubble about to pop?')."""
    return idea is not None and (idea["source"] in DEBATE_SOURCES or (
        idea["source"] == "owner" and bool(re.match(r"^\W*(is|are|does|do|did|will|would|can|could|should)\b",
                                                    idea["topic"], re.I))))


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
    for url in cfg()["sources"].get("news_feeds", []):  # tech news: the debates people are having this week
        try:
            added += _store("debate-news", _news_feed(url), priority=9, system=DEBATE_TRIAGE)
        except Exception as e:
            log.warning("news feed %s unavailable: %s", url, e)
    added += seed_how_it_works() + seed_debates() + seed_evergreen()
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
    tools; long videos rotate between the big debates, how-it-works and concept explainers so the
    channel never runs one format twice in a row; if a lane is empty the next one is used."""
    import random
    from datetime import datetime, timedelta
    paired = "('how-it-works','debate','debate-news')"  # their Short is the teaser of the long video
    used = ("long_made = 0" if kind == "long" else
            f"shorts_made < 2 AND NOT (source IN {paired} AND (long_made = 0 OR shorts_made >= 1))")
    stale = (datetime.now() - timedelta(days=cfg()["sources"].get("news_days", 10))).isoformat(timespec="seconds")
    used += f" AND NOT (source='debate-news' AND long_made = 0 AND created < '{stale}')"  # old news is old
    order = " ORDER BY priority DESC, (shorts_made + long_made) ASC, id DESC LIMIT 1"
    tools = cfg().get("ai_tools", {})
    want_tool = tools.get("enabled") and random.random() < tools.get("share", {}).get(kind, 0)
    tool = "source IN ('AI tools','tool-evergreen')"
    lanes = {"debate": "source IN ('debate','debate-news')", "how": "source = 'how-it-works'",
             "explain": "source NOT IN ('AI tools','tool-evergreen','debate','debate-news','how-it-works')"}
    with db.conn() as c:
        owner = c.execute(f"SELECT * FROM ideas WHERE status='new' AND {used} AND source='owner'{order}").fetchone()
        if owner:
            return owner
        if kind == "long":
            last = c.execute("SELECT i.source FROM videos v JOIN ideas i ON i.id = v.idea_id WHERE v.kind='long'"
                             " AND v.status NOT IN ('failed','rejected') ORDER BY v.id DESC LIMIT 1").fetchone()
            last_lane = {"debate": "debate", "debate-news": "debate", "how-it-works": "how"}.get(last[0] if last else "", "explain")
            rotation = [x for x in cfg()["sources"].get("long_rotation", ["debate", "how", "explain"]) if x in lanes]
            k = (rotation.index(last_lane) + 1) % len(rotation) if last_lane in rotation else 0
            order_lanes = [lanes[x] for x in rotation[k:] + rotation[:k]]
        else:
            order_lanes = ["source NOT IN ('AI tools','tool-evergreen')"]
        for lane in ([tool] + order_lanes if want_tool else order_lanes + [tool]):
            idea = c.execute(f"SELECT * FROM ideas WHERE status='new' AND {used} AND {lane}{order}").fetchone()
            if idea:
                return idea
    return None
