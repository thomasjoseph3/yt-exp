"""Thoma's voice and the sound around it.

Engines are tried in the order of config voice.engines, per scene:
  gemini = Gemini TTS through the AI Studio API key (GEMINI_API_KEY): free tier, very natural,
           takes a style prompt ("playful, clear") and inline tags like <laugh> or <short pause>.
  google = Google Cloud Chirp 3 HD (GOOGLE_TTS_API_KEY): 1M chars/month free, capped below that.
  kokoro = local Kokoro TTS: free and offline, more robotic. Always works.
An engine that fails (rate limit, quota, network) is skipped for the rest of the run.
"""
import base64
import difflib
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
    """Try every TTS model with every key: each model/key pair has its own free daily quota
    (about 10 requests a day), so a limit on one just moves on to the next."""
    v = cfg()["voice"]
    global last_model
    errors = []
    for model in [pinned_model] if pinned_model else v["gemini_models"]:  # one model per video: same sound
        for key in secrets("GEMINI_API_KEY"):
            if (model, key) in _exhausted:
                continue
            styled = model not in _no_style
            for attempt in range(3):
                r = httpx.post("https://generativelanguage.googleapis.com/v1beta/interactions", timeout=180,
                               json=_gemini_body(text, voice, model, styled), headers={"x-goog-api-key": key})
                if r.status_code == 400 and "metadata is not supported" in r.text and styled:
                    _no_style.add(model)  # older models: plain text only
                    styled = False
                    continue
                if r.status_code == 429 and "per minute" in r.text and attempt == 0:
                    time.sleep(20)  # short-term limit: worth one wait
                    continue
                break
            if r.status_code == 200:
                items = [c for step in r.json().get("steps", []) if step.get("type") == "model_output"
                         for c in step.get("content", []) if c.get("type") == "audio"]
                if items:
                    last_model = model
                    raw = base64.b64decode(items[-1]["data"])
                    if raw[:4] == b"RIFF":
                        audio, sr = sf.read(io.BytesIO(raw), dtype="float32")
                        assert sr == SR
                        return audio
                    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768  # raw 24 kHz PCM
            errors.append(f"{model}: HTTP {r.status_code}")
            if r.status_code in (429, 401, 403):
                _exhausted.add((model, key))  # daily quota used up or key rejected: skip for this run
            elif r.status_code not in (404, 500, 503):
                raise RuntimeError(f"Gemini TTS HTTP {r.status_code}: {r.text[:200]}")
    raise RuntimeError("all Gemini TTS models and keys unavailable: " + "; ".join(errors[-4:]))


_exhausted: set = set()
pinned_model = last_model = None
_no_style: set = set()


def _gemini_body(text: str, voice: str | None, model: str, styled: bool = True) -> dict:
    v = cfg()["voice"]
    item = {"type": "text", "text": spoken(text, keep_tags=True)}
    if styled:
        item["annotations"] = [{"type": "speech_metadata", "style": v["gemini_style"]}]
    return {
        "model": model,
        "input": [{"type": "user_input", "content": [item]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice or v["gemini_voice"]}]},
    }


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


last_engine = None
ENGINES = {"gemini": (_gemini, "GEMINI_API_KEY"), "google": (_google, "GOOGLE_TTS_API_KEY"), "kokoro": (_local, None)}
_down: set[str] = set()


def speak(text: str, engine: str | None = None, voice: str | None = None, strict: bool = False) -> np.ndarray:
    """strict: use only `engine` (raise instead of falling back), so one video never mixes voices."""
    global last_engine
    order = [engine] if engine else cfg()["voice"].get("engines", ["kokoro"])
    if "kokoro" not in order and not strict:
        order = [*order, "kokoro"]
    for name in order:
        fn, key = ENGINES[name]
        if name in _down or (key and not secret(key)):
            continue
        try:
            audio = fn(text, voice if engine else None)
            last_engine = name
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


CHUNK_WORDS = 170  # whole scenes per TTS request; a Short is one continuous take
CHUNK_GAP = 0.2    # breath between chunks of a long video


def _chunks(scenes: list[dict]) -> list[list[int]]:
    out, cur, n = [], [], 0
    for i, s in enumerate(scenes):
        w = len(caption_words(s["say"]))
        if cur and n + w > CHUNK_WORDS:
            out.append(cur)
            cur, n = [], 0
        cur.append(i)
        n += w
    return out + [cur] if cur else out


@lru_cache
def _aligner():
    from faster_whisper import WhisperModel
    return WhisperModel("base.en", device="cpu", compute_type="int8", download_root=str(ASSETS / "models/whisper"))


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def align(track: np.ndarray, script_words: list[str]) -> list[tuple[float, float]]:
    """Start/end time of every script word in the track, from local speech recognition.
    Words the recogniser hears differently (numbers, acronyms) are interpolated between neighbours."""
    audio16 = np.interp(np.arange(0, len(track), SR / 16000), np.arange(len(track)), track).astype(np.float32)
    segments, _ = _aligner().transcribe(audio16, language="en", word_timestamps=True, beam_size=1,
                                        initial_prompt=" ".join(script_words[:80]))
    heard = [(_norm(w.word), w.start, w.end) for seg in segments for w in (seg.words or [])]
    times: list = [None] * len(script_words)
    sm = difflib.SequenceMatcher(None, [_norm(w) for w in script_words], [h[0] for h in heard], autojunk=False)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            times[a + k] = (heard[b + k][1], heard[b + k][2])
    total = len(track) / SR
    known = [i for i, t in enumerate(times) if t]
    if not known:  # recogniser failed: spread evenly
        step = total / max(len(script_words), 1)
        return [(i * step, (i + 1) * step) for i in range(len(script_words))]
    for i, t in enumerate(times):  # fill gaps proportionally between the nearest known words
        if t:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        t0 = times[prev][1] if prev is not None else 0.0
        t1 = times[nxt][0] if nxt is not None else total
        lo, hi = (prev if prev is not None else -1), (nxt if nxt is not None else len(script_words))
        span = (t1 - t0) / (hi - lo - 1)
        start = t0 + (i - lo - 1) * span
        times[i] = (start, start + span)
    return times


def narrate(scenes: list[dict], cache_dir=None):
    """Voice the script as one continuous take (or a few long chunks), set the pace, then find
    exactly when every word is spoken.

    cache_dir keeps each chunk's raw take, so re-rendering after a small script fix only re-voices
    the chunks whose words changed.
    Returns (track, spans, words): spans are (start, end) per scene; words are per-scene lists of
    (word, start, end)."""
    import hashlib
    import json
    global pinned_model
    # every chunk uses one engine and one model: a video never changes voice halfway
    meta = cache_dir / "voice.json" if cache_dir else None
    if meta and meta.exists():
        engine, pinned_model = (lambda m: (m["engine"], m.get("model")))(json.loads(meta.read_text()))
    else:
        engine, pinned_model = None, None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    try:
        for idxs in _chunks(scenes):
            text = " ".join(scenes[i]["say"] for i in idxs)
            take = cache_dir / f"{hashlib.sha1(text.encode()).hexdigest()[:16]}.flac" if cache_dir else None
            if take and take.exists():
                audio = sf.read(take, dtype="float32")[0]
            else:
                audio = speak(text, engine, strict=engine is not None)
                if engine is None:
                    engine = last_engine
                    pinned_model = last_model if engine == "gemini" else None
                    if meta:
                        meta.write_text(json.dumps({"engine": engine, "model": pinned_model}))
                if take:
                    sf.write(take, audio, SR)
            parts += [audio, np.zeros(int(CHUNK_GAP * SR), np.float32)]
    finally:
        pinned_model = None
    track = np.concatenate(parts[:-1])
    per_scene = [caption_words(s["say"]) for s in scenes]
    flat = [w for ws in per_scene for w in ws]
    wpm = len(flat) / (len(track) / SR / 60)
    target = cfg()["voice"].get("target_wpm", 165)
    if wpm < target * 0.97:  # too slow sounds lifeless: speed up (pitch stays the same)
        factor = min(target / wpm, 1.2)
        log.info("voice pace %.0f wpm, speeding up x%.2f", wpm, factor)
        track = stretch(track, factor)
    times = align(track, flat)
    words, k = [], 0
    for ws in per_scene:
        words.append([(w, *times[k + j]) for j, w in enumerate(ws)])
        k += len(ws)
    starts = [0.0] + [ws[0][1] for ws in words[1:]]
    ends = starts[1:] + [min(words[-1][-1][2] + 0.3, len(track) / SR)]
    return track, list(zip(starts, ends)), words


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
