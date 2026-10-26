"""YouTube upload through the Data API (OAuth, resumable).

One-time setup: Google Cloud project -> enable "YouTube Data API v3" -> OAuth
client of type "Desktop app" -> save the JSON as
~/.config/thoma-studio/youtube_client.json -> run `thoma auth-youtube`.
Until Google audits your API project, uploads are forced to private.
"""
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ..config import SECRETS_DIR, cfg
from . import caption

log = logging.getLogger("thoma.youtube")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]
CLIENT = SECRETS_DIR / "youtube_client.json"
TOKEN = SECRETS_DIR / "youtube_token.json"


def auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES).run_local_server(port=0)
    TOKEN.write_text(creds.to_json())
    TOKEN.chmod(0o600)
    me = _service().channels().list(part="snippet", mine=True).execute()["items"][0]
    return me["snippet"]["title"]


def _service():
    if not TOKEN.exists():
        raise RuntimeError("YouTube is not signed in: run `thoma auth-youtube`")
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(video: Path, script: dict, kind: str, public: bool) -> dict:
    yt = _service()
    title = script["title"]
    if kind == "short" and "#shorts" not in title.lower() and len(title) <= 92:
        title += " #Shorts"
    body = {
        "snippet": {"title": title[:100], "description": caption(script, kind, "youtube")[:4900],
                    "tags": script.get("tags", []), "categoryId": cfg()["publish"]["youtube_category"],
                    "defaultLanguage": "en", "defaultAudioLanguage": "en"},
        "status": {"privacyStatus": "public" if public else "private", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},
    }
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


def make_public(remote_id: str):
    yt = _service()
    yt.videos().update(part="status", body={"id": remote_id, "status": {
        "privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}).execute()
