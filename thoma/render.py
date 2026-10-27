"""Script + narration -> finished MP4, captions (SRT), chapters and thumbnail.

Visuals are HTML/SVG scenes animated by GSAP (assets/web/stage.*). Headless
Chromium seeks the paused timeline to each frame's time, takes a screenshot,
and the frames go straight into ffmpeg together with the voice track.
"""
import base64
import json
import logging
import math
import random
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import soundfile as sf

from . import visuals, voice
from .config import ASSETS, cfg

log = logging.getLogger("thoma.render")
WEB = ASSETS / "web"
TAIL = 1.2  # seconds held after the last line

LAYOUTS = {
    # Thoma the imp sits small in the bottom-right corner; the visuals get the rest of the frame.
    "short": {"W": 1080, "H": 1920, "stage": {"x": 50, "y": 190, "w": 980, "h": 1060},
              "thoma": {"x": 735, "y": 1440, "w": 210}, "captions_y": 1300, "caption_size": 76,
              "brand": {"x": 50, "y": 100, "size": 38}},
    "long": {"W": 1920, "H": 1080, "stage": {"x": 70, "y": 120, "w": 1560, "h": 900},
             "thoma": {"x": 1655, "y": 735, "w": 225}, "captions_y": None, "caption_size": 0,
             "brand": {"x": 70, "y": 46, "size": 32}},
}
MOODS = {"talk", "point", "think", "wow", "laugh", "wave"}
THEMES = ["midnight", "ocean", "ember", "matrix"]  # looks rotate per video so the channel never feels templated


def _thoma_track(scenes, spans, blocks, track, fps, n_frames):
    """Mouth shape per frame (from voice loudness), mood changes, and blink times for the imp."""
    hop = voice.SR // fps
    rms = np.array([np.sqrt(np.mean(track[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(track) else 0.0
                    for i in range(n_frames)])
    ref = np.percentile(rms[rms > 0], 95) if (rms > 0).any() else 1.0
    rms /= max(ref, 1e-6)
    rms = np.convolve(rms, np.ones(3) / 3, mode="same")  # smooth so the mouth doesn't flicker
    mouth, hold = [], 0
    for v in rms:
        m = 0 if v < 0.12 else 1 if v < 0.4 else 2 if v < 0.75 else 3
        if mouth and m != mouth[-1] and hold < 2:  # keep each mouth shape for at least 2 frames
            m = mouth[-1]
        hold = hold + 1 if mouth and m == mouth[-1] else 0
        mouth.append(m)
    moods = []
    block_starts = {round(b["start"], 2) for b in blocks[1:]}
    for s, (a, _) in zip(scenes, spans):
        mood = s.get("mood") or s.get("pose") or "talk"
        mood = mood if mood in MOODS else "talk"
        if mood == "talk" and round(a, 2) in block_starts:  # point at each new visual
            moods += [[a, "point"], [a + 1.2, "talk"]]
        else:
            moods.append([a, mood])
    rnd = random.Random(3)
    blinks, t = [], 1.5
    while t < n_frames / fps:
        blinks.append(round(t, 2))
        t += rnd.uniform(2.6, 4.8)
    return {"mouth": mouth, "moods": moods, "blinks": blinks}


def _srt(words, path: Path):
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"
    # lines end where a sentence ends (or at a comma once long enough), never mid-sentence like "...thinker. Which"
    chunks, cur = [], []
    for scene_words in words:
        for w in scene_words:
            cur.append(w)
            if w[0][-1] in ".?!" or len(cur) >= 9 or (len(cur) >= 5 and w[0][-1] in ",;:"):
                chunks.append(cur)
                cur = []
    if cur:
        chunks.append(cur)
    out = [f"{n}\n{ts(c[0][1])} --> {ts(c[-1][2])}\n{' '.join(w for w, _, _ in c)}\n" for n, c in enumerate(chunks, 1)]
    path.write_text("\n".join(out))


def _captions(words):
    """Groups of up to 3 words for the karaoke captions on Shorts."""
    groups = []
    for scene_words in words:
        cur = []
        for w, s, e in scene_words:
            cur.append({"w": w, "s": s, "e": e})
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

    track, spans, words = voice.narrate(scenes, out_dir / "takes")
    limit = 58.5 if kind == "short" else 12 * 60
    if len(track) / voice.SR > limit:  # a Short must stay under a minute: speak a little faster
        factor = len(track) / voice.SR / (limit - 0.5)
        if factor > 1.2:
            raise ValueError(f"narration is {len(track) / voice.SR:.0f}s, too long for a {kind}")
        track = voice.stretch(track, factor)
        spans = [(a / factor, b / factor) for a, b in spans]
        words = [[(w, a / factor, b / factor) for w, a, b in ws] for ws in words]
    duration = len(track) / voice.SR + TAIL
    n_frames = math.ceil(duration * fps)

    blocks = _blocks(scenes, spans, words, duration)
    events = [(b["start"] - 0.12, "whoosh", 0.35) for b in blocks[1:]]
    events += [(t, "pop", 0.18) for b in blocks for t in b["reveals"][:6]]
    sf.write(out_dir / "voice.wav", track, voice.SR)
    sf.write(out_dir / "sfx.wav", voice.mix_sfx(np.zeros_like(track), events), voice.SR)
    _srt(words, out_dir / "captions.srt")
    script["chapters"] = chapters(script, spans) if kind == "long" else []

    thoma = _thoma_track(scenes, spans, blocks, track, fps, n_frames)
    used = visuals.icons_used([b["visual"] for b in blocks])
    data = {
        "kind": kind, "W": W, "H": H, "fps": fps, "duration": duration, "n_frames": n_frames,
        "theme": script.get("theme") or THEMES[sum(map(ord, out_dir.name)) % len(THEMES)],
        "title": script["title"],
        "layout": {k: L[k] for k in ("stage", "thoma", "captions_y", "caption_size", "brand")},
        "blocks": blocks, "captions": _captions(words) if L["captions_y"] else [],
        "thoma": thoma,
        "icons": {name: visuals.icon_svg(name) for name in used},
    }
    data["scenes"] = [[round(a, 2), round(b, 2)] for a, b in spans]  # lets the owner's "/fix at 0:23" find the scene
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

    mc = cfg().get("music", {})
    tracks = [t for t in mc.get(kind, []) if (ASSETS / "music" / t).exists()]
    out = out_dir / f"{kind}.mp4"
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "-",
           "-i", str(out_dir / "voice.wav"), "-i", str(out_dir / "sfx.wav")]
    voice_in = f"[1:a]aresample=48000,{voice.VOICE_CHAIN},apad"
    if tracks:
        track_name = random.Random(script["title"]).choice(tracks)
        script["music"] = track_name.rsplit(".", 1)[0]
        cmd += ["-stream_loop", "-1", "-i", str(ASSETS / "music" / track_name)]
        # music sits low and ducks further whenever Thoma speaks
        af = (f"{voice_in},asplit=2[v][key];[2:a]aresample=48000,apad[s];"
              f"[3:a]aresample=48000,volume={mc.get('volume', 0.22)}[m];"
              "[m][key]sidechaincompress=threshold=0.015:ratio=8:attack=20:release=450[md];"
              "[v][s][md]amix=inputs=3:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[a]")
    else:
        af = (f"{voice_in}[v];[2:a]aresample=48000,apad[s];"
              "[v][s]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[a]")
    cmd += ["-filter_complex", af, "-map", "0:v", "-map", "[a]", "-shortest",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-tune", "animation",
            "-pix_fmt", "yuv420p", "-r", str(fps),
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
    for f in ("voice.wav", "sfx.wav"):  # muxed into the mp4; no need to keep them
        (out_dir / f).unlink(missing_ok=True)
    log.info("rendered %s (%.0fs, %.0f MB)", out, duration, out.stat().st_size / 1e6)
    return out


def thumbnail(page, script: dict, path: Path):
    """1280x720 thumbnail: big text, one glowing icon, Thoma the imp reacting."""
    first = visuals.normalize(script["scenes"][0].get("visual"))
    text = script.get("thumb_text") or script["title"].split("?")[0] + "?"
    icon = visuals.fix_icon(script.get("thumb_icon") or first.get("icon") or "sparkles")
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto((WEB / "thumb.html").as_uri())
    page.evaluate("d => draw(d)", {"text": text, "icon": visuals.icon_svg(icon)})
    page.screenshot(path=str(path), type="jpeg", quality=92)
