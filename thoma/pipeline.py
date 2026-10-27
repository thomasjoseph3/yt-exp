"""The production line and the scheduler that runs it.

make()      idea -> script -> render -> 'ready'
schedule()  'approved' (or 'ready' in auto mode) -> uploaded now, released at its slot
tick()      one scheduler pass: read owner replies, refresh ideas, make videos for the
            slots coming up in the next plan_ahead_hours, schedule finished ones.

Built for a machine that is only on part of the day (e.g. overnight): videos are made
ahead and uploaded with a release time, and YouTube publishes them at that time by itself.
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
    if cfg()["publish"]["mode"] == "approve":
        note = f"Reply /approve {vid} or /reject {vid}"
    else:
        note = f"It gets the next free slot automatically. /reject {vid} to drop it"
    mid = notify.send_file(path, f"#{vid} {kind} ready: {script['title']}\n{note}")
    db.set_kv(f"telegram_msg:{vid}", mid)
    upload_pack(script, kind, path.parent, mid)
    return vid


def fix(vid: int, feedback: str) -> None:
    """Owner's correction: rewrite only the scenes they mean, re-voice only what changed, re-render."""
    from . import render
    v = db.video(vid)
    kind, script = v["kind"], json.loads(v["script"])
    out_dir = OUT / f"{vid:04d}-{kind}"
    tlj = out_dir / "timeline.json"
    times = json.loads(tlj.read_text()).get("scenes") if tlj.exists() else None
    with db.conn() as c:
        idea = c.execute("SELECT * FROM ideas WHERE id=?", (v["idea_id"],)).fetchone() if v["idea_id"] else None
    new = writer.revise(script, kind, feedback, idea, times)
    changed = [i for i, (a, b) in enumerate(zip(script["scenes"], new["scenes"]), 1) if a != b]
    changed += list(range(len(script["scenes"]) + 1, len(new["scenes"]) + 1))
    db.update_video(vid, status="rendering", title=new["title"], script=json.dumps(new, ensure_ascii=False))
    (out_dir / "script.json").write_text(json.dumps(new, indent=2, ensure_ascii=False))
    path = render.render(new, kind, out_dir)
    (out_dir / "script.json").write_text(json.dumps(new, indent=2, ensure_ascii=False))
    db.update_video(vid, status="ready", path=str(path), script=json.dumps(new, ensure_ascii=False), publish_at=None)
    note = f"changed scene(s) {', '.join(map(str, changed))}" if changed else "no scene text changed"
    mid = notify.send_file(path, f"#{vid} fixed ({note}): {new['title']}\nReply /approve {vid}, or /fix {vid} ... again")
    db.set_kv(f"telegram_msg:{vid}", mid)
    upload_pack(new, kind, out_dir, mid)


def upload_pack(script: dict, kind: str, out_dir, reply_to=None):
    """Everything needed to post the video by hand: title, description, tags, thumbnail, pinned comment."""
    from .publish import caption
    tags = ", ".join(script.get("tags", []))
    notify.send(f"UPLOAD PACK\n\nTitle:\n{script['title']}\n\nDescription:\n{caption(script, kind, 'youtube')}\n\n"
                f"Tags:\n{tags}\n\nPin this comment:\n{script.get('pinned_comment', '')}", reply_to=reply_to)
    thumb = out_dir / "thumbnail.jpg"
    if kind == "long" and thumb.exists():
        notify.send_photo(thumb, "Thumbnail (1280x720)", reply_to=reply_to)


def slots(kind: str, after: datetime, hours: float) -> list[datetime]:
    """Posting times (local) for this kind between `after` and `after + hours`."""
    sc = cfg()["schedule"]
    days = sc.get("long_days", DAYS) if kind == "long" else DAYS
    out, day = [], after.replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= after + timedelta(hours=hours):
        if DAYS[day.weekday()] in days:
            for hm in sc["publish_times"][kind]:
                t = day + timedelta(minutes=_hm(hm))
                if after < t <= after + timedelta(hours=hours):
                    out.append(t)
        day += timedelta(days=1)
    return sorted(out)


def _taken(kind: str) -> set[str]:
    with db.conn() as c:
        return {r[0] for r in c.execute("SELECT publish_at FROM videos WHERE kind=? AND publish_at IS NOT NULL"
                                        " AND status IN ('scheduled','published')", (kind,))}


def _when(t: datetime) -> str:
    return t.strftime("%a %d %b, %H:%M")


def schedule(video_id: int, at: datetime | None = None) -> bool:
    """Upload a finished video now with its release time (the next free slot unless `at` is given).
    YouTube publishes it at that time by itself; Telegram gets the file and caption for Instagram /
    Facebook. Platforms already done are skipped, so calling it again retries only failures."""
    from .publish import meta, platforms_for, telegram, youtube
    v = db.video(video_id)
    script, path = json.loads(v["script"]), Path(v["path"])
    now = local_now()
    if at is None and v["publish_at"]:
        at = datetime.fromisoformat(v["publish_at"])
    if at is None:
        free = [t for t in slots(v["kind"], now + timedelta(minutes=30), 24 * 14)
                if t.isoformat() not in _taken(v["kind"])]
        if not free:
            return False
        at = free[0]
    tz = ZoneInfo(cfg()["channel"]["timezone"])
    release = at.replace(tzinfo=tz) if at > now + timedelta(minutes=5) else None  # None = public right away
    db.update_video(video_id, publish_at=at.isoformat(), status="scheduled")
    with db.conn() as c:
        done = {r["platform"]: r for r in c.execute("SELECT * FROM uploads WHERE video_id=?", (video_id,))}
    ok = True
    for platform in platforms_for(v["kind"]):
        if platform in done and done[platform]["status"] == "ok":
            continue
        if platform in ("instagram", "facebook") and release:
            continue  # posted by publish_due() at the slot itself, if this machine is on then
        try:
            if platform == "youtube":
                res = youtube.upload(path, script, v["kind"], release)
            elif platform == "telegram":
                res = telegram.share(path, script, v["kind"], video_id, f"at {_when(at)}" if release else "now")
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
    tip = ""
    if release and not cfg()["publish"].get("youtube_audited", False):
        tip = (f"\nUntil Google approves the API audit, set the time yourself: YouTube Studio app -> "
               f"this video -> Visibility -> Schedule -> {_when(at)}.")
    notify.send(f"#{video_id} scheduled for {_when(at)}: {v['title']}\n" + "\n".join(links) + tip)
    return ok


def publish_due():
    """Mark released videos as published, and post to direct-API platforms whose slot has come."""
    from .publish import meta, platforms_for
    now = local_now()
    with db.conn() as c:
        due = c.execute("SELECT id FROM videos WHERE status='scheduled' AND publish_at <= ?",
                        (now.isoformat(),)).fetchall()
    for r in due:
        v = db.video(r["id"])
        with db.conn() as c:
            done = {u["platform"]: u["status"] for u in c.execute("SELECT * FROM uploads WHERE video_id=?", (v["id"],))}
        for platform in platforms_for(v["kind"]):
            if platform in ("instagram", "facebook") and done.get(platform) != "ok":
                try:
                    res = meta.upload(platform, Path(v["path"]), json.loads(v["script"]), v["kind"])
                    row = (v["id"], platform, "ok", res["remote_id"], res["url"], None, db.now())
                except Exception as e:
                    log.exception("upload to %s failed", platform)
                    row = (v["id"], platform, "failed", None, None, str(e)[:500], db.now())
                with db.conn() as c:
                    c.execute("INSERT OR REPLACE INTO uploads VALUES (?,?,?,?,?,?,?)", row)
        with db.conn() as c:
            failed = c.execute("SELECT COUNT(*) FROM uploads WHERE video_id=? AND status!='ok'", (v["id"],)).fetchone()[0]
        if not failed:
            db.update_video(v["id"], status="published")


def _schedule_ready():
    states = ("approved",) if cfg()["publish"]["mode"] == "approve" else ("approved", "ready")
    with db.conn() as c:
        waiting = c.execute(f"SELECT id FROM videos WHERE status IN ({','.join('?' * len(states))}) ORDER BY id",
                            states).fetchall()
        retry = c.execute("SELECT DISTINCT u.video_id FROM uploads u JOIN videos v ON v.id=u.video_id"
                          " WHERE u.status='failed' AND v.status='scheduled'").fetchall()
    for r in [*waiting, *retry]:
        schedule(r[0])


def _cancel_youtube(vid: int):
    from .publish import youtube
    with db.conn() as c:
        row = c.execute("SELECT remote_id FROM uploads WHERE video_id=? AND platform='youtube' AND status='ok'",
                        (vid,)).fetchone()
    if row:
        youtube.unschedule(row[0])


def _handle_owner_replies():
    for cmd, arg in notify.commands():
        vid = int(arg.split()[0]) if arg.split() and arg.split()[0].isdigit() else None
        v = db.video(vid) if vid else None
        if cmd == "approve" and v and v["status"] == "ready":
            db.update_video(vid, status="approved")
            notify.send(f"#{vid} approved; it goes into the next free slot.")
        elif cmd == "reject" and v and v["status"] in ("ready", "approved", "scheduled"):  # (a rejected video can still be /fix-ed)
            if v["status"] == "scheduled":
                _cancel_youtube(vid)
            db.update_video(vid, status="rejected", error=arg, publish_at=None)
            notify.send(f"#{vid} rejected.")
        elif cmd == "topic" and arg:
            notify.send(f"Got it: '{arg}' is next in line (idea #{ideas.add_topic(arg)}).")
        elif cmd in ("short", "reel", "long") and arg:  # owner's own idea: research and make it right away
            kind = "long" if cmd == "long" else "short"
            queue = db.get_kv("make_now", []) + [[kind, ideas.add_topic(arg)]]
            db.set_kv("make_now", queue)
            notify.send(f"On it: researching and making a {kind} about '{arg}'. "
                        f"It comes here for your OK in about {'45' if kind == 'long' else '10'} minutes.")
        elif cmd in ("fix", "edit", "change") and v and arg.split(maxsplit=1)[1:]:
            if v["status"] in ("ready", "approved", "failed", "rejected"):
                db.set_kv("fix_now", db.get_kv("fix_now", []) + [[vid, arg.split(maxsplit=1)[1]]])
                notify.send(f"Fixing #{vid}: I'll change only that part and send you the new version.")
            else:
                notify.send(f"#{vid} is already {v['status']}. Send /reject {vid} first, then /fix {vid} ... "
                            "and I'll make a corrected copy.")
        elif cmd in ("publish", "now") and v and v["status"] in ("ready", "approved"):
            notify.send(f"#{vid} going out now.")
            schedule(vid, at=local_now())
        elif cmd == "status":
            notify.send(status_text())
        elif cmd in ("pause", "resume"):
            db.set_kv("paused", cmd == "pause")
            notify.send(f"Studio {cmd}d.")


def _due_kind(now: datetime) -> str | None:
    """Make videos for the slots coming up that nothing is lined up for yet."""
    sc = cfg()["schedule"]
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for kind, max_fail in (("long", 2), ("short", 3)):
        upcoming = len(slots(kind, now, sc.get("plan_ahead_hours", 36)))
        with db.conn() as c:
            lined_up = c.execute("SELECT COUNT(*) FROM videos WHERE kind=? AND (status IN ('writing','rendering',"
                                 "'ready','approved') OR (status='scheduled' AND publish_at > ?))",
                                 (kind, now.isoformat())).fetchone()[0]
            failed = c.execute("SELECT COUNT(*) FROM videos WHERE kind=? AND status='failed' AND created >= ?",
                               (kind, today.isoformat())).fetchone()[0]
        if lined_up < upcoming and failed < max_fail:
            return kind
    return None


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
    if db.get_kv("paused"):
        return
    try:
        publish_due()
        _schedule_ready()
        while db.get_kv("fix_now", []):  # owner's /fix requests first: they're waiting on them
            queue = db.get_kv("fix_now", [])
            db.set_kv("fix_now", queue[1:])
            try:
                fix(*queue[0])
            except AllProvidersFailed:
                db.set_kv("fix_now", queue[:1] + db.get_kv("fix_now", []))
                raise
            except Exception as e:
                notify.send(f"Could not fix #{queue[0][0]}: {str(e)[:300]}")
        while db.get_kv("make_now", []):  # owner's /short and /long requests jump the queue
            queue = db.get_kv("make_now", [])
            kind, idea_id = queue[0]
            db.set_kv("make_now", queue[1:])
            try:
                make(kind, idea_id)
            except AllProvidersFailed:
                db.set_kv("make_now", [[kind, idea_id]] + db.get_kv("make_now", []))  # try again next tick
                raise
            except Exception as e:
                notify.send(f"Could not make your {kind} (idea #{idea_id}): {str(e)[:300]}")
        last = db.get_kv("ideas_refreshed")
        if not last or datetime.fromisoformat(last) < datetime.now() - timedelta(hours=cfg()["sources"]["refresh_hours"]):
            ideas.refresh()
        kind = _due_kind(now)
        if kind:
            vid = make(kind)
            log.info("made #%d (%s)", vid, kind)
            _schedule_ready()
    except AllProvidersFailed as e:
        log.warning("no LLM available right now, will retry next tick: %s", e)
    except Exception as e:
        log.exception("tick failed")
        notify.send(f"Studio error: {str(e)[:300]}")


def status_text() -> str:
    with db.conn() as c:
        rows = c.execute("SELECT id, kind, status, title, publish_at FROM videos ORDER BY id DESC LIMIT 12").fetchall()
        n_ideas = c.execute("SELECT COUNT(*) FROM ideas WHERE status='new'").fetchone()[0]
    benched = {k: v for k, v in db.get_kv("llm_benched", {}).items()
               if v > datetime.now().timestamp()}
    lines = [f"ideas waiting: {n_ideas}   paused: {bool(db.get_kv('paused'))}",
             f"LLM providers cooling down: {', '.join(benched) or 'none'}"]
    lines += [f"#{r['id']:<4} {r['kind']:<5} {r['status']:<10} {(r['publish_at'] or '')[5:16]:<11} {r['title'][:55]}"
              for r in rows]
    return "\n".join(lines)
