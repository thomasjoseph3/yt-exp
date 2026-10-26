"""Thoma's voice and the sound around it.

Engines are tried in the order of config voice.engines, per scene:
  gemini = Gemini TTS through the AI Studio API key (GEMINI_API_KEY): free tier, very natural,
           takes a style prompt ("playful, clear") and inline tags like <laugh> or <short pause>.
  google = Google Cloud Chirp 3 HD (GOOGLE_TTS_API_KEY): 1M chars/month free, capped below that.
  kokoro = local Kokoro TTS: free and offline, more robotic. Always works.
An engine that fails (rate limit, quota, network) is skipped for the rest of the run.
"""
import base64
import io
import logging
import re
import subprocess
import time
from functools import lru_cache

import httpx
import numpy as np
import soundfile as sf

from .config import ASSETS, cfg, secret, secrets

log = logging.getLogger("thoma.voice")
SR = 24000
SCENE_GAP = 0.3  # silence between scenes
TAG = re.compile(r"<[^>]{1,30}>")  # inline delivery tags such as <laugh>, <short pause>


@lru_cache
def _kokoro():
    from kokoro_onnx import Kokoro
    k = Kokoro(str(ASSETS / "models/kokoro.onnx"), str(ASSETS / "models/voices.bin"))
    logging.getLogger("phonemizer").setLevel(logging.ERROR)
    return k


def spoken(text: str, keep_tags: bool = False) -> str:
    text = text.replace("*", "")
    if not keep_tags:
        text = TAG.sub("", text)
    for written, said in sorted(cfg()["voice"].get("say_as", {}).items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"\b{re.escape(written)}\b", said, text)
    return re.sub(r"\s+", " ", text).strip()


def _gemini(text: str, voice: str | None) -> np.ndarray:
    v = cfg()["voice"]
    last = None
    for model in v["gemini_models"]:  # a busy model (503) hands over to the next one
        try:
            return _gemini_once(text, voice, model)
        except RuntimeError as e:
            last = e
            if "HTTP 503" not in str(e) and "HTTP 404" not in str(e):
                raise
            log.info("%s busy or unavailable, trying the next TTS model", model)
    raise last


def _gemini_once(text: str, voice: str | None, model: str) -> np.ndarray:
    v = cfg()["voice"]
    body = {
        "model": model,
        "input": [{"type": "user_input", "content": [{
            "type": "text", "text": spoken(text, keep_tags=True),
            "annotations": [{"type": "speech_metadata", "style": v["gemini_style"]}]}]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice or v["gemini_voice"]}]},
    }
    for attempt in range(3):
        for key in secrets("GEMINI_API_KEY"):  # backup keys take over on limits or rejection
            r = httpx.post("https://generativelanguage.googleapis.com/v1beta/interactions", json=body,
                           timeout=180, headers={"x-goog-api-key": key})
            if r.status_code not in (401, 403, 429):
                break
        if r.status_code == 429 and attempt < 2:  # every key is rate-limited: wait and try again
            time.sleep(30)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini TTS HTTP {r.status_code}: {r.text[:200]}")
        break
    audio_items = [c for step in r.json().get("steps", []) if step.get("type") == "model_output"
                   for c in step.get("content", []) if c.get("type") == "audio"]
    if not audio_items:
        raise RuntimeError("Gemini TTS returned no audio")
    audio, sr = sf.read(io.BytesIO(base64.b64decode(audio_items[-1]["data"])), dtype="float32")
    assert sr == SR
    return audio


def _google(text: str, voice: str | None) -> np.ndarray:
    voice = voice or cfg()["voice"]["google_voice"]
    if not _within_free_tier(text):
        raise RuntimeError("monthly free-tier cap reached")
    body = {"input": {"text": spoken(text)}, "voice": {"languageCode": voice[:5], "name": voice},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": SR}}
    r = httpx.post("https://texttospeech.googleapis.com/v1/text:synthesize", json=body, timeout=120,
                   params={"key": secret("GOOGLE_TTS_API_KEY")})
    if r.status_code >= 400:
        raise RuntimeError(f"Google TTS HTTP {r.status_code}: {r.text[:200]}")
    audio, sr = sf.read(io.BytesIO(base64.b64decode(r.json()["audioContent"])), dtype="float32")
    assert sr == SR
    return audio


def _local(text: str, voice: str | None) -> np.ndarray:
    v = cfg()["voice"]
    audio, sr = _kokoro().create(spoken(text), voice=voice or v["kokoro_voice"], speed=v.get("speed", 1.0), lang="en-us")
    assert sr == SR
    return audio


def _within_free_tier(text: str) -> bool:
    """Count Google Cloud TTS characters per month; stop before the free tier ends so it never bills."""
    from datetime import date
    from . import db
    key = f"google_tts_chars:{date.today():%Y-%m}"
    used = db.get_kv(key, 0)
    if used + len(text) > cfg()["voice"].get("google_monthly_char_cap", 900_000):
        return False
    db.set_kv(key, used + len(text))
    return True


ENGINES = {"gemini": (_gemini, "GEMINI_API_KEY"), "google": (_google, "GOOGLE_TTS_API_KEY"), "kokoro": (_local, None)}
_down: set[str] = set()


def speak(text: str, engine: str | None = None, voice: str | None = None) -> np.ndarray:
    order = [engine] if engine else cfg()["voice"].get("engines", ["kokoro"])
    if "kokoro" not in order:
        order = [*order, "kokoro"]
    for name in order:
        fn, key = ENGINES[name]
        if name in _down or (key and not secret(key)):
            continue
        try:
            audio = fn(text, voice if engine else None)
            break
        except Exception as e:
            log.warning("%s voice failed, trying the next one: %s", name, e)
            _down.add(name)
    else:
        raise RuntimeError("no voice engine worked")
    # trim leading/trailing silence so timings are tight
    loud = np.flatnonzero(np.abs(audio) > 0.01)
    if len(loud):
        audio = audio[max(loud[0] - 600, 0):loud[-1] + 1800]
    return audio.astype(np.float32)


def caption_words(text: str) -> list[str]:
    return TAG.sub("", text.replace("*", "")).split()


def narrate(scenes: list[dict]):
    """Voice every scene (one request each, which keeps free-tier rate limits happy).

    Returns (track, spans, words): spans are (start, end) per scene; words are per-scene
    lists of (word, start, end), estimated from character counts with extra weight for pauses."""
    parts, spans, words, t = [], [], [], 0.0
    for s in scenes:
        a = speak(s["say"])
        dur = len(a) / SR
        ws = caption_words(s["say"])
        weight = [len(w) + 1 + (4 if w[-1] in ".!?" else 2 if w[-1] in ",;:" else 0) for w in ws]
        total = sum(weight) or 1
        wt, scene_words = t, []
        for w, wgt in zip(ws, weight):
            d = dur * wgt / total
            scene_words.append((w, wt, wt + d))
            wt += d
        spans.append((t, t + dur))
        words.append(scene_words)
        parts += [a, np.zeros(int(SCENE_GAP * SR), np.float32)]
        t += dur + SCENE_GAP
    return np.concatenate(parts), spans, words


def stretch(track: np.ndarray, factor: float) -> np.ndarray:
    """Speed speech up by `factor` without changing pitch (ffmpeg atempo)."""
    import imageio_ffmpeg
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-f", "f32le", "-ar", str(SR),
                        "-ac", "1", "-i", "-", "-filter:a", f"atempo={factor:.4f}", "-f", "f32le", "-"],
                       input=track.astype(np.float32).tobytes(), capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32)


# ---- sound effects, synthesised so there is nothing to license ----

def _whoosh(dur=0.45):
    n = int(dur * SR)
    rng = np.random.default_rng(5)
    noise = rng.normal(0, 1, n)
    # sweep a one-pole low-pass from dull to bright and back
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    cutoff = 0.02 + 0.25 * env
    out, y = np.zeros(n), 0.0
    for i in range(n):
        y += cutoff[i] * (noise[i] - y)
        out[i] = y
    return (out / (np.abs(out).max() + 1e-9) * env * 0.5).astype(np.float32)


def _pop(dur=0.09):
    t = np.linspace(0, dur, int(dur * SR), endpoint=False)
    f = 900 * np.exp(-t * 18) + 300
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45) * 0.5).astype(np.float32)


@lru_cache
def sfx(name):
    return {"whoosh": _whoosh, "pop": _pop}[name]()


def mix_sfx(track: np.ndarray, events: list[tuple[float, str, float]]) -> np.ndarray:
    """events: (time, 'whoosh'|'pop', volume)."""
    out = np.concatenate([track, np.zeros(SR, np.float32)])
    for t, name, vol in events:
        clip = sfx(name) * vol
        i = max(int(t * SR), 0)
        j = min(i + len(clip), len(out))
        out[i:j] += clip[: j - i]
    return out


# Speech mastering: trim rumble, warm the body, lift clarity, even out the level.
VOICE_CHAIN = ("highpass=f=75,lowpass=f=15000,equalizer=f=180:t=q:w=1:g=1.5,equalizer=f=350:t=q:w=1.5:g=-2,"
               "equalizer=f=3200:t=q:w=1.2:g=2.5,acompressor=threshold=-21dB:ratio=3:attack=5:release=90:makeup=2")


def audition(out_dir, text: str) -> list:
    """Say the same line in several voices so the owner can pick by ear."""
    out_dir.mkdir(parents=True, exist_ok=True)
    v = cfg()["voice"]
    picks = []
    if secret("GEMINI_API_KEY"):
        picks += [("gemini", n) for n in v.get("audition_voices", [])]
    if secret("GOOGLE_TTS_API_KEY"):
        picks += [("google", f"en-US-Chirp3-HD-{n}") for n in v.get("audition_voices", [])]
    picks += [("kokoro", n) for n in v.get("audition_kokoro", [])]
    paths = []
    for engine, name in picks:
        p = out_dir / f"{engine}-{name.split('-')[-1]}.wav"
        sf.write(p, speak(text, engine=engine, voice=name), SR)
        paths.append(p)
    return paths
