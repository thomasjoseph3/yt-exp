"""Real stock photos for 'image' scenes, from Pixabay.

An 'image' visual asks for a real photo by search term (e.g. "self-driving car street").
We search Pixabay, download the best hit into the video's out folder, and hand the local
file path to the stage page. Photos are deleted again after the video is rendered
(render.render() calls cleanup()), so nothing piles up on disk.

Pixabay rules we honour:
- Download and serve the file locally; never hotlink Pixabay URLs in the page.
- safesearch is always on.
- Pixabay Content License: free for commercial use, no attribution required.

No PIXABAY key, no results, or any network error -> returns None, and the stage builder
falls back to plain text so a video is never blank or broken.
"""
import hashlib
import logging
import shutil
import time
from pathlib import Path

import httpx

from .config import secret

log = logging.getLogger(__name__)

API = "https://pixabay.com/api/"
IMAGE_TYPES = {"photo", "illustration", "vector", "all"}
# Pixabay's image CDN 429s/403s requests without a browser-like User-Agent.
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _name(query: str, orientation: str, image_type: str) -> str:
    return hashlib.md5(f"{query}|{orientation}|{image_type}".encode()).hexdigest()[:12]


def fetch(query: str, images_dir: Path, orientation: str = "horizontal",
          image_type: str = "photo") -> str | None:
    """Download a photo for `query` into images_dir and return its file:// URI (or None)."""
    key = secret("PIXABAY")
    query = (query or "").strip()
    if not key or not query:
        return None
    if image_type not in IMAGE_TYPES:
        image_type = "photo"
    images_dir.mkdir(parents=True, exist_ok=True)

    images_dir = images_dir.resolve()
    stem = _name(query, orientation, image_type)
    for cached in images_dir.glob(f"{stem}.*"):  # already fetched this video
        return cached.as_uri()

    try:
        r = httpx.get(API, params={
            "key": key, "q": query[:100], "image_type": image_type,
            "orientation": orientation, "safesearch": "true",
            "per_page": 5, "order": "popular",
        }, timeout=30, headers=UA)
        r.raise_for_status()
        hits = r.json().get("hits") or []
        if not hits:
            log.warning("pixabay: no results for %r", query)
            return None
        hit = hits[0]
        url = hit.get("largeImageURL") or hit.get("webformatURL")
        if not url:
            return None
        img = None
        for attempt in range(3):  # the CDN 429s on bursts (several image scenes in a row); back off and retry
            img = httpx.get(url, timeout=60, follow_redirects=True, headers=UA)
            if img.status_code != 429:
                break
            time.sleep(1.5 * (attempt + 1))
        img.raise_for_status()
        ext = ".png" if url.lower().split("?")[0].endswith(".png") else ".jpg"
        dest = images_dir / f"{stem}{ext}"
        dest.write_bytes(img.content)
        log.info("pixabay: %r -> %s (%s)", query, dest.name, hit.get("pageURL", ""))
        return dest.as_uri()
    except Exception as e:  # network down, rate limit, bad key: fall back to text
        log.warning("pixabay fetch failed for %r: %s", query, e)
        return None


def cleanup(images_dir: Path) -> None:
    """Delete all downloaded photos (called after the video is rendered)."""
    shutil.rmtree(images_dir, ignore_errors=True)
