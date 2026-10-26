"""Command line: `uv run thoma <command>`. Run `uv run thoma -h` for the list."""
import argparse
import json
import logging
import time
from logging.handlers import RotatingFileHandler

from .config import DATA, cfg


def main():
    ap = argparse.ArgumentParser(prog="thoma", description="Thoma Explains: automated video studio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ideas", help="pull new topics from source channels")
    p.add_argument("--backfill", type=int, default=0, help="pages of 50 older uploads (needs YOUTUBE_API_KEY)")
    p = sub.add_parser("topic", help="ask for a video on a topic (used next)")
    p.add_argument("text", nargs="+")
    p = sub.add_parser("make", help="write and render one video now")
    p.add_argument("kind", choices=["short", "long"])
    p.add_argument("--idea", type=int)
    p.add_argument("--script", help="render this script JSON instead of writing one")
    p = sub.add_parser("preview", help="render still frames of a script JSON (fast visual check)")
    p.add_argument("script")
    p.add_argument("kind", choices=["short", "long"])
    p.add_argument("--at", help="comma-separated seconds; default: middle of every visual")
    p = sub.add_parser("approve", help="approve a ready video for the next publish slot")
    p.add_argument("id", type=int)
    p = sub.add_parser("reject", help="drop a ready video")
    p.add_argument("id", type=int)
    p = sub.add_parser("publish", help="upload a video to all its platforms right now")
    p.add_argument("id", type=int)
    sub.add_parser("tick", help="one scheduler pass")
    sub.add_parser("daemon", help="run forever (tick every schedule.tick_minutes)")
    sub.add_parser("status", help="queue and provider status")
    sub.add_parser("test-llm", help="check which LLM providers answer")
    sub.add_parser("auth-youtube", help="sign in to YouTube (once)")
    a = ap.parse_args()

    cfg()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(),
                                  RotatingFileHandler(DATA / "studio.log", maxBytes=5 << 20, backupCount=3)])
    from . import db, ideas, pipeline

    if a.cmd == "ideas":
        print(f"{ideas.refresh(a.backfill)} new ideas")
    elif a.cmd == "topic":
        print(f"queued as idea #{ideas.add_topic(' '.join(a.text))}")
    elif a.cmd == "make":
        script = json.load(open(a.script)) if a.script else None
        vid = pipeline.make(a.kind, a.idea, script)
        print(f"#{vid} ready: {db.video(vid)['path']}")
    elif a.cmd == "preview":
        from . import render
        from .config import OUT
        times = [float(x) for x in a.at.split(",")] if a.at else None
        for p in render.preview(json.load(open(a.script)), a.kind, OUT / "preview", times):
            print(p)
    elif a.cmd == "approve":
        db.update_video(a.id, status="approved")
    elif a.cmd == "reject":
        db.update_video(a.id, status="rejected")
    elif a.cmd == "publish":
        pipeline.publish(a.id)
    elif a.cmd == "tick":
        pipeline.tick()
    elif a.cmd == "daemon":
        while True:
            pipeline.tick()
            time.sleep(cfg()["schedule"]["tick_minutes"] * 60)
    elif a.cmd == "status":
        print(pipeline.status_text())
    elif a.cmd == "test-llm":
        from . import llm
        for prov in cfg()["llm"]["providers"]:
            try:
                out = llm.CALLERS[prov["type"]](prov, "Reply with JSON only.", 'Reply {"ok": true}')
                print(f"{prov['name']:<10} OK   {out.strip()[:60]}")
            except Exception as e:
                print(f"{prov['name']:<10} FAIL {str(e)[:120]}")
    elif a.cmd == "auth-youtube":
        from .publish import youtube
        print("signed in as:", youtube.auth())
