"""SQLite store: ideas, videos and per-platform uploads."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import DATA, cfg

SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY,
    source TEXT,                 -- e.g. 'IBM Technology' or 'evergreen'
    source_ref TEXT UNIQUE,      -- video id / topic slug, for dedupe
    source_title TEXT,
    source_text TEXT,            -- description, used only for the copy-overlap check
    transcript TEXT,             -- source video transcript: research input + copy-overlap check
    research TEXT,               -- neutral notes the writer works from
    topic TEXT,                  -- the beginner topic Thoma will explain
    angle TEXT,                  -- the analogy / hook angle
    status TEXT DEFAULT 'new',   -- new | rejected
    priority INTEGER DEFAULT 1,
    shorts_made INTEGER DEFAULT 0,
    long_made INTEGER DEFAULT 0,
    created TEXT
);
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER,
    kind TEXT,                   -- short | long
    status TEXT,                 -- writing | rendering | ready | approved | scheduled | published | failed | rejected
    title TEXT,
    script TEXT,                 -- JSON
    path TEXT,
    publish_at TEXT,             -- local time of its posting slot, set when scheduled
    error TEXT,
    created TEXT,
    updated TEXT
);
CREATE TABLE IF NOT EXISTS uploads (
    video_id INTEGER,
    platform TEXT,
    status TEXT,                 -- ok | failed
    remote_id TEXT,
    url TEXT,
    error TEXT,
    created TEXT,
    PRIMARY KEY (video_id, platform)
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def conn():
    cfg()
    c = sqlite3.connect(DATA / "studio.db", timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    if "publish_at" not in {r[1] for r in c.execute("PRAGMA table_info(videos)")}:  # older databases
        c.execute("ALTER TABLE videos ADD COLUMN publish_at TEXT")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def get_kv(key, default=None):
    with conn() as c:
        row = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_kv(key, value):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, json.dumps(value)))


def update_video(video_id, **fields):
    fields["updated"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE videos SET {cols} WHERE id=?", (*fields.values(), video_id))


def video(video_id) -> sqlite3.Row:
    with conn() as c:
        return c.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
