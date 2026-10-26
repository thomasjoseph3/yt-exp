"""Telegram: send updates and preview videos to the owner, read approve/reject replies."""
import logging
import re
import subprocess
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


LIMIT = 48 << 20  # bot uploads max out at 50 MB


def _fit(path: Path) -> Path:
    """A same-resolution copy squeezed under the bot limit (only for files that are too big)."""
    import imageio_ffmpeg
    probe = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True).stderr
    h, m, sec = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe).groups()
    duration = int(h) * 3600 + int(m) * 60 + float(sec)
    kbps = int(LIMIT * 8 / duration / 1000 * 0.92) - 128  # leave room for audio and container
    small = path.with_name(path.stem + "_telegram.mp4")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(path),
                    "-c:v", "libx264", "-preset", "medium", "-tune", "animation", "-b:v", f"{kbps}k",
                    "-maxrate", f"{kbps * 1.3:.0f}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(small)], check=True)
    return small


def send_file(path: Path, text: str) -> int | None:
    """Send a video as a file, so Telegram keeps the original quality. Returns the message id."""
    if not secret("TELEGRAM_BOT_TOKEN") or not secret("TELEGRAM_CHAT_ID"):
        return None
    to_send = path if path.stat().st_size <= LIMIT else _fit(path)
    with to_send.open("rb") as f:
        res = _api("sendDocument", data={"chat_id": secret("TELEGRAM_CHAT_ID"), "caption": text[:1000]},
                   files={"document": (path.name, f, "video/mp4")})
    if to_send != path:
        to_send.unlink(missing_ok=True)
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
