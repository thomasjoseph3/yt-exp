"""Telegram: send updates and preview videos to the owner, read approve/reject replies."""
import logging
from pathlib import Path

import httpx

from . import db
from .config import secret

log = logging.getLogger("thoma.notify")


def _api(method, **kw):
    token = secret("TELEGRAM_BOT_TOKEN")
    if not token or not secret("TELEGRAM_CHAT_ID"):
        return None
    try:
        r = httpx.post(f"https://api.telegram.org/bot{token}/{method}", timeout=120, **kw)
        return r.json()
    except Exception as e:
        log.warning("telegram %s failed: %s", method, e)
        return None


def send(text: str, reply_to: int | None = None):
    log.info("notify: %s", text.replace("\n", " | "))
    data = {"chat_id": secret("TELEGRAM_CHAT_ID"), "text": text}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    _api("sendMessage", data=data)


def send_file(path: Path, text: str) -> int | None:
    """Send a video as a file, so Telegram keeps the original quality. Returns the message id."""
    if path.stat().st_size > 49 << 20:  # bot upload limit is 50 MB
        send(text + f"\n(file is over Telegram's 50 MB bot limit; it is at {path})")
        return None
    with path.open("rb") as f:
        res = _api("sendDocument", data={"chat_id": secret("TELEGRAM_CHAT_ID"), "caption": text[:1000]},
                   files={"document": (path.name, f, "video/mp4")})
    if not res or not res.get("ok"):
        send(text)
        return None
    return res["result"]["message_id"]


def commands() -> list[tuple[str, str]]:
    """New '/approve 12', '/reject 12 reason' messages from the owner's chat."""
    offset = db.get_kv("telegram_offset", 0)
    res = _api("getUpdates", data={"offset": offset, "timeout": 0})
    if not res or not res.get("ok"):
        return []
    out = []
    for u in res["result"]:
        offset = u["update_id"] + 1
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != secret("TELEGRAM_CHAT_ID"):
            continue  # ignore anyone else who finds the bot
        parts = (msg.get("text") or "").strip().lstrip("/").split(maxsplit=1)
        if parts:
            out.append((parts[0].lower(), parts[1] if len(parts) > 1 else ""))
    db.set_kv("telegram_offset", offset)
    return out
