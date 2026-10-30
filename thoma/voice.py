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
            if time.time() - _exhausted.get((model, key), 0) < 3 * 3600:  # quotas reset daily; retry later
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
                _exhausted[(model, key)] = time.time()  # daily quota used up or key rejected: skip for now
            elif r.status_code not in (404, 500, 503):
                raise RuntimeError(f"Gemini TTS HTTP {r.status_code}: {r.text[:200]}")
    raise RuntimeError("all Gemini TTS models and keys unavailable: " + "; ".join(errors[-4:]))


_exhausted: dict = {}
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


class VoiceUnavailable(RuntimeError):
    """No allowed voice has quota left right now. The video waits and is voiced later (Gemini's free
    tier resets every day) instead of switching to a voice that doesn't sound like Thoma."""


def speak(text: str, engine: str | None = None, voice: str | None = None, strict: bool = False) -> np.ndarray:
    """strict: use only `engine` (raise instead of falling back), so one video never mixes voices."""
    global last_engine
    order = [engine] if engine else cfg()["voice"].get("engines", ["kokoro"])
    if "kokoro" not in order and not strict and cfg()["voice"].get("local_fallback", True):
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
        raise VoiceUnavailable("no voice engine has quota left (" + ", ".join(order) + ")")
    # trim leading/trailing silence so timings are tight
    loud = np.flatnonzero(np.abs(audio) > 0.01)
    if len(loud):
        audio = audio[max(loud[0] - 600, 0):loud[-1] + 1800]
    return audio.astype(np.float32)


def caption_words(text: str) -> list[str]:
    """Spoken words as shown in captions; a lone dash or symbol joins the word before it."""
    out = []
    for w in TAG.sub("", text.replace("*", "")).split():
        if re.search(r"[A-Za-z0-9]", w) or not out:
            out.append(w)
        else:
            out[-1] += " " + w if w in ("—", "–", "-") else w
    return [w.replace(" —", "").replace(" –", "").replace(" -", "") for w in out]


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


class RecordingMismatch(ValueError):
    """The owner's recording doesn't follow the script closely enough for the visuals to land on the words."""


def recorded(path) -> np.ndarray:
    """The owner's own recording, cleaned for narration: rumble out, light noise reduction, and long pauses
    cut down to a short breath so the pace stays brisk like a real YouTuber's. Mono at SR."""
    import imageio_ffmpeg
    trim = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1"
    af = (f"highpass=f=70,afftdn=nf=-30,{trim},areverse,{trim},areverse,"
          "silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-45dB:stop_silence=0.32")
    out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(path), "-af", af,
                          "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, np.float32).copy()


last_match = 1.0  # share of script words the aligner found in the last track


def _hear(track: np.ndarray) -> list[tuple[str, float, float]]:
    """Every word the local recogniser hears, with its start and end time."""
    audio16 = np.interp(np.arange(0, len(track), SR / 16000), np.arange(len(track)), track).astype(np.float32)
    # No initial_prompt: given the script as a hint, Whisper skips whole stretches it thinks were "already
    # said", and the captions in those stretches drift by seconds.
    segments, _ = _aligner().transcribe(audio16, language="en", word_timestamps=True, beam_size=5)
    return [(_norm(w.word), w.start, w.end) for seg in segments for w in (seg.words or []) if _norm(w.word)]


def _utterances(track: np.ndarray) -> list[tuple[float, float]]:
    """Stretches of speech between pauses (start, end in seconds)."""
    hop = int(0.02 * SR)
    rms = np.sqrt(np.mean(track[:len(track) // hop * hop].reshape(-1, hop) ** 2, axis=1))
    if not len(rms):
        return []
    quiet = rms < 0.25 * np.median(rms[rms >= np.percentile(rms, 40)])
    segs, start, run = [], None, 0
    for f, q in enumerate(quiet):
        if not q:
            start, run = (f if start is None else start), 0
        else:
            run += 1
            if start is not None and run >= 11:  # a pause of 0.22 s or more ends an utterance
                segs.append((start, f - run + 1))
                start = None
    if start is not None:
        segs.append((start, len(quiet)))
    return [(a * 0.02, b * 0.02) for a, b in segs if b - a >= 8]


def cut_retakes(track: np.ndarray, script_words: list[str]):
    """A fluffed line said again leaves the first try in a recording (and Whisper, hearing the whole take,
    quietly skips a phrase said twice). So each utterance is heard on its own, and one is cut when it
    repeats what comes right after it AND the take matches the script at least as well without it. Coughs
    and clicks (short sounds with no words) go too; ad-libs and repetitions the script really has stay.
    Returns (track, heard words with times in the cut track)."""
    script = [_norm(w) for w in script_words]
    utts = []
    for a, b in _utterances(track):
        lo, hi = max(int((a - 0.1) * SR), 0), min(int((b + 0.1) * SR), len(track))
        clip = track[lo:hi]
        clip16 = np.interp(np.arange(0, len(clip), SR / 16000), np.arange(len(clip)), clip).astype(np.float32)
        segments, _ = _aligner().transcribe(clip16, language="en", word_timestamps=True, beam_size=5,
                                            condition_on_previous_text=False)
        ws = [(_norm(w.word), lo / SR + w.start, lo / SR + w.end) for seg in segments for w in (seg.words or [])
              if _norm(w.word)]
        utts.append((a, b, ws))

    def matched(keep):
        heard = [w for k in keep for w, _, _ in utts[k][2]]
        return sum(m.size for m in difflib.SequenceMatcher(None, script, heard, autojunk=False).get_matching_blocks())

    keep = list(range(len(utts)))
    best = matched(keep)
    for i, (a, b, ws) in enumerate(utts):
        words = [w for w, _, _ in ws]
        if not words:
            if b - a < 2.0:  # a cough or a click
                keep.remove(i)
            continue
        after = [w for v in utts[i + 1:i + 3] for w, _, _ in v[2]][:len(words) + 6]
        if len(set(words) & set(after)) < min(2, len(set(words))):
            continue
        trial = [k for k in keep if k != i]
        score = matched(trial)
        if score >= best:
            keep, best = trial, score
    cuts = []
    for i in sorted(set(range(len(utts))) - set(keep)):
        nxt = utts[i + 1][0] if i + 1 < len(utts) else len(track) / SR
        cuts.append((max(utts[i][0] - 0.03, 0), nxt - 0.03))
    heard = [w for k in keep for w in utts[k][2]]
    if not cuts:
        return track, heard
    pieces, at, fade = [], 0, int(0.01 * SR)
    for a, b in cuts:
        pieces.append(track[at:int(a * SR)].copy())
        at = int(b * SR)
    pieces.append(track[at:].copy())
    for p in pieces:  # tiny fades so a cut never clicks
        if len(p) > 2 * fade:
            p[:fade] *= np.linspace(0, 1, fade)
            p[-fade:] *= np.linspace(1, 0, fade)
    log.info("cut %d retake(s)/noise from the recording: %s", len(cuts), ", ".join(f"{a:.1f}-{b:.1f}s" for a, b in cuts))

    def shift(t):
        return t - sum(min(b, t) - a for a, b in cuts if t > a)
    heard = [(w, shift(a), shift(b)) for w, a, b in heard]
    return np.concatenate(pieces), heard


def align(track: np.ndarray, script_words: list[str], heard=None) -> list[tuple[float, float]]:
    """Start/end time of every script word in the track, from local speech recognition.
    Words the recogniser hears differently (numbers, acronyms) are interpolated between neighbours."""
    heard = heard if heard is not None else _hear(track)
    times: list = [None] * len(script_words)
    sm = difflib.SequenceMatcher(None, [_norm(w) for w in script_words], [h[0] for h in heard], autojunk=False)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            times[a + k] = (heard[b + k][1], heard[b + k][2])
    global last_match
    total = len(track) / SR
    known = [i for i, t in enumerate(times) if t]
    last_match = len(known) / max(len(script_words), 1)
    log.info("aligned %d of %d words by ear; the rest are placed between them", len(known), len(script_words))
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


def narrate(scenes: list[dict], cache_dir=None, recording=None):
    """Voice the script as one continuous take (or a few long chunks), set the pace, then find
    exactly when every word is spoken.

    cache_dir keeps each chunk's raw take, so re-rendering after a small script fix only re-voices
    the chunks whose words changed. recording: the owner's own narration of the whole script, used
    instead of a TTS voice.
    Returns (track, spans, words): spans are (start, end) per scene; words are per-scene lists of
    (word, start, end)."""
    track = recorded(recording) if recording else _tts(scenes, cache_dir)
    per_scene = [caption_words(s["say"]) for s in scenes]
    flat = [w for ws in per_scene for w in ws]
    wpm = len(flat) / (len(track) / SR / 60)
    target = cfg()["voice"].get("target_wpm", 165)
    heard = None
    if recording:  # a real person's pace is kept; only a slow read gets a gentle nudge
        track, heard = cut_retakes(track, flat)
        wpm = len(flat) / (len(track) / SR / 60)
        if wpm < target * 0.88:
            factor = min(target * 0.95 / wpm, 1.12)
            log.info("recording pace %.0f wpm, speeding up x%.2f", wpm, factor)
            track = stretch(track, factor)
            heard = [(w, a / factor, b / factor) for w, a, b in heard]
    elif wpm < target * 0.93 or wpm > target * 1.07:  # too slow sounds lifeless, too fast loses people
        factor = min(max(target / wpm, 0.85), 1.2)       # small changes only, pitch stays the same
        log.info("voice pace %.0f wpm, adjusting speed x%.2f", wpm, factor)
        track = stretch(track, factor)
    times = align(track, flat, heard)
    if recording and last_match < 0.6:
        raise RecordingMismatch(f"only {last_match:.0%} of the script's words were heard in the recording")
    words, k = [], 0
    for ws in per_scene:
        words.append([(w, *times[k + j]) for j, w in enumerate(ws)])
        k += len(ws)
    starts = [0.0] + [ws[0][1] for ws in words[1:]]
    ends = starts[1:] + [min(words[-1][-1][2] + 0.3, len(track) / SR)]
    return track, list(zip(starts, ends)), words


def _tts(scenes: list[dict], cache_dir=None) -> np.ndarray:
    import hashlib
    import json
    global pinned_model
    _down.clear()  # a long-running daemon tries every engine again for each video
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
    return np.concatenate(parts[:-1])


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
def level(track: np.ndarray, target_db: float = -15.0) -> np.ndarray:
    """One fixed gain so speech sits at the same loudness in every video (about -14 LUFS after the
    mastering chain's compressor and makeup gain). Measured on the speech only, not the silences."""
    frames = track[: len(track) // 480 * 480].reshape(-1, 480)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    speech = rms[rms > max(rms.max() * 0.05, 1e-4)]
    if not len(speech):
        return track
    gain = 10 ** ((target_db - 20 * np.log10(np.sqrt((speech ** 2).mean()))) / 20)
    return np.clip(track * gain, -1, 1).astype(np.float32)


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
