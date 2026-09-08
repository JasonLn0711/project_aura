"""Single-owner session core: durable audio, serialized commands, bounded inference."""
import concurrent.futures
import datetime
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import threading
import uuid

from aura.audio.recording_session import RecordingSession, write_session_manifest

PROFILES = {
    "off": ("off", "off"), "light": ("light", "normal"),
    "medium": ("medium", "off"), "far-speaker": ("medium", "far-speaker"),
    "rescue-offline": ("medium", "rescue-offline"),
}
ACTIVE = {"starting", "recording", "pausing", "paused", "stopping", "draining", "importing", "refining", "exporting"}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def default_root():
    return Path(os.environ.get("AURA_DATA_DIR", Path.home() / ".local/share/project-aura")).expanduser()


def options_for(values=None):
    from aura.config import DEFAULT_LIVE_PROMPT
    result = dict(profile="light", language="zh", beam_size=5, prompt=DEFAULT_LIVE_PROMPT,
                  hotwords="", punctuation=True, target_dbfs=-20.0, diarization=False,
                  min_speakers=2, max_speakers=6, audio_format="m4a")
    values = values or {}
    if not isinstance(values, dict) or set(values) - result.keys():
        raise ValueError("Unknown transcription options")
    result.update(values)
    if result["profile"] not in PROFILES:
        raise ValueError("Unknown audio profile")
    if type(result["beam_size"]) is not int or not 1 <= result["beam_size"] <= 10:
        raise ValueError("beam_size must be between 1 and 10")
    if result["language"] not in (None, "zh", "en"):
        raise ValueError("language must be zh, en, or null for detection")
    if any(type(result[k]) is not bool for k in ("punctuation", "diarization")):
        raise ValueError("Punctuation and diarization must be boolean")
    if any(type(result[k]) is not int for k in ("min_speakers", "max_speakers")) or not 1 <= result["min_speakers"] <= result["max_speakers"] <= 20:
        raise ValueError("Invalid speaker range")
    if type(result["target_dbfs"]) not in (float, int) or not -60 <= result["target_dbfs"] <= -1:
        raise ValueError("target_dbfs must be between -60 and -1")
    if result["audio_format"] not in ("m4a", "wav", "mp3"):
        raise ValueError("Unsupported audio export format")
    for key in ("prompt", "hotwords"):
        if not isinstance(result[key], str) or len(result[key]) > 8192:
            raise ValueError(f"Invalid {key}")
    result["denoise"], result["distance"] = PROFILES[result["profile"]]
    return result


class SessionCore:
    def __init__(self, root=None, executor=None):
        self.root = Path(root or default_root()).resolve()
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        from aura.audit import AuditRecorder
        self.audit = AuditRecorder(self.root / "audit")
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.db = sqlite3.connect(self.root / "sessions.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, session TEXT NOT NULL, kind TEXT NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued');
            CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, command TEXT NOT NULL, result TEXT NOT NULL);
        """)
        self.sessions = {r["id"]: json.loads(r["data"]) for r in self.db.execute("SELECT * FROM sessions")}
        self.recordings = {}
        self.detectors = {}
        self.producers = set()
        self.pool = None
        self.execute_override = executor
        self.last_event_revision = {}
        self.shutdown = False
        for s in self.sessions.values():
            if s["state"] in ACTIVE:
                s["state"] = "recoverable"
                s["error"] = "Service restarted; preserved audio is ready for recovery"
                self._save(s)
        self.db.execute("UPDATE jobs SET state='queued' WHERE state='running'")
        self.db.commit()
        self.worker = threading.Thread(target=self._work, name="aura-inference", daemon=True)
        self.worker.start()

    def _save(self, session, event="session.updated"):
        session["updated_at"] = now()
        data = json.dumps(session, ensure_ascii=False)
        self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?)", (session["id"], data))
        snapshot = dict(session)
        # Progress events carry small deltas; transcripts travel only when their revision changes.
        if self.last_event_revision.get(session["id"]) == session["revision"]:
            snapshot.pop("transcript", None)
            snapshot.pop("live_text", None)
        self.last_event_revision[session["id"]] = session["revision"]
        self.db.execute("INSERT INTO events(session,data) VALUES (?,?)", (session["id"], json.dumps({"type": event, "session": snapshot})))
        self.db.commit()
        with self.changed:
            self.changed.notify_all()

    def _get(self, sid):
        if sid not in self.sessions:
            raise ValueError("Unknown session")
        return self.sessions[sid]

    def _available(self):
        if any(s["state"] in ACTIVE for s in self.sessions.values()):
            raise ValueError("A recording or transcription job is active; attach or finish it first")

    def _new(self, args, state):
        if args.get("source", "system_microphone") not in ("microphone", "system", "system_microphone"):
            raise ValueError("Unknown capture source")
        sid = str(uuid.uuid4())
        title = args.get("title") or "Meeting"
        if not isinstance(title, str) or len(title) > 200:
            raise ValueError("Title must contain at most 200 characters")
        session = dict(id=sid, title=title, state=state, created_at=now(), options=options_for({**self._preferences(), **args.get("options", {})}),
                       transcript="", live_text="", revision=0, edited=False, samples=0, input_sequence=0,
                       pauses=[], artifacts={}, segments=[], error=None, source=args.get("source", "system_microphone"),
                       capture_location=args.get("capture_location", "server"), producer_connected=False)
        self.sessions[sid] = session
        self.directory(sid).mkdir(mode=0o700, parents=True)
        self._save(session)
        return session

    def directory(self, sid):
        if str(uuid.UUID(sid)) != sid:
            raise ValueError("Invalid session ID")
        return self.root / "sessions" / sid

    def _job(self, s, kind, **payload):
        payload.update(options=s["options"], directory=str(self.directory(s["id"])))
        self.db.execute("INSERT INTO jobs(session,kind,payload) VALUES (?,?,?)", (s["id"], kind, json.dumps(payload)))
        self.db.commit()
        self.changed.notify_all()

    def request(self, command, args=None, request_id=None):
        args = args or {}
        if not isinstance(args, dict):
            raise ValueError("Command arguments must be an object")
        with self.lock:
            signature = json.dumps([command, args], sort_keys=True)
            cache_command = request_id and command not in ("get", "sessions", "capabilities", "export", "preferences.get")
            if cache_command:
                previous = self.db.execute("SELECT command,result FROM commands WHERE id=?", (request_id,)).fetchone()
                if previous:
                    if previous[0] != signature:
                        raise ValueError("Request ID already used for a different command")
                    return json.loads(previous[1])
            result = self._request(command, args)
            if command not in ("get", "sessions", "capabilities", "preferences.get"):
                self.audit.record("session.command", category="session", details={"command": command})
            # Snapshot before returning: callers never share mutable session state.
            result = json.loads(json.dumps(result))
            if cache_command:
                self.db.execute("INSERT INTO commands VALUES (?,?,?)", (request_id, signature, json.dumps(result)))
                self.db.commit()
            return result

    def _preferences(self):
        return {r[0]: json.loads(r[1]) for r in self.db.execute("SELECT key,value FROM preferences")}

    def _request(self, command, args):
        if command == "preferences.get":
            return self._preferences()
        if command == "preferences.set":
            values = {**self._preferences(), **args}
            options_for(values)
            self.db.executemany("INSERT OR REPLACE INTO preferences VALUES (?,?)", [(k, json.dumps(v)) for k, v in args.items()])
            self.db.commit()
            return values
        if command == "capabilities":
            import shutil
            return dict(protocol=1, ffmpeg=bool(shutil.which("ffmpeg")), profiles=list(PROFILES), capture_format="s16le/16000/mono", single_owner=True,
                        deepfilternet=bool(shutil.which("deep-filter")), clearvoice=bool(os.environ.get("AURA_CLEARVOICE_PYTHON")))
        if command == "sessions":
            return list(reversed(list(self.sessions.values())))
        if command == "get":
            s = self._get(args["session_id"])
            s["backlog"] = self.db.execute("SELECT count(*) FROM jobs WHERE session=? AND state IN ('queued','running')", (s["id"],)).fetchone()[0]
            counts = dict(self.db.execute("SELECT state,count(*) FROM jobs WHERE session=? AND kind='chunk' GROUP BY state", (s["id"],)).fetchall())
            s["work"] = {k: counts.get(k, 0) for k in ("queued", "running", "done", "failed")}
            return s
        if command == "record":
            self._available()
            if args.get("source", "system_microphone") not in ("microphone", "system", "system_microphone"):
                raise ValueError("Unknown capture source")
            if args.get("capture_location", "server") not in ("server", "client"):
                raise ValueError("Unknown capture location")
            opts = options_for({**self._preferences(), **args.get("options", {})})
            if opts["profile"] == "rescue-offline":
                raise ValueError("Rescue offline is available for imported audio")
            s = self._new(args, "starting")
            self._job(s, "load", **{k: opts[k] for k in ("prompt", "hotwords")})
            return s
        if command == "schedule":
            if args.get("capture_location", "server") != "server":
                raise ValueError("Scheduled recording requires server-side capture")
            start = datetime.datetime.fromisoformat(args["start_at"])
            end = datetime.datetime.fromisoformat(args["stop_at"])
            if start.tzinfo is None or end.tzinfo is None or start <= datetime.datetime.now(datetime.timezone.utc) or end <= start:
                raise ValueError("Use a future timezone-aware start and a later stop")
            if options_for({**self._preferences(), **args.get("options", {})})["profile"] == "rescue-offline":
                raise ValueError("Offline rescue is an import-only profile")
            s = self._new(args, "scheduled")
            s.update(start_at=start.astimezone(datetime.timezone.utc).isoformat(), stop_at=end.astimezone(datetime.timezone.utc).isoformat())
            self._save(s)
            return s
        if command == "transcribe":
            if any(s["state"] in ACTIVE - {"importing", "refining", "exporting"} for s in self.sessions.values()):
                raise ValueError("Finish the active recording before importing media")
            path = Path(args["path"]).resolve()
            if not path.is_file():
                raise ValueError("Import file is unavailable on the server")
            s = self._new(args, "importing")
            s["source_path"] = str(path)
            self._job(s, "file", path=str(path), purpose="import")
            self._save(s)
            return s
        s = self._get(args["session_id"])
        if command == "capture.failed":
            self._flush(s)
            s.update(state="failed", error=str(args.get("error", "Capture failed"))[:2000], producer_connected=False)
            self._save(s)
            return s
        if command == "producer.open":
            if s["id"] in self.producers or s["state"] != "recording":
                raise ValueError("Session is not accepting a capture producer")
            self.producers.add(s["id"])
            s["producer_connected"] = True
        elif command == "pause":
            if s["state"] not in ("recording", "pausing", "paused"):
                raise ValueError("Pause requires a recording session")
            if s["state"] == "recording":
                s["state"] = "pausing" if s["producer_connected"] else "paused"
                s["pauses"].append(dict(started_at=now(), sample=s["samples"]))
        elif command == "producer.paused":
            if s["state"] != "pausing":
                raise ValueError("Session is not pausing")
            self._flush(s)
            s["capture_paused_ack"] = True
            running = self.db.execute("SELECT count(*) FROM jobs WHERE session=? AND state='running'", (s["id"],)).fetchone()[0]
            if not running:
                s["state"] = "paused"
        elif command == "resume":
            if s["state"] != "paused":
                raise ValueError("Resume requires a paused session")
            if s["pauses"]:
                s["pauses"][-1]["resumed_at"] = now()
            self.detectors.pop(s["id"], None)
            s["capture_paused_ack"] = False
            s["state"] = "recording"
        elif command == "stop":
            if s["state"] == "scheduled":
                s["state"] = "cancelled"
                self._save(s)
                return s
            if s["state"] in ("ready", "stopping", "draining"):
                return s
            if s["state"] not in ("recording", "paused", "pausing", "starting"):
                raise ValueError("Stop requires an active recording")
            s["state"] = "stopping" if s["producer_connected"] else "draining"
            if s["state"] == "draining":
                self._flush(s)
        elif command == "producer.stopped":
            if s["state"] != "stopping":
                raise ValueError("Capture stop acknowledgement requires a stopping session")
            self._flush(s)
            s["state"] = "draining"
            s["producer_connected"] = False
            self.producers.discard(s["id"])
        elif command == "edit":
            if args.get("revision") != s["revision"]:
                raise ValueError("Transcript changed; reload the current revision before saving")
            text = args.get("text")
            if not isinstance(text, str) or len(text) > 8_000_000:
                raise ValueError("Invalid transcript text")
            self._write_text(s, "transcript.txt", text)
            s.update(transcript=text, revision=s["revision"] + 1, edited=True)
        elif command == "refine":
            self._available()
            if s["state"] not in ("ready", "recoverable", "failed"):
                raise ValueError("Refine requires a saved recording")
            path = s["artifacts"].get("wav") or s.get("source_path")
            if not path:
                from aura.audio.recording_session import recover_recording_session
                paths = recover_recording_session(self.directory(s["id"]) / "session.json")
                path = str(paths["mixed"])
                s["artifacts"]["wav"] = path
            s["state"] = "refining"
            self._job(s, "file", path=path, purpose="refine")
        elif command == "export":
            fmt = args.get("format", "txt")
            if fmt == "txt":
                text = s["transcript"]
                return {"name": f'{s["id"]}.txt', "text": text + ("\n" if text and not text.endswith("\n") else "")}
            if fmt == "refined":
                path = s["artifacts"].get("refined.txt")
                if not path:
                    raise ValueError("Run refinement before exporting refined text")
                return {"path": path}
            if fmt == "json":
                return {"name": f'{s["id"]}.json', "text": json.dumps(s, ensure_ascii=False, indent=2)}
            if fmt not in ("wav", "m4a", "mp3") or fmt not in s["artifacts"]:
                raise ValueError("Requested audio artifact is not available")
            return {"path": s["artifacts"][fmt]}
        else:
            raise ValueError(f"Unknown command: {command}")
        self._save(s)
        return s

    def _write_text(self, s, name, text):
        path = self.directory(s["id"]) / name
        temp = path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as f:
            f.write(text + ("\n" if text and not text.endswith("\n") else ""))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        s["artifacts"][name] = str(path)

    def _write_search_artifacts(self, s):
        from dataclasses import asdict
        from aura.ui.transcript_io import prepare_transcript, write_json_file
        directory = self.directory(s["id"])
        manifest_path = directory / "session.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
            "schema_version": 1, "meeting_id": s["id"], "status": "ready",
            "workflow": "import", "source_path": s.get("source_path"), "audio_tracks": {},
            "started_at": s["created_at"], "ended_at": now(),
        }
        prepared = prepare_transcript(s["transcript"], enable_punctuation=False, enable_glossary_correction=False)
        write_json_file(directory / "prepared_transcript.json", asdict(prepared))
        write_json_file(directory / "segments.json", {"segments": s.get("segments", []),
            "audio_path": s.get("source_path") or s["artifacts"].get("wav")})
        manifest.update(title=s["title"], prepared_transcript="prepared_transcript.json",
                        transcript_sha256=prepared.content_sha256, audio_profile=s["options"]["profile"])
        write_session_manifest(manifest_path, manifest)

    def ingest(self, sid, sequence, pcm, tracks):
        import numpy as np
        from aura.audio.vad import SileroStreamVAD, SpeechIntervals
        from aura.config import SAMPLE_RATE, CHUNK_SIZE
        with self.lock:
            s = self._get(sid)
            if s["state"] not in ("recording", "pausing", "stopping"):
                raise ValueError("Session is not accepting audio")
            if sequence != s["input_sequence"]:
                raise ValueError("Audio sequence mismatch; reconnect using the session snapshot")
            if not tracks or len(set(tracks)) != len(tracks) or "mixed" not in tracks or set(tracks) - {"mixed", "microphone", "system"}:
                raise ValueError("Invalid audio tracks")
            if len(pcm) != CHUNK_SIZE * 2 * len(tracks):
                raise ValueError("Audio frames must contain 30 ms of 16 kHz signed 16-bit PCM per track")
            if sid not in self.recordings:
                rec = RecordingSession.start(self.directory(sid), recording_name=sid, capture_mode=s["source"], sample_rate=SAMPLE_RATE, sample_width=2)
                rec.manifest["meeting_id"] = sid
                write_session_manifest(rec.manifest_path, rec.manifest)
                self.recordings[sid] = rec
            data = {track: pcm[i * CHUNK_SIZE * 2:(i + 1) * CHUNK_SIZE * 2] for i, track in enumerate(tracks)}
            rec = self.recordings[sid]
            rec.append_pcm(data)
            if sid not in self.detectors:
                try:
                    vad = SileroStreamVAD()
                    s["vad_backend"] = "silero-v6"
                except Exception as exc:
                    import webrtcvad
                    vad = webrtcvad.Vad(3)
                    s["vad_backend"] = "webrtc-fallback"
                    s["warning"] = str(exc)
                intervals = SpeechIntervals(CHUNK_SIZE)
                intervals.position = s["samples"]
                self.detectors[sid] = (vad, intervals, {"misses": 0})
            vad, intervals, stats = self.detectors[sid]
            try:
                speech = vad.is_speech(data["mixed"], SAMPLE_RATE)
            except Exception as exc:
                import webrtcvad
                vad = webrtcvad.Vad(3)
                self.detectors[sid] = (vad, intervals, stats)
                s.update(vad_backend="webrtc-fallback", warning=str(exc))
                speech = vad.is_speech(data["mixed"], SAMPLE_RATE)
            stats["misses"] = 0 if speech else stats["misses"] + 1
            from aura.audio.meeting_distance import meeting_distance_policy_for
            from aura.audio.vad import should_treat_frame_as_speech
            policy = meeting_distance_policy_for(s["options"]["distance"])
            samples = np.frombuffer(data["mixed"], dtype="<i2")
            rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
            s["audio_level"] = min(1.0, rms / 32768)
            speech = should_treat_frame_as_speech(speech, rms,
                intervals.active, stats["misses"], policy.live_energy_gate_rms, (policy.live_energy_bridge_ms + 29) // 30)
            chunk = intervals.push(samples, speech)
            s["samples"] += CHUNK_SIZE
            s["input_sequence"] += 1
            if chunk:
                self._enqueue_chunk(s, chunk)
            # PCM is journaled continuously; snapshots are checkpointed once per second.
            if s["input_sequence"] % 34 == 0:
                self._save(s)
            return {"state": s["state"], "input_sequence": s["input_sequence"]}

    def _enqueue_chunk(self, s, chunk):
        self.recordings[s["id"]].checkpoint()
        self._job(s, "chunk", path=str(self.directory(s["id"]) / ".capture/mixed.pcm"),
                  start=chunk.start_sample, end=chunk.end_sample, terminal=chunk.terminal)

    def _flush(self, s):
        detector = self.detectors.pop(s["id"], None)
        if detector:
            chunk = detector[1].finish()
            if chunk:
                self._enqueue_chunk(s, chunk)

    def disconnected(self, sid):
        with self.lock:
            self.producers.discard(sid)
            s = self._get(sid)
            s["producer_connected"] = False
            if s["state"] in ("recording", "pausing", "stopping"):
                self._flush(s)
                s["state"] = "paused"
                s["warning"] = "Capture producer disconnected; resume explicitly"
            self._save(s)

    def events(self, sid=None, after=0):
        with self.changed:
            rows = self.db.execute("SELECT * FROM events WHERE seq>? AND (? IS NULL OR session=?) ORDER BY seq LIMIT 100", (after, sid, sid)).fetchall()
            return [dict(seq=r["seq"], **json.loads(r["data"])) for r in rows]

    def _execute(self, kind, payload):
        if self.execute_override:
            return self.execute_override(kind, payload)
        if self.pool is None:
            self.pool = concurrent.futures.ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        from aura.session_runtime import execute
        return self.pool.submit(execute, kind, payload).result()

    def _work(self):
        while True:
            with self.changed:
                if self.shutdown:
                    break
                for s in self.sessions.values():
                    if s["state"] == "scheduled" and s["start_at"] <= now():
                        try:
                            self._available()
                            s["state"] = "starting"
                            self._job(s, "load", prompt=s["options"]["prompt"], hotwords=s["options"]["hotwords"])
                        except ValueError as exc:
                            s.update(state="failed", error=str(exc))
                        self._save(s)
                    if s["state"] in ("recording", "paused") and s.get("stop_at", "9999") <= now():
                        self._request("stop", {"session_id": s["id"]})
                row = next((r for r in self.db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY id")
                    if self.sessions[r["session"]]["state"] not in ("paused", "pausing", "recoverable", "failed")), None)
                if not row:
                    for s in self.sessions.values():
                        if s["state"] == "draining":
                            self._finalize(s)
                    if self.pool and not any(s["state"] in ACTIVE for s in self.sessions.values()):
                        self.pool.shutdown()
                        self.pool = None
                    self.changed.wait(0.2)
                    continue
                self.db.execute("UPDATE jobs SET state='running' WHERE id=?", (row["id"],))
                self.db.commit()
            try:
                result = self._execute(row["kind"], json.loads(row["payload"]))
                with self.changed:
                    s = self.sessions[row["session"]]
                    if row["kind"] == "load":
                        s["runtime"] = result
                        if s["state"] == "starting":
                            s["state"] = "recording"
                    elif row["kind"] == "chunk":
                        text = result["text"].strip()
                        if text:
                            from aura.asr.file_pipeline import format_timestamp
                            from dataclasses import asdict
                            from aura.review import ReviewSegment
                            s.setdefault("segments", []).append(asdict(ReviewSegment(
                                f'live-{result["start_sample"]}', round(result["start_sample"] / 16),
                                round(result["end_sample"] / 16), text)))
                            s["live_text"] += f'[{format_timestamp(result["start_sample"] / 16000)}] {text}\n'
                            if not s["edited"]:
                                s["transcript"] = s["live_text"]
                                s["revision"] += 1
                            self._write_text(s, "live.txt", s["live_text"])
                    elif row["kind"] == "export":
                        s["artifacts"][s["options"]["audio_format"]] = result["path"]
                        s["state"] = "ready"
                    else:
                        purpose = json.loads(row["payload"])["purpose"]
                        self._write_text(s, "refined.txt" if purpose == "refine" else "transcript.txt", result["text"])
                        if purpose == "import":
                            if not s["edited"]:
                                s["transcript"] = result["text"]
                            s["segments"] = result.get("segments", [])
                            s["revision"] += 1
                            if s["edited"]:
                                self._write_text(s, "transcript.txt", s["transcript"])
                        else:
                            from aura.ui.transcript_io import write_json_file
                            write_json_file(self.directory(s["id"]) / "refined_segments.json", result.get("segments", []))
                        self._write_search_artifacts(s)
                        s["state"] = "ready"
                    self.db.execute("UPDATE jobs SET state='done' WHERE id=?", (row["id"],))
                    if s["state"] == "pausing" and s.get("capture_paused_ack"):
                        s["state"] = "paused"
                    self._save(s)
            except Exception as exc:
                with self.changed:
                    s = self.sessions[row["session"]]
                    s.update(state="failed", error=str(exc))
                    self.db.execute("UPDATE jobs SET state='failed' WHERE id=?", (row["id"],))
                    self._save(s)

    def _finalize(self, s):
        try:
            rec = self.recordings.pop(s["id"], None)
            if rec:
                paths = rec.finalize()
                s["artifacts"].update({"wav": str(paths["mixed"])})
            self._write_text(s, "live.txt", s["live_text"])
            self._write_text(s, "transcript.txt", s["transcript"])
            self._write_search_artifacts(s)
            s["state"] = "ready"
            if rec and s["options"]["audio_format"] != "wav":
                s["state"] = "exporting"
                self._job(s, "export", path=s["artifacts"]["wav"])
        except Exception as exc:
            s.update(state="failed", error=str(exc))
        self._save(s)

    def close(self):
        with self.changed:
            self.shutdown = True
            self.changed.notify_all()
        self.worker.join()
        if self.pool:
            self.pool.shutdown()
        with self.lock:
            for sid, rec in self.recordings.items():
                rec._close()
                self.sessions[sid]["state"] = "recoverable"
                self._save(self.sessions[sid])
            self.db.close()
