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


def video_file(v) -> Path:
    """Where the video is on THIS machine (the database may have come from another one via backup.sh)."""
    p = Path(v["path"])
    return p if p.exists() else OUT / p.parent.name / p.name


def local_now() -> datetime:
    return datetime.now(ZoneInfo(cfg()["channel"]["timezone"])).replace(tzinfo=None)


def _hm(s: str):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def write_video(kind: str, idea_id: int | None = None, script: dict | None = None) -> int:
    """Write and check a script (unless one is given). The video waits as 'scripted' until rendered."""
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
    except Exception as e:
        db.update_video(vid, status="failed", error=str(e)[:1000])
        raise
    out_dir = OUT / f"{vid:04d}-{kind}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))
    db.update_video(vid, status="scripted", title=script["title"], script=json.dumps(script, ensure_ascii=False))
    if kind in cfg()["voice"].get("record", []):  # the owner narrates this kind: wait for their recording
        ask_recording(vid)
    if idea:
        with db.conn() as c:
            col = "long_made" if kind == "long" else "shorts_made"
            c.execute(f"UPDATE ideas SET {col}={col}+1 WHERE id=?", (idea["id"],))
    return vid


def render_video(vid: int) -> Path:
    """Voice and render a scripted video, then send it to the owner. If no voice has quota left, it
    goes back to 'scripted' and is rendered on a later tick (finished voice chunks are kept)."""
    from . import render, voice  # heavy imports only when rendering
    v = db.video(vid)
    kind, script = v["kind"], json.loads(v["script"])
    out_dir = OUT / f"{vid:04d}-{kind}"
    if writer.words(script) > writer.FORMATS[kind]["words"][1] and v["idea_id"]:
        script = rewrite_to_length(vid)
    db.update_video(vid, status="rendering")
    try:
        path = render.render(script, kind, out_dir)  # adds chapter times to the script
    except voice.VoiceUnavailable:
        db.update_video(vid, status="scripted")
        raise
    except voice.RecordingMismatch as e:
        (out_dir / "owner_voice.wav").rename(out_dir / "owner_voice.rejected.wav")
        db.update_video(vid, status="recording")
        notify.send(f"#{vid}: your recording doesn't follow the script ({e}). Please record the reading sheet "
                    f"again and reply to it, or send /ai {vid} to use the AI voice.", db.get_kv(f"record_sheet:{vid}"))
        raise
    except Exception as e:
        db.update_video(vid, status="failed", error=str(e)[:1000])
        raise
    (out_dir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))
    db.update_video(vid, status="ready", path=str(path), script=json.dumps(script, ensure_ascii=False))
    _announce(vid, script, kind, path)
    return path


def rewrite_to_length(vid: int) -> dict:
    """A script written before the length limit changed (owner, 2026-10-30: 5 minutes at most) is written
    again at the new length. The topic's research is cached, so this is one writing pass plus the check."""
    v = db.video(vid)
    with db.conn() as c:
        idea = c.execute("SELECT * FROM ideas WHERE id=?", (v["idea_id"],)).fetchone()
    log.info("#%d is %d words, over the %s limit: rewriting it", vid, writer.words(json.loads(v["script"])), v["kind"])
    script = writer.write(idea, v["kind"])
    (OUT / f"{vid:04d}-{v['kind']}" / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))
    db.update_video(vid, title=script["title"], script=json.dumps(script, ensure_ascii=False))
    return script


def render_scripted() -> int:
    """Render every waiting script, oldest first (a long video before its Short). Stops when the voice
    quota is used up for today. Returns how many were rendered."""
    from .voice import RecordingMismatch, VoiceUnavailable
    done = 0
    with db.conn() as c:
        # a render cut off midway (laptop shut, process stopped) stays 'rendering': queue it again. A real
        # render takes ~30 min; its saved voice takes mean no voice quota is spent twice.
        stale = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
        c.execute("UPDATE videos SET status='scripted' WHERE status='rendering' AND updated < ?", (stale,))
        waiting = [r[0] for r in c.execute("SELECT id FROM videos WHERE status='scripted' ORDER BY id")]
    for vid in waiting:
        try:
            render_video(vid)
            done += 1
        except VoiceUnavailable as e:
            log.warning("voice quota used up, #%d and later wait for the next run: %s", vid, e)
            break
        except RecordingMismatch:
            continue  # the owner was asked to record again
        except Exception as e:
            log.exception("render of #%d failed", vid)
            notify.send(f"#{vid} failed to render: {str(e)[:300]}")
    return done


def series(n: int = 10, render: bool = True) -> list[int]:
    """'How it works' batch: for each of the next n topics in assets/how_it_works.txt, write the long
    video and its teaser Short (scripts checked by the reviewer), then render as much as today's voice
    quota allows. The rest is rendered by later runs or by the daemon's ticks. When the first writer's
    drafts keep failing the checks, the next writer in llm.roles.write gets a turn."""
    ideas.seed_how_it_works()
    with db.conn() as c:
        todo = c.execute("SELECT id, topic FROM ideas WHERE source='how-it-works' AND status='new' AND long_made=0"
                         " ORDER BY priority DESC, id DESC LIMIT ?", (n,)).fetchall()
    made = []
    writers = list(cfg()["llm"]["roles"]["write"])
    for idea in todo:
        for kind in ("long", "short"):
            for k, name in enumerate(writers):
                cfg()["llm"]["roles"]["write"] = writers[k:]
                try:
                    made.append(write_video(kind, idea["id"]))
                    log.info("series: wrote #%d %s for %r", made[-1], kind, idea["topic"])
                    break
                except Exception as e:  # incl. AllProvidersFailed: a reply that never parsed is that writer failing
                    log.warning("series: %s by %s for %r failed: %s", kind, name, idea["topic"], e)
            else:
                notify.send(f"Could not write the {kind} video on '{idea['topic']}'; see the log.")
                break  # no teaser without its long video
        cfg()["llm"]["roles"]["write"] = writers
    if render:
        render_scripted()
    return made


def make(kind: str, idea_id: int | None = None, script: dict | None = None) -> int:
    """Write (unless a script is given), render, and queue one video. Returns its id."""
    vid = write_video(kind, idea_id, script)
    if db.video(vid)["status"] == "scripted":  # (not when it waits for the owner's recording)
        render_video(vid)
    return vid


def _announce(vid: int, script: dict, kind: str, path: Path):
    if cfg()["publish"]["mode"] == "approve":
        note = f"Reply /approve {vid} or /reject {vid}"
    else:
        note = f"It gets the next free slot automatically. /reject {vid} to drop it"
    mid = notify.send_file(path, f"#{vid} {kind} ready: {script['title']}\n{note}")
    db.set_kv(f"telegram_msg:{vid}", mid)
    upload_pack(script, kind, path.parent, mid)
    return vid


RECORD_TIPS = """HOW TO RECORD (about {minutes} minutes)
- One take, top to bottom. Phone 15-20 cm from your mouth, in a quiet room with soft things around
  (a bedroom with curtains beats an empty hall). Fan off.
- Talk to one friend, not to a microphone: brisk, warm, smiling, the way you'd explain it over tea.
  Don't read word by word; small changes in wording are fine.
- Fluffed a line? Pause a second and say the whole sentence again. The studio cuts the first try out.
- Lines in [brackets] are chapter names: don't read them.
- Then reply to THIS message with the voice note (or an audio file under 20 MB, e.g. .m4a/.mp3).
  Bigger file? Copy it to the laptop and run: uv run thoma record {vid} <file>
- No time? Send /ai {vid} and Thoma's AI voice reads it."""


def reading_sheet(vid: int, script: dict) -> str:
    """The script as the owner reads it aloud: paragraphs per scene, chapter names in brackets."""
    import re
    n = sum(len(sc["say"].split()) for sc in script["scenes"])
    lines = [script["title"], "", RECORD_TIPS.format(minutes=round(n / 150), vid=vid), "", "-" * 40, ""]
    for sc in script["scenes"]:
        if sc.get("chapter"):
            lines += ["", f"[{sc['chapter']}]"]
        lines.append(re.sub(r"<[^>]{1,30}>", "", sc["say"]).replace("*", "").strip())
    return "\n".join(lines) + "\n"


def ask_recording(vid: int, why: str = "") -> None:
    """Send the owner the reading sheet; the video waits as 'recording' until their audio arrives
    (or voice.record_wait_hours pass, then the AI voice reads it)."""
    v = db.video(vid)
    script = json.loads(v["script"])
    db.update_video(vid, status="recording")
    db.set_kv(f"record_asked:{vid}", db.now())
    hours = cfg()["voice"].get("record_wait_hours", 20)
    mid = notify.send_text_file(f"thoma-{vid}-read-aloud.txt", reading_sheet(vid, script),
                                f"#{vid} {v['kind']}: '{script['title']}' is written. {why}Please narrate it: the "
                                f"reading sheet and tips are in this file. Reply to this message with your recording. "
                                f"(No recording in {hours} h: the AI voice reads it, so no slot is missed.)")
    if mid:
        db.set_kv(f"record_msg:{mid}", vid)
        db.set_kv(f"record_sheet:{vid}", mid)


def save_recording(vid: int, src: Path) -> Path:
    """The owner's narration -> out/<id>/owner_voice.wav; the next render uses it instead of the AI voice."""
    import subprocess
    import imageio_ffmpeg
    v = db.video(vid)
    out = OUT / f"{vid:04d}-{v['kind']}" / "owner_voice.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(src), "-ac", "1",
                    "-ar", "48000", str(out)], check=True)
    db.update_video(vid, status="scripted", error=None)
    log.info("#%d: owner's recording saved (%s)", vid, src.name)
    return out


def _recording_from_telegram(info: dict) -> None:
    import re
    with db.conn() as c:
        waiting = [r[0] for r in c.execute("SELECT id FROM videos WHERE status='recording' ORDER BY id")]
    hint = re.search(r"#(\d+)|^\s*(\d+)\s*$", info.get("caption") or "")
    vid = (int(hint.group(1) or hint.group(2)) if hint else db.get_kv(f"record_msg:{info.get('reply_to')}")
           or (waiting[0] if len(waiting) == 1 else None))
    if not vid or not db.video(vid):
        notify.send("Got a recording, but which video is it for? Reply to that video's reading sheet, or send it "
                    f"again with the number as the caption (e.g. #12). Waiting for a recording: {waiting or 'none'}.")
        return
    if info.get("size", 0) > 20 << 20:
        notify.send(f"That file is over 20 MB, which Telegram bots can't fetch. Send it as a voice note or .m4a, "
                    f"or copy it to the laptop and run: uv run thoma record {vid} <file>")
        return
    folder = OUT / f"{vid:04d}-{db.video(vid)['kind']}"
    folder.mkdir(parents=True, exist_ok=True)
    take = notify.download(info["file_id"], folder / ("owner_take" + Path(info.get("name") or "x.ogg").suffix))
    save_recording(vid, take)
    notify.send(f"Got your recording for #{vid}. Cleaning it up and matching the visuals to your words now; "
                "the video comes here when it's done.")


def _recording_timeouts() -> None:
    """A recording that never came: the AI voice reads the script, so the slot isn't missed."""
    hours = cfg()["voice"].get("record_wait_hours", 20)
    with db.conn() as c:
        waiting = [r[0] for r in c.execute("SELECT id FROM videos WHERE status='recording'")]
    for vid in waiting:
        asked = db.get_kv(f"record_asked:{vid}")
        if asked and datetime.fromisoformat(asked) < datetime.now() - timedelta(hours=hours):
            db.update_video(vid, status="scripted")
            notify.send(f"No recording for #{vid} after {hours} h, so the AI voice reads it. "
                        f"(/record {vid} if you'd still like to narrate it.)")


def remember_feedback(v, verdict: str, note: str = "") -> None:
    """Owner's verdicts and notes, fed into every future script brief (writer.owner_feedback)."""
    items = db.get_kv("owner_feedback", [])
    items.append({"video": v["id"], "kind": v["kind"], "title": v["title"], "verdict": verdict, "note": note,
                  "at": db.now()})
    db.set_kv("owner_feedback", items[-40:])


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
    remember_feedback(v, "fix", feedback)
    new = writer.revise(script, kind, feedback, idea, times)
    changed = [i for i, (a, b) in enumerate(zip(script["scenes"], new["scenes"]), 1) if a != b]
    changed += list(range(len(script["scenes"]) + 1, len(new["scenes"]) + 1))
    db.update_video(vid, status="rendering", title=new["title"], script=json.dumps(new, ensure_ascii=False))
    (out_dir / "script.json").write_text(json.dumps(new, indent=2, ensure_ascii=False))
    if changed and (out_dir / "owner_voice.wav").exists():  # their old recording no longer matches the words
        (out_dir / "owner_voice.wav").rename(out_dir / "owner_voice.old.wav")
        ask_recording(vid, f"The fix changed scene(s) {', '.join(map(str, changed))}, so it needs a new recording. ")
        return
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
    related = ""
    if script.get("related"):  # a teaser Short: YouTube's API can't set its link, the Studio app can
        related = (f"\n\nRelated video (the Short's link to the full video): #{script['related']['video']} "
                   f"'{script['related']['title']}'. Once that video is public: YouTube Studio -> this Short -> "
                   "Edit -> Related video -> pick it.")
    notify.send(f"UPLOAD PACK\n\nTitle:\n{script['title']}\n\nDescription:\n{caption(script, kind, 'youtube')}\n\n"
                f"Tags:\n{tags}\n\nPin this comment:\n{script.get('pinned_comment', '')}{related}", reply_to=reply_to)
    thumb = out_dir / "thumbnail.jpg"
    if kind == "long" and thumb.exists():
        notify.send_photo(thumb, "Thumbnail (1280x720)", reply_to=reply_to)
    cover = out_dir / "cover.jpg"
    if kind == "short" and cover.exists():
        notify.send_photo(cover, "Cover image for Instagram/Facebook Reels (it is also the Short's first frame)",
                          reply_to=reply_to)


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
    script, path = json.loads(v["script"]), video_file(v)
    now = local_now()
    if at is None and v["publish_at"]:
        at = datetime.fromisoformat(v["publish_at"])
    if at is None:
        after = now + timedelta(minutes=30)
        full = _full_video(script)
        if full is not None:  # a teaser Short goes out after its long video, so it can link to it
            if full["status"] not in ("scheduled", "published") or not full["publish_at"]:
                log.info("#%d waits for its long video #%d to be scheduled", video_id, full["id"])
                return False
            after = max(after, datetime.fromisoformat(full["publish_at"]))
        free = [t for t in slots(v["kind"], after, 24 * 21) if t.isoformat() not in _taken(v["kind"])]
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


def _full_video(script: dict):
    """The long video a teaser Short points to, unless it was dropped (then the Short goes out alone)."""
    rel = script.get("related")
    v = db.video(rel["video"]) if rel else None
    return v if v and v["status"] not in ("failed", "rejected") else None


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
                    res = meta.upload(platform, video_file(v), json.loads(v["script"]), v["kind"])
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
            remember_feedback(v, "approved", arg.split(maxsplit=1)[1] if len(arg.split()) > 1 else "")
            writer.save_example(json.loads(v["script"]), v["kind"], vid)
            notify.send(f"#{vid} approved; it goes into the next free slot.")
        elif cmd == "reject" and v and v["status"] in ("ready", "approved", "scheduled"):  # (a rejected video can still be /fix-ed)
            if v["status"] == "scheduled":
                _cancel_youtube(vid)
            reason = arg.split(maxsplit=1)[1] if len(arg.split()) > 1 else ""
            db.update_video(vid, status="rejected", error=reason or "rejected by owner", publish_at=None)
            remember_feedback(v, "rejected", reason)
            notify.send(f"#{vid} rejected." + ("" if reason else f" Tip: add why (/reject {vid} too technical) "
                                                "and every future script learns from it."))
        elif cmd == "recording":
            try:
                _recording_from_telegram(json.loads(arg))
            except Exception as e:
                log.exception("recording from Telegram failed")
                notify.send(f"Could not use that recording: {str(e)[:200]}")
        elif cmd in ("ai", "aivoice") and v and v["status"] == "recording":
            db.update_video(vid, status="scripted")
            notify.send(f"OK, the AI voice reads #{vid}.")
        elif cmd == "record" and v and v["status"] in ("scripted", "recording", "ready", "approved", "failed", "rejected"):
            ask_recording(vid)
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
        elif cmd in ("plan", "week", "schedule"):
            notify.send(plan_text())
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
            lined_up = c.execute("SELECT COUNT(*) FROM videos WHERE kind=? AND (status IN ('writing','scripted','rendering',"
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
        folder = video_file(r).parent
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
    _recording_timeouts()
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
        if render_scripted() == 0 and _voice_waiting():
            return  # scripts are waiting for tomorrow's voice quota; don't write more yet
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


def _voice_waiting() -> bool:
    with db.conn() as c:
        return c.execute("SELECT COUNT(*) FROM videos WHERE status='scripted'").fetchone()[0] > 0


def plan_text(days: int = 7) -> str:
    """The coming week, slot by slot: which video goes out then, and what is still missing."""
    now = local_now()
    with db.conn() as c:
        booked = {(r["kind"], r["publish_at"]): r for r in c.execute(
            "SELECT id, kind, title, publish_at FROM videos WHERE status IN ('scheduled','published')"
            " AND publish_at > ?", (now.isoformat(),))}
        # approved videos take the earliest free slots first, then the ones still waiting for you
        queue = {k: list(c.execute("SELECT id, status, title FROM videos WHERE kind=? AND status IN "
                                   "('approved','ready','writing','scripted','recording','rendering') ORDER BY status != 'approved', id", (k,)))
                 for k in ("long", "short")}
    state = {"approved": "approved", "ready": "needs your /approve", "writing": "being made",
             "scripted": "script done, waiting for voice", "rendering": "being made",
             "recording": "waiting for your recording"}
    lines, gaps = [f"Plan for the next {days} days:"], 0
    for t, kind in sorted((t, k) for k in ("long", "short") for t in slots(k, now, days * 24)):
        r = booked.get((kind, t.isoformat()))
        if r:
            what = f"#{r['id']} {r['title'][:45]} (scheduled)"
        elif queue[kind]:
            q = queue[kind].pop(0)
            what = f"#{q['id']} {q['title'][:45] or '...'} ({state[q['status']]})"
        else:
            what, gaps = "empty: made automatically before then", gaps + 1
        lines.append(f"{_when(t)}  {kind:<5} {what}")
    if gaps and db.get_kv("paused"):
        lines.append("The studio is paused, so empty slots stay empty. Send /resume.")
    return "\n".join(lines)


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
