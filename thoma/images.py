"""Real photos for scenes: freely licensed images, found by search, checked by eye, cached and credited.

Sources, in order: Wikimedia Commons (real products, people, places; no key), Pexels (stock photos, needs
PEXELS_API_KEY) and Openverse (Creative Commons search, no key, slow). Only licenses that allow use in a
monetized video are taken (config images.licenses), and every photo used is credited in the description.
A vision model (Gemini, free tier) picks the candidate that really shows what the scene needs, so a
search that only matched a file name never reaches the screen. No good photo: the scene falls back to
an animated visual.
"""
import base64
import hashlib
import html as htmlmod
import json
import logging
import re
from pathlib import Path

import httpx

from .config import cfg, secret, secrets

log = logging.getLogger("thoma.images")
UA = {"User-Agent": "ThomaStudio/1.0 (https://github.com/thomasjoseph3/yt-exp; educational video tool)"}
BAD_FILES = re.compile(r"\.(svg|pdf|djvu|tiff?|gif|ogv|webm|ogg|mp3|stl)$|\blogo\b|\bicon\b|\bmap\b|\bflag of\b", re.I)
# a "photo" made by an image generator is not a real photo: never show one as real
AI_MADE = re.compile(r"dall[·\-. ]?e|midjourney|stable ?diffusion|\bflux\b|ai[- ]generated|generated (by|with) (ai|an ai)|"
                     r"\bimagen\b|\bsora\b|firefly", re.I)


def _plain(s) -> str:
    return " ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", str(s or ""))).split())


def _license_ok(code: str) -> bool:
    """code like 'cc by 4.0', 'cc by-sa 3.0', 'cc0', 'public domain', 'pexels'."""
    code = code.lower().replace("-", " ").strip()
    allowed = cfg().get("images", {}).get("licenses", ["cc0", "public domain", "cc by", "cc by sa", "godl", "pexels"])
    if re.search(r"\b(nc|nd)\b|non ?commercial|no ?deriv", code):
        return False
    if re.search(r"\bsa\b|share ?alike", code):
        return "cc by sa" in allowed
    return any(code.startswith(a) or a in code for a in allowed)


def _commons(query: str, n: int = 10) -> list[dict]:
    r = httpx.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 1920, "format": "json"})
    out = []
    for p in sorted((r.json().get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99)):
        ii = (p.get("imageinfo") or [{}])[0]
        m = ii.get("extmetadata") or {}
        lic = _plain((m.get("LicenseShortName") or {}).get("value"))
        title = p["title"].removeprefix("File:")
        author = _plain((m.get("Artist") or {}).get("value"))
        if len(author) > 40:  # e.g. "While provided by the Bureau of Engraving..." -> a short name for the credit
            author = author[:40].rsplit(" ", 1)[0] + "…"
        out.append({"source": "Wikimedia Commons", "title": title, "w": ii.get("width", 0), "h": ii.get("height", 0),
                    "url": ii.get("thumburl") or ii.get("url"), "page": ii.get("descriptionurl", ""),
                    "license": lic, "author": author or "unknown author",
                    "about": title + " " + _plain((m.get("ImageDescription") or {}).get("value"))[:300]
                             + " " + _plain((m.get("Categories") or {}).get("value"))[:300]})
    return out


def _pexels(query: str, n: int = 8) -> list[dict]:
    key = secret("PEXELS_API_KEY")
    if not key:
        return []
    r = httpx.get("https://api.pexels.com/v1/search", headers={"Authorization": key}, timeout=30,
                  params={"query": query, "per_page": n})
    return [{"source": "Pexels", "title": x.get("alt") or query, "w": x["width"], "h": x["height"],
             "url": x["src"]["large2x"], "page": x["url"], "license": "Pexels license",
             "author": x.get("photographer", "Pexels"), "about": x.get("alt") or ""} for x in r.json().get("photos", [])]


def _openverse(query: str, n: int = 8) -> list[dict]:
    r = httpx.get("https://api.openverse.org/v1/images/", headers=UA, timeout=15,
                  params={"q": query, "license_type": "commercial,modification", "page_size": n})
    return [{"source": x.get("source", "Openverse"), "title": x.get("title") or query, "w": x.get("width") or 0,
             "h": x.get("height") or 0, "url": x["url"], "page": x.get("foreign_landing_url", ""),
             "license": f"cc {x['license']} {x.get('license_version') or ''}".replace("cc cc0", "cc0").replace("cc pdm", "public domain"),
             "author": x.get("creator") or "unknown author", "about": x.get("title") or ""}
            for x in r.json().get("results", [])]


def _search(query: str) -> list[dict]:
    found = []
    for fn in (_commons, _pexels, _openverse):
        try:
            found += fn(query)
        except Exception as e:
            log.info("%s search for %r failed: %s", fn.__name__, query, str(e)[:100])
        if len([c for c in found if _usable(c)]) >= 6:
            break
    return [c for c in found if _usable(c)]


def _usable(c: dict) -> bool:
    return (c.get("url") and _license_ok(c["license"]) and min(c["w"], c["h"]) >= 600
            and 0.45 < c["w"] / max(c["h"], 1) < 2.6 and not BAD_FILES.search(c["title"])
            and not AI_MADE.search(c["about"]))


def _score(c: dict, words: set[str]) -> float:
    about = set(re.findall(r"[a-z0-9]+", c["about"].lower()))
    return len(words & about) + min(c["w"], 3000) / 6000


def _thumb(url: str) -> bytes | None:
    small = re.sub(r"/(\d+)px-", "/480px-", url) if "upload.wikimedia.org" in url else url
    try:
        r = httpx.get(small, headers=UA, timeout=30, follow_redirects=True)
        return r.content if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") else None
    except httpx.HTTPError:
        return None


def _pick(cands: list[dict], show: str, line: str) -> int:
    """Let a vision model look at the candidates. -1 = none of them shows it. Without a key: the best match."""
    keys = secrets("GEMINI_API_KEY")
    models = cfg().get("images", {}).get("check_models", ["gemini-2.5-flash-lite", "gemini-2.5-flash"])
    thumbs = [_thumb(c["url"]) for c in cands]
    parts = [{"text": f"These are candidate photos for one scene of a tech explainer video. The narrator says: "
                      f"\"{line}\"\nThe photo must show: {show}.\n"
                      "Pick the photo that clearly shows exactly that (the right product, person, place or thing, "
                      "not a look-alike or a different model), is a real, sharp photograph (not an AI-generated or "
                      "illustrated image, chart, map, logo, screenshot or meme), has NO captions, prices, watermarks "
                      "or other text laid over it, and works full screen. Reply JSON only: "
                      '{"best": <photo number>, "why": "..."}, or {"best": -1, "why": "..."} if none fits.'}]
    for k, (c, t) in enumerate(zip(cands, thumbs)):
        if t:
            parts += [{"text": f"Photo {k}: {c['title'][:80]}"},
                      {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(t).decode()}}]
    if not keys or len(parts) == 1:
        return 0 if any(thumbs) else -1
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for model in models:
        for key in keys:
            try:
                r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                               json=body, headers={"x-goog-api-key": key}, timeout=90)
                if r.status_code != 200:
                    continue
                text = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"].get("parts", []))
                best = int(json.loads(re.search(r"\{.*\}", text, re.S).group(0)).get("best", -1))
                log.info("photo check for %r: %s", show[:50], best)
                return best if -1 <= best < len(cands) and (best == -1 or thumbs[best]) else -1
            except Exception as e:
                log.info("photo check with %s failed: %s", model, str(e)[:100])
    return 0 if thumbs[0] else -1  # nobody could look: trust the search ranking


def find(query: str, show: str, line: str, out_dir: Path) -> dict | None:
    """A checked photo for one scene, downloaded into out_dir/img. Cached by query, so a re-render
    (or the owner's /fix) never searches again. Returns {"file", "credit", "w", "h"} or None."""
    img_dir = out_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    index_file = img_dir / "index.json"
    index = json.loads(index_file.read_text()) if index_file.exists() else {}
    key = f"{query}|{show}".lower()
    if key in index:
        hit = index[key]
        return hit if hit and (img_dir / Path(hit["file"]).name).exists() else None
    words = set(re.findall(r"[a-z0-9]+", f"{query} {show}".lower())) - {"the", "a", "of", "and", "in", "on", "photo"}
    cands = sorted(_search(query), key=lambda c: -_score(c, words))[:6]
    hit = None
    if cands:
        best = _pick(cands, show or query, line)
        if best >= 0:
            c = cands[best]
            try:
                r = httpx.get(c["url"], headers=UA, timeout=60, follow_redirects=True)
                r.raise_for_status()
                f = img_dir / (hashlib.sha1(c["url"].encode()).hexdigest()[:12] + ".jpg")
                f.write_bytes(r.content)
                lic = c["license"] if c["source"] == "Pexels" else c["license"].upper().replace("CC0", "CC0 1.0")
                hit = {"file": str(f), "w": c["w"], "h": c["h"], "page": c["page"],
                       "credit": f"\"{c['title'][:70]}\" by {c['author']}, {lic}, via {c['source']}",
                       "short": f"{c['author'][:30]} / {c['source']}"}
            except httpx.HTTPError as e:
                log.info("download of %s failed: %s", c["url"], e)
    index[key] = hit
    index_file.write_text(json.dumps(index, indent=1, ensure_ascii=False))
    log.info("photo for %r: %s", query, hit["credit"] if hit else "none found")
    return hit


def attach(blocks: list[dict], out_dir: Path) -> list[str]:
    """Find a photo for every photo/photos/quote visual (in place). A photo scene with nothing usable
    becomes a big-text line, so a missing photo never breaks a render. Returns the credit lines."""
    credits = []
    for b in blocks:
        v = b["visual"]
        line = b.get("say", "")
        if v.get("type") == "photo":
            hit = find(v.get("query", ""), v.get("show", ""), line, out_dir) if v.get("query") else None
            if hit:
                v.update(src=Path(hit["file"]).as_uri(), credit=hit["short"], iw=hit["w"], ih=hit["h"])
                credits.append(hit["credit"])
            else:
                text = v.get("caption") or v.get("show") or line[:60]
                b["visual"] = {"type": "bigtext", "text": text}
        elif v.get("type") == "photos":
            for item in v.get("items", []):
                hit = find(item.get("query", ""), item.get("show", ""), line, out_dir) if item.get("query") else None
                if hit:
                    item.update(src=Path(hit["file"]).as_uri(), iw=hit["w"], ih=hit["h"])
                    credits.append(hit["credit"])
        elif v.get("type") == "quote" and v.get("query"):
            hit = find(v["query"], v.get("show") or v["query"], line, out_dir)
            if hit:
                v.update(src=Path(hit["file"]).as_uri(), credit=hit["short"])
                credits.append(hit["credit"])
    return list(dict.fromkeys(credits))
