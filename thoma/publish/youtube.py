"""YouTube upload through the Data API (OAuth, resumable).

One-time setup: Google Cloud project -> enable "YouTube Data API v3" -> OAuth
client of type "Desktop app" -> save the JSON as
~/.config/thoma-studio/youtube_client.json -> run `thoma auth-youtube`.
Until Google audits your API project, uploads are forced to private.
"""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ..config import SECRETS_DIR, cfg
from . import caption

log = logging.getLogger("thoma.youtube")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]
CLIENT = SECRETS_DIR / "youtube_client.json"
TOKEN = SECRETS_DIR / "youtube_token.json"


def auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
    port = int(os.environ.get("THOMA_AUTH_PORT", 0))
    if port:  # inside Docker: no browser here, so print the link and listen on the mapped port
        creds = flow.run_local_server(host="localhost", bind_addr="0.0.0.0", port=port, open_browser=False,
                                      authorization_prompt_message="Open this link in your browser:\n{url}\n")
    else:
        creds = flow.run_local_server(port=0)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    TOKEN.chmod(0o600)
    me = _service().channels().list(part="snippet", mine=True).execute()["items"][0]
    return me["snippet"]["title"]


def _creds():
    if not TOKEN.exists():
        raise RuntimeError("YouTube is not signed in: run `thoma auth-youtube`")
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _service():
    return build("youtube", "v3", credentials=_creds(), cache_discovery=False)


def report(days: int = 28) -> str:
    """A plain-text growth report from the YouTube Analytics API: channel totals plus the top videos
    with their retention. Needs the yt-analytics.readonly scope (re-run auth-youtube if it is missing)."""
    import json as _json
    from datetime import date, timedelta
    granted = _json.loads(TOKEN.read_text(encoding="utf-8")).get("scopes", []) if TOKEN.exists() else []
    if not any("yt-analytics" in s for s in granted):
        return "Analytics not authorised yet. Re-run `uv run thoma auth-youtube` and approve again (the scope list grew)."
    from googleapiclient.errors import HttpError
    creds = _creds()
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    end, start = date.today(), date.today() - timedelta(days=days)
    s, e = start.isoformat(), end.isoformat()
    try:
        tot = ya.reports().query(ids="channel==MINE", startDate=s, endDate=e,
            metrics="views,estimatedMinutesWatched,averageViewPercentage,subscribersGained,likes").execute()
    except HttpError as ex:
        if "accessNotConfigured" in str(ex) or "has not been used" in str(ex):
            return ("The YouTube Analytics API isn't enabled on your Cloud project yet. Enable it here, wait "
                    "~2 min, then retry:\n  https://console.cloud.google.com/apis/library/youtubeanalytics.googleapis.com")
        raise
    row = (tot.get("rows") or [[0, 0, 0, 0, 0]])[0]
    lines = [f"Last {days} days (channel):",
             f"  views={int(row[0])}  watch-hours={row[1] / 60:.1f}  avg-view={row[2]:.0f}%  "
             f"subs+={int(row[3])}  likes={int(row[4])}"]
    vids = ya.reports().query(ids="channel==MINE", startDate=s, endDate=e,
        metrics="views,estimatedMinutesWatched,averageViewPercentage,averageViewDuration",
        dimensions="video", sort="-views", maxResults=10).execute()
    rows = vids.get("rows") or []
    if rows:
        titles = {v["id"]: v["snippet"]["title"] for v in
                  yt.videos().list(part="snippet", id=",".join(r[0] for r in rows)).execute().get("items", [])}
        lines.append(f"\nTop videos by views (retention = how far the average viewer watches):")
        for r in rows:
            lines.append(f"  views={int(r[0]):>5}  retention={r[2]:>4.0f}%  avg={int(r[3]):>3}s  "
                         f"| {titles.get(r[0], r[0])[:60]}")
    return "\n".join(lines)


def upload(video: Path, script: dict, kind: str, publish_at: datetime | None = None) -> dict:
    """Upload; with publish_at (timezone-aware) YouTube itself makes it public at that time,
    so this machine can be off by then. Without it, the video goes public right away."""
    yt = _service()
    title = script["title"]
    if kind == "short" and "#shorts" not in title.lower() and len(title) <= 92:
        title += " #Shorts"
    body = {
        "snippet": {"title": title[:100], "description": caption(script, kind, "youtube")[:4900],
                    "tags": script.get("tags", []), "categoryId": cfg()["publish"]["youtube_category"],
                    "defaultLanguage": "en", "defaultAudioLanguage": "en"},
        "status": {"privacyStatus": "private" if publish_at else "public", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},
    }
    if publish_at:
        body["status"]["publishAt"] = publish_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 << 20, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk(num_retries=5)
    vid = resp["id"]
    log.info("youtube upload ok: %s (%s)", vid, body["status"]["privacyStatus"])
    # Extras can fail on quota or an unverified channel; the video itself is already up.
    thumb, srt = video.parent / "thumbnail.jpg", video.parent / "captions.srt"
    if thumb.exists():
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
        except Exception as e:
            log.warning("thumbnail failed (verify the channel by phone to allow custom thumbnails): %s", e)
    if srt.exists():
        try:
            yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": "en", "name": "English"}},
                                 media_body=MediaFileUpload(str(srt))).execute()
        except Exception as e:
            log.warning("captions failed: %s", e)
    return {"remote_id": vid, "url": f"https://youtu.be/{vid}"}


def unschedule(remote_id: str):
    """Cancel a scheduled release: the video stays private."""
    _service().videos().update(part="status", body={"id": remote_id, "status": {
        "privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}).execute()


def make_public(remote_id: str):
    yt = _service()
    yt.videos().update(part="status", body={"id": remote_id, "status": {
        "privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}).execute()
