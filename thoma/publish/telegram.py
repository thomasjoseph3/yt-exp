"""'Manual' platform: the owner gets the full-quality file and a caption on Telegram,
and posts to Instagram/Facebook by hand. No copy is kept anywhere else."""
from pathlib import Path

from .. import db, notify
from ..config import secret
from . import caption


def share(video: Path, script: dict, kind: str, video_id: int) -> dict:
    if not secret("TELEGRAM_BOT_TOKEN") or not secret("TELEGRAM_CHAT_ID"):
        raise RuntimeError("Telegram is not set up (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in .env)")
    # The approval message already carries the file; reply to it instead of sending it twice.
    mid = db.get_kv(f"telegram_msg:{video_id}") or notify.send_file(video, script["title"])
    if not mid:
        raise RuntimeError("could not send the video to Telegram")
    notify.send(f"Post this to Instagram + Facebook. Caption to copy:\n\n{caption(script, kind, 'instagram')}",
                reply_to=mid)
    return {"remote_id": str(mid), "url": "telegram"}
