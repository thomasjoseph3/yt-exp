"""The production line and the scheduler that runs it.

make()     idea -> script -> render -> 'ready'
publish()  'approved' (or 'ready' with auto_publish) -> every platform
tick()     one scheduler pass: refresh ideas, read owner replies, make what is
           due, publish into the next slot. The daemon calls it every few minutes.
"""
import fcntl
import json
import logging
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import db, ideas, notify, writer
from .config import DATA, OUT, cfg
from .llm import AllProvidersFailed

log = logging.getLogger("thoma.pipeline")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def local_now() -> datetime:
    return datetime.now(ZoneInfo(cfg()["channel"]["timezone"])).replace(tzinfo=None)


def _hm(s: str):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def quiet(now: datetime) -> bool:
    start, end = (_hm(x) for x in cfg()["schedule"]["quiet_hours"])
    t = now.hour * 60 + now.minute
    return (start <= t or t < end) if start > end else (start <= t < end)


def make(kind: str, idea_id: int | None = None, script: dict | None = None) -> int:
    """Write (unless a script is given), render, and queue one video. Returns its id."""
    from . import render  # heavy imports only when rendering
    with db.conn() as c:
        idea = (c.execute("SELECT * FROM ideas WHERE id=?", (idea_id,)).fetchone() if idea_id
                else None if script else ideas.next_idea(kind))
        if not script and idea is None:
            raise RuntimeError("no ideas left: run `thoma ideas`")
        vid = c.execute("INSERT INTO videos (idea_id, kind, status, title, created, updated) VALUES (?,?,?,?,?,?)",
                        (idea["id"] if idea else None, kind, "writing", "", db.now(), db.now())).lastrowid
    try:
        if script is None:
            script = writer.write(idea, kind)
        db.update_video(vid, status="rendering", title=script["title"], script=json.dumps(script, ensure_ascii=False))
        out_dir = OUT / f"{vid:04d}-{kind}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))
        path = render.render(script, kind, out_dir)  # adds chapter times to the script
        (out_dir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))
        db.update_video(vid, status="ready", path=str(path), script=json.dumps(script, ensure_ascii=False))
        if idea:
            with db.conn() as c:
                col = "long_made" if kind == "long" else "shorts_made"
                c.execute(f"UPDATE ideas SET {col}={col}+1 WHERE id=?", (idea["id"],))
    except Exception as e:
        db.update_video(vid, status="failed", error=str(e)[:1000])
        raise
    if not cfg()["publish"]["auto_publish"]:
        mid = notify.send_file(path, f"#{vid} {kind} ready: {script['title']}\nReply /approve {vid} or /reject {vid}")
        db.set_kv(f"telegram_msg:{vid}", mid)
    return vid


def publish(video_id: int) -> bool:
    """Upload to every platform for its kind. Platforms that already succeeded are skipped,
    so calling this again retries only the failures. Returns True when all are done."""
    from .publish import meta, platforms_for, telegram, youtube
    v = db.video(video_id)
    script, path = json.loads(v["script"]), Path(v["path"])
    with db.conn() as c:
        done = {r["platform"]: r for r in c.execute("SELECT * FROM uploads WHERE video_id=?", (video_id,))}
    ok = True
    for platform in platforms_for(v["kind"]):
        if platform in done and done[platform]["status"] == "ok":
            continue
        try:
            if platform == "youtube":
                res = youtube.upload(path, script, v["kind"], public=True)
            elif platform == "telegram":
                res = telegram.share(path, script, v["kind"], video_id)
            else:
                res = meta.upload(platform, path, script, v["kind"])
            row = (video_id, platform, "ok", res["remote_id"], res["url"], None, db.now())
        except Exception as e:
            log.exception("upload to %s failed", platform)
            ok = False
            row = (video_id, platform, "failed", None, None, str(e)[:500], db.now())
        with db.conn() as c:
            c.execute("INSERT OR REPLACE INTO uploads VALUES (?,?,?,?,?,?,?)", row)
    with db.conn() as c:
        links = [f"{r['platform']}: {r['url'] or r['error']}" for r in
                 c.execute("SELECT * FROM uploads WHERE video_id=?", (video_id,))]
    if ok:
        db.update_video(video_id, status="published")
    notify.send(f"#{video_id} {'published' if ok else 'partly published'}: {v['title']}\n" + "\n".join(links))
    return ok


def _handle_owner_replies():
    for cmd, arg in notify.commands():
        vid = int(arg.split()[0]) if arg.split() and arg.split()[0].isdigit() else None
        v = db.video(vid) if vid else None
        if cmd == "approve" and v and v["status"] == "ready":
            db.update_video(vid, status="approved")
            notify.send(f"#{vid} approved, goes out in the next slot.")
        elif cmd == "reject" and v and v["status"] in ("ready", "approved"):
            db.update_video(vid, status="rejected", error=arg)
            notify.send(f"#{vid} rejected.")
        elif cmd == "topic" and arg:
            notify.send(f"Got it: '{arg}' is next in line (idea #{ideas.add_topic(arg)}).")
        elif cmd == "status":
            notify.send(status_text())
        elif cmd in ("pause", "resume"):
            db.set_kv("paused", cmd == "pause")
            notify.send(f"Studio {cmd}d.")


def _made(kind: str, since: datetime) -> int:
    with db.conn() as c:
        return c.execute("SELECT COUNT(*) FROM videos WHERE kind=? AND status NOT IN ('failed','rejected')"
                         " AND created >= ?", (kind, since.isoformat())).fetchone()[0]


def _failed_today(kind: str, today: datetime) -> int:
    with db.conn() as c:
        return c.execute("SELECT COUNT(*) FROM videos WHERE kind=? AND status='failed' AND created >= ?",
                         (kind, today.isoformat())).fetchone()[0]


def _due_kind(now: datetime) -> str | None:
    s = cfg()["schedule"]
    # created timestamps are machine-local; compare against machine-local midnight
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    if DAYS[now.weekday()] in s["long_days"] and _made("long", today) == 0 \
            and _made("long", week) < s["longs_per_week"] and _failed_today("long", today) < 2:
        return "long"
    if _made("short", today) < s["shorts_per_day"] and _failed_today("short", today) < 3:
        return "short"
    return None


def _publish_due(now: datetime):
    auto = cfg()["publish"]["auto_publish"]
    for kind, slots in cfg()["schedule"]["publish_times"].items():
        for slot in slots:
            key = f"slot:{now.date()}:{kind}:{slot}"
            mins_late = now.hour * 60 + now.minute - _hm(slot)
            if mins_late < 0 or db.get_kv(key):
                continue
            if mins_late > 180:  # missed it (machine was off); don't post at odd hours
                db.set_kv(key, "missed")
                continue
            states = ("approved", "ready") if auto else ("approved",)
            with db.conn() as c:
                v = c.execute(f"SELECT id FROM videos WHERE kind=? AND status IN ({','.join('?' * len(states))})"
                              " ORDER BY id LIMIT 1", (kind, *states)).fetchone()
            if v:
                db.set_kv(key, v["id"])
                publish(v["id"])
    # retry partial uploads from earlier slots
    with db.conn() as c:
        retry = [r[0] for r in c.execute(
            "SELECT DISTINCT video_id FROM uploads WHERE status='failed' AND created >= ?",
            ((datetime.now() - timedelta(days=1)).isoformat(),))]
    for vid in retry:
        if db.video(vid)["status"] != "published":
            publish(vid)


def cleanup():
    """Free disk: long videos after keep_long_days, published Shorts right away, failures after a few days."""
    st = cfg().get("storage", {})
    now = datetime.now()
    with db.conn() as c:
        rows = c.execute("SELECT id, kind, status, path, created FROM videos WHERE path IS NOT NULL").fetchall()
    for r in rows:
        folder = Path(r["path"]).parent
        if not folder.exists():
            continue
        age = (now - datetime.fromisoformat(r["created"])).days
        if (r["kind"] == "long" and age >= st.get("keep_long_days", 14)) \
                or (r["kind"] == "short" and r["status"] == "published" and st.get("delete_published_shorts", True)) \
                or (r["status"] in ("failed", "rejected") and age >= st.get("keep_failed_days", 3)):
            shutil.rmtree(folder, ignore_errors=True)
            log.info("cleanup: removed %s", folder.name)
    for f in (OUT / "preview").glob("*"):  # stills from `thoma preview`
        if time.time() - f.stat().st_mtime > 86400:
            f.unlink()


def tick():
    lock = (DATA / "tick.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.info("another tick is running")
        return
    now = local_now()
    _handle_owner_replies()
    cleanup()
    if db.get_kv("paused") or quiet(now):
        return
    try:
        last = db.get_kv("ideas_refreshed")
        if not last or datetime.fromisoformat(last) < datetime.now() - timedelta(hours=cfg()["sources"]["refresh_hours"]):
            ideas.refresh()
        _publish_due(now)
        kind = _due_kind(now)
        if kind:
            vid = make(kind)
            log.info("made #%d (%s)", vid, kind)
            _publish_due(local_now())
    except AllProvidersFailed as e:
        log.warning("no LLM available right now, will retry next tick: %s", e)
    except Exception as e:
        log.exception("tick failed")
        notify.send(f"Studio error: {str(e)[:300]}")


def status_text() -> str:
    with db.conn() as c:
        rows = c.execute("SELECT id, kind, status, title FROM videos ORDER BY id DESC LIMIT 12").fetchall()
        n_ideas = c.execute("SELECT COUNT(*) FROM ideas WHERE status='new'").fetchone()[0]
    benched = {k: v for k, v in db.get_kv("llm_benched", {}).items()
               if v > datetime.now().timestamp()}
    lines = [f"ideas waiting: {n_ideas}   paused: {bool(db.get_kv('paused'))}",
             f"LLM providers cooling down: {', '.join(benched) or 'none'}"]
    lines += [f"#{r['id']:<4} {r['kind']:<5} {r['status']:<10} {r['title'][:60]}" for r in rows]
    return "\n".join(lines)
