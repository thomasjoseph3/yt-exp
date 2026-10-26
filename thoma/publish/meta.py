"""Facebook Page and Instagram uploads through the Meta Graph API.

Needs, in .env: META_PAGE_ID, META_PAGE_TOKEN (long-lived Page token with
pages_manage_posts, pages_read_engagement, instagram_basic,
instagram_content_publish) and META_IG_USER_ID (an Instagram professional
account linked to that Page). Shorts go up as Reels on both.
"""
import logging
import time
from pathlib import Path

import httpx

from ..config import cfg, secret
from . import caption

log = logging.getLogger("thoma.meta")


def _v():
    return cfg()["publish"]["graph_api_version"]


def _need(*names):
    vals = [secret(n) for n in names]
    missing = [n for n, v in zip(names, vals) if not v]
    if missing:
        raise RuntimeError(f"missing in .env: {', '.join(missing)}")
    return vals


def _check(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        raise RuntimeError(f"Meta HTTP {r.status_code}: {r.text[:400]}")
    return r.json()


def instagram_reel(video: Path, script: dict) -> dict:
    ig, token = _need("META_IG_USER_ID", "META_PAGE_TOKEN")
    g = f"https://graph.facebook.com/{_v()}"
    c = _check(httpx.post(f"{g}/{ig}/media", timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "share_to_feed": "true",
        "caption": caption(script, "short", "instagram")[:2200], "access_token": token}))
    cid = c["id"]
    data = video.read_bytes()
    _check(httpx.post(f"https://rupload.facebook.com/ig-api-upload/{_v()}/{cid}", content=data, timeout=600,
                      headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))}))
    for _ in range(60):  # Instagram processes the video before it can be published
        st = _check(httpx.get(f"{g}/{cid}", params={"fields": "status_code,status", "access_token": token}))
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing failed: {st.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timed out")
    pub = _check(httpx.post(f"{g}/{ig}/media_publish", data={"creation_id": cid, "access_token": token}, timeout=60))
    link = _check(httpx.get(f"{g}/{pub['id']}", params={"fields": "permalink", "access_token": token}))
    return {"remote_id": pub["id"], "url": link.get("permalink", "")}


def facebook_reel(video: Path, script: dict) -> dict:
    page, token = _need("META_PAGE_ID", "META_PAGE_TOKEN")
    g = f"https://graph.facebook.com/{_v()}"
    start = _check(httpx.post(f"{g}/{page}/video_reels", data={"upload_phase": "start", "access_token": token}))
    vid = start["video_id"]
    data = video.read_bytes()
    _check(httpx.post(f"https://rupload.facebook.com/video-upload/{_v()}/{vid}", content=data, timeout=600,
                      headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))}))
    _check(httpx.post(f"{g}/{page}/video_reels", timeout=60, data={
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
        "description": caption(script, "short", "facebook"), "access_token": token}))
    return {"remote_id": vid, "url": f"https://www.facebook.com/reel/{vid}"}


def facebook_video(video: Path, script: dict) -> dict:
    page, token = _need("META_PAGE_ID", "META_PAGE_TOKEN")
    with video.open("rb") as f:
        r = _check(httpx.post(f"https://graph-video.facebook.com/{_v()}/{page}/videos", timeout=1800,
                              data={"title": script["title"], "description": caption(script, "long", "facebook"),
                                    "access_token": token},
                              files={"source": (video.name, f, "video/mp4")}))
    return {"remote_id": r["id"], "url": f"https://www.facebook.com/{page}/videos/{r['id']}"}


def upload(platform: str, video: Path, script: dict, kind: str) -> dict:
    if platform == "instagram":
        return instagram_reel(video, script)
    return facebook_reel(video, script) if kind == "short" else facebook_video(video, script)
