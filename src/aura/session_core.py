"""Single-owner session core: durable audio, serialized commands, bounded inference."""
import concurrent.futures
import datetime
import json
import math
import multiprocessing
import os
from pathlib import Path
import sqlite3
import threading
import uuid

from aura.metadata import __version__
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


def options_for(values=None, preferences=None):
    from aura.config import DEFAULT_LIVE_PROMPT
    from aura.asr.models import MODEL_KEYS, PARAKEET, PARAKEET_DEFAULTS
    result = dict(asr_model="breeze", profile="light", language="zh", beam_size=5, prompt=DEFAULT_LIVE_PROMPT,
                  hotwords="", punctuation=True, target_dbfs=-20.0, diarization=False,
                  min_speakers=2, max_speakers=6, audio_format="m4a",
                  live_segmentation="adaptive", live_max_segment_len_sec=20.0, live_silence_ms=800)
    values = values or {}
    if not isinstance(values, dict) or set(values) - result.keys():
        raise ValueError("Unknown transcription options")
    preferences = preferences or {}
    selected = values.get("asr_model", preferences.get("asr_model", "breeze"))
    if selected not in MODEL_KEYS:
        raise ValueError("Unknown ASR model")
    result.update(preferences)
    if selected == PARAKEET:
        result.update(PARAKEET_DEFAULTS)
        for key, expected in PARAKEET_DEFAULTS.items():
            if key in values and values[key] != expected:
                raise ValueError(f"Parakeet requires {key}={expected!r}; use Breeze for Whisper controls or Chinese.")
    result.update(values)
    if result["profile"] not in PROFILES:
        raise ValueError("Unknown audio profile")
    if result["live_segmentation"] not in ("adaptive", "fixed"):
        raise ValueError("live_segmentation must be adaptive or fixed")
    maximum = result["live_max_segment_len_sec"]
    if type(maximum) not in (float, int) or not math.isfinite(maximum) or not 2 <= maximum <= 30:
        raise ValueError("live_max_segment_len_sec must be between 2 and 30 seconds")
    if type(result["live_silence_ms"]) is not int or not 200 <= result["live_silence_ms"] <= 2000:
        raise ValueError("live_silence_ms must be between 200 and 2000 milliseconds")
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
        self.pool_model = None
        self.model_control = None
        self.keep_model = False
        self.model_state = dict(state="unloaded", asr_model=None, error=None)
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

    def _model_available(self):
        if self.model_state["state"] in ("loading", "unloading"):
            raise ValueError("ASR model is loading or unloading; wait for /model status before starting work.")

    def _available(self):
        self._model_available()
        if any(s["state"] in ACTIVE for s in self.sessions.values()):
            raise ValueError("A recording or transcription job is active; attach or finish it first")

    def _new(self, args, state):
        from aura.asr.hotwords import validate_cached_context
        options = options_for(args.get("options", {}), self._preferences())
        validate_cached_context(options)
        if args.get("source", "system_microphone") not in ("microphone", "system", "system_microphone"):
            raise ValueError("Unknown capture source")
        sid = str(uuid.uuid4())
        title = args.get("title") or "Meeting"
        if not isinstance(title, str) or len(title) > 200:
            raise ValueError("Title must contain at most 200 characters")
        session = dict(id=sid, title=title, state=state, created_at=now(), options=options,
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
            cache_command = request_id and command not in ("get", "sessions", "capabilities", "export", "preferences.get", "model.status")
            if cache_command:
                previous = self.db.execute("SELECT command,result FROM commands WHERE id=?", (request_id,)).fetchone()
                if previous:
                    if previous[0] != signature:
                        raise ValueError("Request ID already used for a different command")
                    return json.loads(previous[1])
            result = self._request(command, args)
            if command not in ("get", "sessions", "capabilities", "preferences.get", "model.status"):
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
        if command == "model.status":
            return dict(self.model_state, default=self._preferences().get("asr_model", "breeze"),
                        kept_loaded=self.keep_model)
        if command in ("model.load", "model.unload"):
            from aura.asr.models import MODEL_KEYS
            if set(args) - {"asr_model"}:
                raise ValueError("Unknown model options")
            self._available()
            key = args.get("asr_model", self._preferences().get("asr_model", "breeze"))
            if key not in MODEL_KEYS:
                raise ValueError("Unknown ASR model")
            self.model_state = dict(state="loading" if command == "model.load" else "unloading",
                                    asr_model=key if command == "model.load" else self.model_state["asr_model"], error=None)
            self.model_control = (command, key)
            self.changed.notify_all()
            return self._request("model.status", {})
        if command == "preferences.get":
            return self._preferences()
        if command == "preferences.set":
            values = {**self._preferences(), **args}
            options_for(args, self._preferences())
            self.db.executemany("INSERT OR REPLACE INTO preferences VALUES (?,?)", [(k, json.dumps(v)) for k, v in args.items()])
            self.db.commit()
            return values
        if command == "capabilities":
            import shutil
            from aura.asr.models import capabilities
            return dict(model_control=True, recover=True, asr_models=capabilities(), protocol=1, service_version=__version__,
                        diagnostics={"data_dir": str(self.root), "service_log": str(self.root / "service.log"),
                                     "capture_log": str(self.root / "capture.log")}, ffmpeg=bool(shutil.which("ffmpeg")), profiles=list(PROFILES), capture_format="s16le/16000/mono", single_owner=True,
                        deepfilternet=bool(shutil.which("deep-filter")), clearvoice=bool(os.environ.get("AURA_CLEARVOICE_PYTHON")))
        if command == "sessions":
            if args.get("summary"):
                from aura.sdk import session_summary, session_order
                return sorted((session_summary(s) for s in self.sessions.values()), key=session_order, reverse=True)
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
            opts = options_for(args.get("options", {}), self._preferences())
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
            if options_for(args.get("options", {}), self._preferences())["profile"] == "rescue-offline":
                raise ValueError("Offline rescue is an import-only profile")
            s = self._new(args, "scheduled")
            s.update(start_at=start.astimezone(datetime.timezone.utc).isoformat(), stop_at=end.astimezone(datetime.timezone.utc).isoformat())
            self._save(s)
            return s
        if command == "transcribe":
            self._model_available()
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
            message = str(args.get("error", "Capture failed"))[:2000]
            if s.get("error"):
                s["capture_error"] = message
            else:
                s["error"] = message
            s.update(state="failed", producer_connected=False)
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
                if s["state"] == "paused":
                    self._flush(s, "pause")
        elif command == "producer.paused":
            if s["state"] != "pausing":
                raise ValueError("Session is not pausing")
            self._flush(s, "pause")
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
                self._flush(s, "stop")
        elif command == "producer.stopped":
            if s["state"] != "stopping":
                raise ValueError("Capture stop acknowledgement requires a stopping session")
            self._flush(s, "stop")
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
        elif command == "recover":
            self._available()
            if s["state"] not in ("ready", "recoverable", "failed") or s.get("source_path"):
                raise ValueError("Recover requires a stopped, saved recording")
            rows = self.db.execute("SELECT * FROM jobs WHERE session=? AND kind='chunk' AND state IN ('failed','queued') ORDER BY id", (s["id"],)).fetchall()
            if not rows and s["state"] == "ready":
                return s
            from aura.audio.recording_session import recover_recording_session
            if s["id"] in self.recordings:
                paths = self.recordings.pop(s["id"]).finalize(keep_pcm=True)
            else:
                paths = recover_recording_session(self.directory(s["id"]) / "session.json", keep_pcm=True)
            s["artifacts"]["wav"] = str(paths["mixed"])
            previous_error = s.get("error")
            if not s.get("asr_issues"):
                for event in self.db.execute("SELECT data FROM events WHERE session=? ORDER BY seq", (s["id"],)):
                    snapshot = json.loads(event[0]).get("session", {})
                    if snapshot.get("state") == "failed" and snapshot.get("error"):
                        previous_error = snapshot["error"]
                        break
            for row in rows:
                payload = json.loads(row["payload"])
                if not Path(payload["path"]).exists():
                    payload["path"] = str(paths["mixed"])
                    self.db.execute("UPDATE jobs SET payload=? WHERE id=?", (json.dumps(payload), row["id"]))
                if row["state"] == "failed" and not any(i["job_id"] == row["id"] for i in s.get("asr_issues", [])):
                    self._issue(s, row, payload, previous_error or "Previously failed chunk")
                self.db.execute("UPDATE jobs SET state='queued' WHERE id=?", (row["id"],))
            s.update(state="draining", recovery_active=True)
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
            if fmt in ("refined", "recovered"):
                if fmt == "recovered":
                    path = s["artifacts"].get("recovered.txt")
                    if not path:
                        raise ValueError("Run recovery before exporting recovered text")
                    return {"path": path}
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

    def _issue(self, s, row, payload, error):
        issues = s.setdefault("asr_issues", [])
        issue = next((i for i in issues if i["job_id"] == row["id"]), None)
        if issue is None:
            issue = dict(job_id=row["id"], start_sample=payload["start"],
                         end_sample=payload["end"], error=str(error)[:2000])
            issues.append(issue)
        issue.update(status="pending", last_error=str(error)[:2000])

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
                        transcript_sha256=prepared.content_sha256, audio_profile=s["options"]["profile"],
                        asr_model=s["options"].get("asr_model", "breeze"), runtime=s.get("runtime"))
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
                intervals = SpeechIntervals(CHUNK_SIZE,
                    max_seconds=s["options"].get("live_max_segment_len_sec", 12.0),
                    silence_ms=s["options"].get("live_silence_ms", 800),
                    segmentation=s["options"].get("live_segmentation", "fixed"))
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
        s["last_split"] = dict(reason=chunk.split_reason, start_sample=chunk.start_sample,
                               end_sample=chunk.end_sample, terminal=chunk.terminal)
        self._job(s, "chunk", path=str(self.directory(s["id"]) / ".capture/mixed.pcm"),
                  start=chunk.start_sample, end=chunk.end_sample, terminal=chunk.terminal,
                  split_reason=chunk.split_reason)

    def _flush(self, s, reason="flush"):
        detector = self.detectors.pop(s["id"], None)
        if detector:
            chunk = detector[1].finish(reason)
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
        model_key = payload.get("options", {}).get("asr_model", "breeze")
        if kind != "export" and self.pool is not None and self.pool_model != model_key:
            self.keep_model = False
            self.pool.shutdown()
            self.pool = None
        if kind != "export":
            self.pool_model = model_key
        if self.pool is None:
            self.pool = concurrent.futures.ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        from aura.session_runtime import execute
        return self.pool.submit(execute, kind, payload).result()

    def _control_model(self, command, key):
        try:
            if command == "model.load":
                result = self._execute("load", {"options": options_for({"asr_model": key})})
                with self.changed:
                    self.keep_model = True
                    self.model_state = dict(state="loaded", asr_model=key, runtime=result, error=None)
                    self.db.execute("INSERT OR REPLACE INTO preferences VALUES (?,?)", ("asr_model", json.dumps(key)))
                    self.db.commit()
            else:
                if self.pool:
                    self.pool.shutdown()
                with self.changed:
                    self.pool = None
                    self.keep_model = False
                    self.model_state = dict(state="unloaded", asr_model=None, error=None)
        except Exception as exc:
            if self.pool:
                self.pool.shutdown()
            with self.changed:
                self.pool = None
                self.keep_model = False
                self.model_state = dict(state="error", asr_model=key, error=str(exc))
        finally:
            with self.changed:
                self.changed.notify_all()

    def _work(self):
        while True:
            with self.changed:
                if self.shutdown:
                    break
                control = self.model_control
                self.model_control = None
            if control:
                self._control_model(*control)
                continue
            with self.changed:
                if self.shutdown:
                    break
                # A control request may arrive between the two lock acquisitions.
                if self.model_control:
                    continue
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
                    if self.pool and not self.keep_model and not any(s["state"] in ACTIVE for s in self.sessions.values()):
                        self.pool.shutdown()
                        self.pool = None
                        self.model_state = dict(state="unloaded", asr_model=None, error=self.model_state.get("error"))
                    self.changed.wait(0.2)
                    continue
                if row["kind"] != "export" and (self.pool is None or self.pool_model != json.loads(row["payload"])["options"].get("asr_model", "breeze")):
                    self.model_state = dict(state="loading", asr_model=json.loads(row["payload"])["options"].get("asr_model", "breeze"), error=None)
                self.db.execute("UPDATE jobs SET state='running' WHERE id=?", (row["id"],))
                self.db.commit()
            try:
                result = self._execute(row["kind"], json.loads(row["payload"]))
                with self.changed:
                    s = self.sessions[row["session"]]
                    if row["kind"] != "export":
                        self.model_state = dict(state="loaded", asr_model=json.loads(row["payload"])["options"].get("asr_model", "breeze"),
                                                runtime=result.get("runtime", result if row["kind"] == "load" else {}), error=None)
                    if "runtime" in result:
                        s["runtime"] = result["runtime"]
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
                            segment = asdict(ReviewSegment(
                                f'live-{result["start_sample"]}', round(result["start_sample"] / 16),
                                round(result["end_sample"] / 16), text))
                            segments = s.setdefault("segments", [])
                            if s.get("recovery_active"):
                                segments[:] = [x for x in segments if x["segment_id"] != segment["segment_id"]]
                                segments.append(segment)
                                segments.sort(key=lambda x: x["start_ms"])
                                s["live_text"] = "".join(f'[{format_timestamp(x["start_ms"] / 1000)}] {x["text"]}\n' for x in segments)
                            else:
                                segments.append(segment)
                                s["live_text"] += f'[{format_timestamp(result["start_sample"] / 16000)}] {text}\n'
                            if not s["edited"]:
                                s["transcript"] = s["live_text"]
                                s["revision"] += 1
                            self._write_text(s, "live.txt", s["live_text"])
                        for issue in s.get("asr_issues", []):
                            if issue["job_id"] == row["id"]:
                                issue["status"] = "resolved"
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
                    from aura.asr.models import ASROutputError
                    payload = json.loads(row["payload"])
                    if row["kind"] == "chunk":
                        self._issue(s, row, payload, exc)
                    if row["kind"] == "chunk" and isinstance(exc, ASROutputError):
                        self.db.execute("UPDATE jobs SET state='failed' WHERE id=?", (row["id"],))
                        if s["state"] == "pausing" and s.get("capture_paused_ack"):
                            s["state"] = "paused"
                        self._save(s)
                        continue
                    s.update(state="failed", error=s.get("error") or str(exc))
                    if row["kind"] != "export":
                        self.keep_model = False
                        self.model_state = dict(state="error", asr_model=json.loads(row["payload"])["options"].get("asr_model", "breeze"), error=str(exc))
                    self.db.execute("UPDATE jobs SET state='failed' WHERE id=?", (row["id"],))
                    self._save(s)

    def _finalize(self, s):
        try:
            rec = self.recordings.pop(s["id"], None)
            if rec:
                paths = rec.finalize(keep_pcm=any(i["status"] == "pending" for i in s.get("asr_issues", [])))
                s["artifacts"].update({"wav": str(paths["mixed"])})
            self._write_text(s, "live.txt", s["live_text"])
            self._write_text(s, "transcript.txt", s["transcript"])
            self._write_search_artifacts(s)
            s["state"] = "ready"
            if s.pop("recovery_active", False):
                self._write_text(s, "recovered.txt", s["live_text"])
                if not any(i["status"] == "pending" for i in s.get("asr_issues", [])):
                    if s.get("error"):
                        s["recovered_error"] = s.pop("error")
                    s["error"] = None
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
