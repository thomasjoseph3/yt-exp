"""Telegram: send updates and preview videos to the owner, read approve/reject replies."""
import json
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


def send_photo(path: Path, text: str = "", reply_to: int | None = None):
    with path.open("rb") as f:
        data = {"chat_id": secret("TELEGRAM_CHAT_ID"), "caption": text[:1000]}
        if reply_to:
            data["reply_to_message_id"] = reply_to
        _api("sendDocument", data=data, files={"document": (path.name, f, "image/jpeg")})


def send_text_file(name: str, content: str, text: str) -> int | None:
    """A text file (e.g. the reading sheet for the owner's recording). Returns the message id."""
    res = _api("sendDocument", data={"chat_id": secret("TELEGRAM_CHAT_ID"), "caption": text[:1000]},
               files={"document": (name, content.encode(), "text/plain")})
    if not res or not res.get("ok"):
        send(text + "\n\n" + content[:3000])
        return None
    return res["result"]["message_id"]


def download(file_id: str, path: Path) -> Path:
    """A file the owner sent (bots can fetch up to 20 MB)."""
    res = _api("getFile", data={"file_id": file_id})
    if not res or not res.get("ok"):
        raise RuntimeError("Telegram would not hand over the file (bots can only fetch files up to 20 MB)")
    r = httpx.get(f"https://api.telegram.org/file/bot{secret('TELEGRAM_BOT_TOKEN')}/{res['result']['file_path']}",
                  timeout=300)
    if r.status_code != 200:  # (never raise_for_status here: its message would carry the bot token)
        raise RuntimeError(f"Telegram file download failed: HTTP {r.status_code}")
    path.write_bytes(r.content)
    return path


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
        audio = msg.get("voice") or msg.get("audio") or msg.get("document") or {}
        if audio and (msg.get("voice") or msg.get("audio") or str(audio.get("mime_type", "")).startswith("audio/")
                      or re.search(r"\.(m4a|mp3|wav|ogg|opus|aac|flac)$", audio.get("file_name", ""), re.I)):
            # the owner's narration: a voice note or an audio file, as a reply to the reading sheet or with "#12"
            out.append(("recording", json.dumps({"file_id": audio["file_id"], "size": audio.get("file_size", 0),
                                                 "name": audio.get("file_name", "voice.ogg"),
                                                 "caption": msg.get("caption", ""),
                                                 "reply_to": (msg.get("reply_to_message") or {}).get("message_id")})))
            continue
        parts = (msg.get("text") or "").strip().lstrip("/").split(maxsplit=1)
        if parts:
            out.append((parts[0].lower(), parts[1] if len(parts) > 1 else ""))
    db.set_kv("telegram_offset", offset)
    return out
