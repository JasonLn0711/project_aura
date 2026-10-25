"""Offline migration of completed recording packages to mixed M4A retention."""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import uuid

from aura.audio.retention import AudioCleanupIncomplete, complete_recording_m4a, prepare_recording_m4a, recording_audio_plan


@contextmanager
def service_lock(root):
    """Use the same exclusive lock as aura.service; never edit a live owner's DB."""
    lock = (root / "service.lock").open("a+")
    try:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            if not lock.read(1):
                lock.write("0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock.close()
        raise RuntimeError("AURA service is running; leave active recordings intact and retry after the service exits") from exc
    try:
        yield
    finally:
        lock.close()


def cleanup_manifest(manifest, *, apply=False, target_dbfs=-20.0, persist=None):
    try:
        plan = recording_audio_plan(manifest)
        if not apply:
            return dict(status="preview", **plan)
        output = prepare_recording_m4a(manifest, target_dbfs)
        result = complete_recording_m4a(manifest, output, persist=persist)
        return dict(status="cleaned", manifest=str(manifest), **result)
    except AudioCleanupIncomplete as exc:
        return dict(manifest=str(manifest), **exc.report)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        return dict(status="skipped", manifest=str(manifest), reason=str(exc))


def cleanup_service_sessions(root, *, apply=False):
    root = Path(root).expanduser().resolve()
    database = root / "sessions.sqlite3"
    if not database.is_file():
        yield dict(status="skipped", root=str(root), reason="No session database")
        return
    with closing(sqlite3.connect(f"{database.as_uri()}?mode={'rw' if apply else 'ro'}", uri=True)) as db:
        sessions = [json.loads(row[0]) for row in db.execute("SELECT data FROM sessions")]
        for session in sessions:
            sid = session["id"]
            try:
                valid_id = str(uuid.UUID(sid)) == sid
            except (ValueError, TypeError, AttributeError):
                valid_id = False
            if not valid_id:
                yield dict(status="skipped", session_id=sid, reason="Invalid session ID")
                continue
            unresolved = db.execute("SELECT 1 FROM jobs WHERE session=? AND "
                                    "(state IN ('queued','running') OR (kind='chunk' AND state='failed')) LIMIT 1", (sid,)).fetchone()
            if (session["state"] != "ready" or session.get("source_path") or session.get("producer_connected")
                    or any(i.get("status") == "pending" for i in session.get("asr_issues", [])) or unresolved
                    or session.get("diarization", {}).get("state") in ("failed", "loading", "ready", "running", "recovering")):
                yield dict(status="skipped", session_id=sid, reason="Imported, active, unfinished, or recoverable session")
                continue
            manifest = root / "sessions" / sid / "session.json"

            def persist(output):
                session["artifacts"].pop("wav", None)
                session["artifacts"].pop("mp3", None)
                session["artifacts"]["m4a"] = str(output)
                session["options"]["audio_format"] = "m4a"
                session["updated_at"] = datetime.now(timezone.utc).isoformat()
                with db:
                    db.execute("UPDATE sessions SET data=? WHERE id=?", (json.dumps(session, ensure_ascii=False), sid))
                    db.execute("INSERT INTO events(session,data) VALUES (?,?)", (sid, json.dumps({"type": "session.updated", "session": session})))
                    # Cached command snapshots must not reintroduce obsolete artifact paths.
                    db.execute("DELETE FROM commands WHERE instr(command, ?) > 0 OR instr(result, ?) > 0", (sid, sid))

            yield dict(session_id=sid, **cleanup_manifest(manifest, apply=apply,
                        target_dbfs=session["options"].get("target_dbfs", -20.0), persist=persist))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, help="AURA service data directory (must be offline for --apply)")
    parser.add_argument("--legacy-root", type=Path, help="Project directory containing NAME/NAME_session/session.json")
    parser.add_argument("--apply", action="store_true", help="Convert, validate, update references, then remove redundant audio")
    args = parser.parse_args(argv)
    if args.data_root is None and args.legacy_root is None:
        parser.error("Specify --data-root and/or --legacy-root explicitly")
    results = []

    def emit(result):
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    if args.legacy_root:
        for manifest in sorted(args.legacy_root.expanduser().glob("*/*_session/session.json")):
            emit(cleanup_manifest(manifest, apply=args.apply))
    if args.data_root:
        root = args.data_root.expanduser().resolve()
        try:
            if args.apply and (root / "sessions.sqlite3").is_file():
                with service_lock(root):
                    for result in cleanup_service_sessions(root, apply=True):
                        emit(result)
            else:
                for result in cleanup_service_sessions(root):
                    emit(result)
        except (OSError, RuntimeError) as exc:
            emit(dict(status="blocked", root=str(root), reason=str(exc)))
    print(json.dumps(dict(summary=True, cleaned=sum(r["status"] == "cleaned" for r in results),
                          skipped=sum(r["status"] == "skipped" for r in results),
                          incomplete=sum(r["status"] == "incomplete" for r in results),
                          blocked=sum(r["status"] == "blocked" for r in results),
                          released_bytes=sum(r.get("released_bytes", 0) for r in results)), ensure_ascii=False))
    return 1 if any(r["status"] in ("blocked", "incomplete") for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
