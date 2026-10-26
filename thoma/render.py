"""Script + narration -> finished MP4, captions (SRT), chapters and thumbnail.

Visuals are HTML/SVG scenes animated by GSAP (assets/web/stage.*). Headless
Chromium seeks the paused timeline to each frame's time, takes a screenshot,
and the frames go straight into ffmpeg together with the voice track.
"""
import base64
import io
import json
import logging
import math
import random
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import soundfile as sf

from . import character, visuals, voice
from .config import ASSETS, cfg

log = logging.getLogger("thoma.render")
WEB = ASSETS / "web"
TAIL = 1.2  # seconds held after the last line

LAYOUTS = {
    "short": {"W": 1080, "H": 1920, "stage": {"x": 50, "y": 200, "w": 980, "h": 1040},
              "thoma": {"x": 290, "y": 1430, "w": 500, "h": 750}, "captions_y": 1285, "caption_size": 74,
              "brand": {"x": 50, "y": 100, "size": 38}},
    "long": {"W": 1920, "H": 1080, "stage": {"x": 70, "y": 140, "w": 1380, "h": 880},
             "thoma": {"x": 1440, "y": 340, "w": 467, "h": 700}, "captions_y": None, "caption_size": 0,
             "brand": {"x": 70, "y": 52, "size": 32}},
}


def _png_uri(img) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG", compress_level=1)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _thoma_track(scenes, spans, blocks, track, fps, n_frames, height):
    """Per-frame [sprite index, bob px], plus the sprite images."""
    hop = voice.SR // fps
    rms = np.array([np.sqrt(np.mean(track[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(track) else 0.0
                    for i in range(n_frames)])
    ref = np.percentile(rms[rms > 0], 95) if (rms > 0).any() else 1.0
    rms /= max(ref, 1e-6)
    rnd = random.Random(3)
    blinks, t = [], 1.5
    while t < n_frames / fps:
        blinks.append(t)
        t += rnd.uniform(2.6, 4.8)
    block_starts = [b["start"] for b in blocks]
    scene_starts = [a for a, _ in spans]
    keys, sprites, frames = {}, [], []
    for fi in range(n_frames):
        t = fi / fps
        si = max(0, int(np.searchsorted(scene_starts, t, side="right")) - 1)
        pose = scenes[si].get("pose", "talk")
        if pose == "talk" and any(s <= t < s + 1.0 for s in block_starts[1:]):
            pose = "point"
        level = rms[fi]
        mouth = 0 if level < 0.12 else 1 if level < 0.4 else 2 if level < 0.75 else 3
        blink = any(b <= t < b + 0.13 for b in blinks)
        speaking = level > 0.05
        gesture = (int(t * 3) % 6) * 2 if speaking and pose == "talk" else 0
        key = (pose, mouth, blink, gesture)
        if key not in keys:
            keys[key] = len(sprites)
            sprites.append(_png_uri(character.sprite(pose, mouth, blink, gesture, height)))
        bob = round(4 * math.sin(t * 2 * math.pi / 1.7)) if speaking else 0
        frames.append([keys[key], bob])
    return sprites, frames


def _srt(words, path: Path):
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"
    out, n = [], 0
    for scene_words in words:
        for i in range(0, len(scene_words), 8):
            chunk = scene_words[i:i + 8]
            n += 1
            text = " ".join(w for w, _, _ in chunk).replace("*", "")
            out.append(f"{n}\n{ts(chunk[0][1])} --> {ts(chunk[-1][2])}\n{text}\n")
    path.write_text("\n".join(out))


def _captions(words):
    """Groups of up to 3 words for the karaoke captions on Shorts."""
    groups = []
    for scene_words in words:
        cur = []
        for w, s, e in scene_words:
            cur.append({"w": w.replace("*", ""), "s": s, "e": e})
            if len(cur) == 3 or w[-1] in ".,?!:;":
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
    return [{"start": g[0]["s"], "end": g[-1]["e"], "words": g} for g in groups]


def _blocks(scenes, spans, words, end_time):
    """Merge 'keep' scenes into the visual before them and time every reveal."""
    blocks = []
    for s, (a, b), ws in zip(scenes, spans, words):
        v = visuals.normalize(s.get("visual"))
        if v.get("type") == "keep" and blocks:
            blocks[-1]["words"] += ws
            continue
        if v.get("type") == "keep":
            v = {"type": "bigtext", "text": s["say"][:60]}
        blocks.append({"visual": v, "start": a, "words": list(ws)})
    for i, blk in enumerate(blocks):
        blk["end"] = blocks[i + 1]["start"] if i + 1 < len(blocks) else end_time
        blk["reveals"] = visuals.reveal_times(blk["visual"], blk["words"], blk["start"], blk["end"])
        del blk["words"]
    return blocks


def chapters(script: dict, spans) -> list[tuple[float, str]]:
    marks = [(0.0, "Intro")]
    for s, (a, _) in zip(script["scenes"], spans):
        if s.get("chapter") and a - marks[-1][0] >= 10:
            marks.append((round(a, 1), s["chapter"]))
    return marks if len(marks) >= 3 else []


def _browser(W, H):
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(args=["--allow-file-access-from-files"])
    page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    return pw, browser, page, errors


def prepare(script: dict, kind: str, out_dir: Path) -> dict:
    """Narrate, time every visual, and build the data the stage page needs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fps = cfg()["video"]["fps"]
    L = LAYOUTS[kind]
    W, H = L["W"], L["H"]
    scenes = script["scenes"]

    track, spans, words = voice.narrate(scenes)
    limit = 58.5 if kind == "short" else 12 * 60
    if len(track) / voice.SR > limit:  # a Short must stay under a minute: speak a little faster
        speed = cfg()["voice"]["speed"] * len(track) / voice.SR / (limit - 1)
        if speed > 1.25:
            raise ValueError(f"narration is {len(track) / voice.SR:.0f}s, too long for a {kind}")
        track, spans, words = voice.narrate(scenes, speed)
    duration = len(track) / voice.SR + TAIL
    n_frames = math.ceil(duration * fps)

    blocks = _blocks(scenes, spans, words, duration)
    events = [(b["start"] - 0.12, "whoosh", 0.35) for b in blocks[1:]]
    events += [(t, "pop", 0.18) for b in blocks for t in b["reveals"][:6]]
    sf.write(out_dir / "voice.wav", voice.mix_sfx(track, events), voice.SR)
    _srt(words, out_dir / "captions.srt")
    script["chapters"] = chapters(script, spans) if kind == "long" else []

    sprites, frames = _thoma_track(scenes, spans, blocks, track, fps, n_frames, L["thoma"]["h"])
    used = visuals.icons_used([b["visual"] for b in blocks])
    data = {
        "kind": kind, "W": W, "H": H, "fps": fps, "duration": duration, "n_frames": n_frames,
        "title": script["title"],
        "layout": {k: L[k] for k in ("stage", "thoma", "captions_y", "caption_size", "brand")},
        "blocks": blocks, "captions": _captions(words) if L["captions_y"] else [],
        "thoma": {"sprites": sprites, "frames": frames},
        "icons": {name: visuals.icon_svg(name) for name in used},
    }
    (out_dir / "timeline.json").write_text(json.dumps({k: v for k, v in data.items() if k not in ("thoma", "icons")}, indent=1))
    return data


def preview(script: dict, kind: str, out_dir: Path, times: list[float] | None = None) -> list[Path]:
    """Still frames at chosen times (default: the middle of every visual). Fast way to check a look."""
    data = prepare(script, kind, out_dir)
    times = times or [round((b["start"] + b["end"]) / 2, 2) for b in data["blocks"]]
    pw, browser, page, errors = _browser(data["W"], data["H"])
    paths = []
    try:
        page.goto((WEB / "stage.html").as_uri())
        page.evaluate("d => load(d)", data)
        for t in times:
            page.evaluate("t => seek(t)", t)
            p = out_dir / f"preview_{t:06.2f}.png"
            page.screenshot(path=str(p))
            paths.append(p)
        if kind == "long":
            thumbnail(page, script, out_dir / "thumbnail.jpg")
    finally:
        browser.close()
        pw.stop()
    if errors:
        log.warning("stage errors: %s", errors[:5])
    return paths


def render(script: dict, kind: str, out_dir: Path) -> Path:
    data = prepare(script, kind, out_dir)
    fps, n_frames, duration, W, H = data["fps"], data["n_frames"], data["duration"], data["W"], data["H"]

    music = sorted(p for p in (ASSETS / "music").glob("*") if p.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a"))
    out = out_dir / f"{kind}.mp4"
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "-", "-i", str(out_dir / "voice.wav")]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(random.Random(len(script["title"])).choice(music))]
        vol = cfg()["video"].get("music_volume", 0.08)
        af = (f"[1:a]aresample=48000,apad[v];[2:a]aresample=48000,volume={vol}[m];"
              "[v][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    else:
        af = "[1:a]aresample=48000,apad,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    cmd += ["-filter_complex", af, "-map", "0:v", "-map", "[a]", "-shortest",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)]

    pw, browser, page, errors = _browser(W, H)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        page.goto((WEB / "stage.html").as_uri())
        page.evaluate("d => load(d)", data)
        if errors:
            log.warning("stage errors: %s", errors[:5])
        cdp = page.context.new_cdp_session(page)
        shot = {"format": "jpeg", "quality": 92, "optimizeForSpeed": True}
        for fi in range(n_frames):
            page.evaluate("t => seek(t)", fi / fps)
            proc.stdin.write(base64.b64decode(cdp.send("Page.captureScreenshot", shot)["data"]))
            if fi % (fps * 30) == 0:
                log.info("render %s: %d/%d s", kind, fi // fps, int(duration))
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg failed")
        if kind == "long":
            thumbnail(page, script, out_dir / "thumbnail.jpg")
    finally:
        if proc.poll() is None:
            proc.kill()
        browser.close()
        pw.stop()
    log.info("rendered %s (%.0fs)", out, duration)
    return out


def thumbnail(page, script: dict, path: Path):
    """1280x720 thumbnail: big text, one glowing icon, Thoma."""
    first = visuals.normalize(script["scenes"][0].get("visual"))
    text = script.get("thumb_text") or script["title"].split("?")[0] + "?"
    icon = visuals.fix_icon(script.get("thumb_icon") or first.get("icon") or "sparkles")
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto((WEB / "thumb.html").as_uri())
    page.evaluate("d => draw(d)", {"text": text, "icon": visuals.icon_svg(icon),
                                   "thoma": _png_uri(character.sprite("point", 2, False, 0, 900))})
    page.screenshot(path=str(path), type="jpeg", quality=92)
