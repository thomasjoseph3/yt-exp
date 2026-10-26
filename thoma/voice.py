"""Thoma's voice: local Kokoro TTS (Apache-2.0, free, runs on CPU), plus simple sound effects."""
import logging
import re
from functools import lru_cache

import numpy as np

from .config import ASSETS, cfg

SR = 24000
SCENE_GAP = 0.3     # silence between scenes
SENTENCE_GAP = 0.08  # silence between sentences in a scene


@lru_cache
def _engine():
    from kokoro_onnx import Kokoro
    k = Kokoro(str(ASSETS / "models/kokoro.onnx"), str(ASSETS / "models/voices.bin"))
    logging.getLogger("phonemizer").setLevel(logging.ERROR)
    blend = cfg()["voice"]["blend"]
    style = sum(w * k.get_voice_style(name) for name, w in blend.items()) / sum(blend.values())
    return k, style


def spoken(text: str) -> str:
    text = text.replace("*", "")
    for written, said in sorted(cfg()["voice"].get("say_as", {}).items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"\b{re.escape(written)}\b", said, text)
    return text


def speak(text: str, speed: float | None = None) -> np.ndarray:
    k, style = _engine()
    audio, sr = k.create(spoken(text), voice=style, speed=speed or cfg()["voice"]["speed"], lang="en-us")
    assert sr == SR
    # trim the model's leading/trailing silence so timings are tight
    loud = np.flatnonzero(np.abs(audio) > 0.01)
    if len(loud):
        audio = audio[max(loud[0] - 600, 0):loud[-1] + 1800]
    return audio.astype(np.float32)


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def narrate(scenes: list[dict], speed: float | None = None):
    """Voice every scene sentence by sentence.

    Returns (track, spans, words): spans are (start, end) per scene; words are
    per-scene lists of (word, start, end), estimated within each sentence."""
    parts, spans, words, t = [], [], [], 0.0
    for s in scenes:
        start, scene_words = t, []
        for sent in sentences(s["say"]):
            a = speak(sent, speed)
            dur = len(a) / SR
            ws = sent.split()
            total = sum(len(w) + 1 for w in ws)
            wt = t
            for w in ws:
                d = dur * (len(w) + 1) / total
                scene_words.append((w, wt, wt + d))
                wt += d
            parts += [a, np.zeros(int(SENTENCE_GAP * SR), np.float32)]
            t += dur + SENTENCE_GAP
        spans.append((start, t))
        words.append(scene_words)
        parts.append(np.zeros(int(SCENE_GAP * SR), np.float32))
        t += SCENE_GAP
    return np.concatenate(parts), spans, words


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
