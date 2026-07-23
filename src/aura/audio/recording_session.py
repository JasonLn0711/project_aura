import datetime
import json
import os
import time
import wave
from pathlib import Path
from uuid import uuid4


SESSION_STATUSES = {"recording", "finalizing", "ready", "recoverable", "failed"}
TRACK_NAMES = ("mixed", "system", "microphone")
FLUSH_INTERVAL_SECONDS = 1.0
FSYNC_INTERVAL_SECONDS = 5.0


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _atomic_write_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2, sort_keys=True)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def write_session_manifest(path: str | Path, payload: dict) -> Path:
    path = Path(path)
    if path.name != "session.json":
        raise ValueError("Session manifest path must end with session.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path, payload)
    return path


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _load_manifest(manifest_path: Path) -> dict:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unreadable recording session manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"Recording session manifest must be an object: {manifest_path}")
    if manifest.get("status") not in SESSION_STATUSES:
        raise ValueError(f"Unsupported recording session status: {manifest.get('status')}")
    return manifest


def _session_file(session_dir: Path, relative_path: str) -> Path:
    path = (session_dir / relative_path).resolve()
    try:
        path.relative_to(session_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Session path escapes its directory: {relative_path}") from exc
    return path


def discover_recoverable_sessions(root: str | Path) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    candidates = []
    for manifest_path in sorted(root.rglob("session.json")):
        try:
            manifest = _load_manifest(manifest_path)
            if manifest.get("recovery_acknowledged_at"):
                continue
            audio_tracks = manifest.get("audio_tracks", {})
            has_audio_tracks = (
                isinstance(audio_tracks, dict)
                and audio_tracks
                and all(
                    _session_file(manifest_path.parent, relative_path).is_file()
                    for relative_path in audio_tracks.values()
                )
            )
            if manifest["status"] == "ready":
                prepared_path = manifest.get("prepared_transcript")
                has_transcript_artifacts = (
                    isinstance(prepared_path, str)
                    and _session_file(manifest_path.parent, prepared_path).is_file()
                ) or (manifest_path.parent / "segments.json").is_file()
                if not has_transcript_artifacts and has_audio_tracks:
                    candidates.append(manifest_path)
                continue
            journals = manifest.get("pcm_journals", {})
            if has_audio_tracks or any(
                _session_file(manifest_path.parent, relative_path).stat().st_size > 0
                for relative_path in journals.values()
            ):
                candidates.append(manifest_path)
        except (OSError, TypeError, ValueError):
            continue
    return candidates


def recover_recording_session(manifest_path: str | Path) -> dict[str, Path]:
    manifest_path = Path(manifest_path)
    manifest = _load_manifest(manifest_path)
    original_status = manifest["status"]
    original_failure = manifest.get("failure")
    partial_recovery = original_status != "ready"
    session = RecordingSession(manifest_path.parent, manifest)
    audio_tracks = {
        track: _session_file(manifest_path.parent, relative_path)
        for track, relative_path in manifest.get("audio_tracks", {}).items()
    }
    if audio_tracks and all(path.exists() for path in audio_tracks.values()):
        recovered_tracks = audio_tracks
    else:
        recovered_tracks = session.finalize(
            capture_error=(
                InterruptedError(
                    f"Recovered audio from interrupted {original_status} session"
                )
                if partial_recovery
                else None
            )
        )
        manifest = session.manifest
    recovered_at = _utc_now()
    if partial_recovery:
        manifest["status"] = "ready"
        manifest["recording_outcome"] = "partial"
        manifest["recovery_original_status"] = original_status
        manifest["recovery_outcome"] = "partial_audio_recovered"
        if original_failure is not None:
            manifest["failure"] = original_failure
        else:
            manifest.setdefault(
                "failure",
                {
                    "phase": "recovery",
                    "error_class": "InterruptedRecordingSession",
                    "message": (
                        "The recording process ended before the session reached "
                        "its normal ready state."
                    ),
                    "occurred_at": recovered_at,
                },
            )
        manifest["recovery_next_action"] = "review_recovered_partial_audio"
    else:
        manifest.setdefault("recording_outcome", "complete")
        manifest["recovery_next_action"] = "import_audio_for_transcription"
    manifest["recovery_acknowledged_at"] = recovered_at
    write_session_manifest(manifest_path, manifest)
    return recovered_tracks


class RecordingSession:
    def __init__(self, session_dir: Path, manifest: dict):
        self.session_dir = session_dir
        self.manifest_path = session_dir / "session.json"
        self.manifest = manifest
        self._files = {}
        self._last_flush = time.monotonic()
        self._last_fsync = self._last_flush

    @classmethod
    def start(
        cls,
        session_dir: str | Path,
        *,
        recording_name: str,
        capture_mode: str,
        sample_rate: int,
        sample_width: int,
    ):
        if not recording_name or Path(recording_name).name != recording_name:
            raise ValueError("recording_name must be a file name")
        if sample_rate <= 0 or sample_width <= 0:
            raise ValueError("sample_rate and sample_width must be positive")

        session_dir = Path(session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = session_dir / "session.json"
        if manifest_path.exists():
            raise FileExistsError(f"Recording session already exists: {manifest_path}")

        manifest = {
            "schema_version": 1,
            "meeting_id": str(uuid4()),
            "status": "recording",
            "title": recording_name,
            "started_at": _utc_now(),
            "ended_at": None,
            "capture_mode": capture_mode,
            "sample_rate": sample_rate,
            "sample_width": sample_width,
            "recording_name": recording_name,
            "pcm_journals": {},
            "audio_tracks": {},
        }
        write_session_manifest(manifest_path, manifest)
        return cls(session_dir, manifest)

    def append_pcm(self, tracks: dict[str, bytes]) -> None:
        if self.manifest["status"] != "recording":
            raise RuntimeError(f"Cannot append PCM while session is {self.manifest['status']}")
        for track, pcm in tracks.items():
            if track not in TRACK_NAMES:
                raise ValueError(f"Unsupported audio track: {track}")
            if len(pcm) % self.manifest["sample_width"]:
                raise ValueError(f"PCM byte count is not sample-aligned for {track}")
        try:
            for track, pcm in tracks.items():
                if not pcm:
                    continue
                target = self._files.get(track)
                if target is None:
                    journal_dir = self.session_dir / ".capture"
                    journal_dir.mkdir(parents=True, exist_ok=True)
                    journal_path = journal_dir / f"{track}.pcm"
                    target = journal_path.open("ab")
                    self._files[track] = target
                    self.manifest["pcm_journals"][track] = str(journal_path.relative_to(self.session_dir))
                    write_session_manifest(self.manifest_path, self.manifest)
                target.write(pcm)
            now = time.monotonic()
            if now - self._last_flush >= FLUSH_INTERVAL_SECONDS:
                self._flush()
            if now - self._last_fsync >= FSYNC_INTERVAL_SECONDS:
                self._fsync()
        except OSError as exc:
            self._record_failure(exc)
            raise

    def _record_failure(self, error: Exception) -> None:
        for target in self._files.values():
            try:
                target.close()
            except OSError:
                pass
        self._files.clear()
        self.manifest["status"] = "failed"
        self.manifest["ended_at"] = _utc_now()
        self.manifest["failure"] = {
            "error_class": type(error).__name__,
            "message": str(error),
            "occurred_at": _utc_now(),
        }
        try:
            write_session_manifest(self.manifest_path, self.manifest)
        except OSError:
            pass

    def checkpoint(self) -> None:
        try:
            self._fsync()
        except OSError as exc:
            self._record_failure(exc)
            raise

    def _flush(self) -> None:
        for target in self._files.values():
            target.flush()
        self._last_flush = time.monotonic()

    def _fsync(self) -> None:
        self._flush()
        for target in self._files.values():
            os.fsync(target.fileno())
        self._last_fsync = self._last_flush

    def _close(self) -> None:
        try:
            self._fsync()
        finally:
            for target in self._files.values():
                target.close()
            self._files.clear()

    def finalize(
        self,
        *,
        trim_trailing_frames: int = 0,
        frame_samples: int = 0,
        capture_error: Exception | None = None,
    ) -> dict[str, Path]:
        if trim_trailing_frames < 0 or (trim_trailing_frames and frame_samples <= 0):
            raise ValueError("frame_samples must be positive when trimming frames")
        recording_name = self.manifest.get("recording_name")
        if not isinstance(recording_name, str) or not recording_name or Path(recording_name).name != recording_name:
            raise ValueError("recording_name must be a file name")
        journals = self.manifest.get("pcm_journals")
        if not isinstance(journals, dict) or any(track not in TRACK_NAMES for track in journals):
            raise ValueError("pcm_journals contains unsupported tracks")
        try:
            self.manifest["status"] = "finalizing"
            write_session_manifest(self.manifest_path, self.manifest)
            self._close()

            if trim_trailing_frames:
                trim_bytes = trim_trailing_frames * frame_samples * self.manifest["sample_width"]
                for relative_path in journals.values():
                    journal_path = _session_file(self.session_dir, relative_path)
                    journal_path.touch(exist_ok=True)
                    journal_path.truncate(max(0, journal_path.stat().st_size - trim_bytes))

            audio_tracks = {}
            for track, relative_path in journals.items():
                partial_suffix = "_partial" if capture_error is not None else ""
                suffix = partial_suffix if track == "mixed" else f"{partial_suffix}_{track}"
                wav_path = self.session_dir / f"{recording_name}{suffix}.wav"
                temporary = wav_path.with_name(f".{wav_path.name}.tmp")
                try:
                    with wave.open(str(temporary), "wb") as recording, _session_file(
                        self.session_dir,
                        relative_path,
                    ).open("rb") as pcm:
                        recording.setnchannels(1)
                        recording.setsampwidth(self.manifest["sample_width"])
                        recording.setframerate(self.manifest["sample_rate"])
                        while chunk := pcm.read(1024 * 1024):
                            recording.writeframesraw(chunk)
                    with temporary.open("rb+") as durable_wav:
                        os.fsync(durable_wav.fileno())
                    os.replace(temporary, wav_path)
                    _fsync_directory(self.session_dir)
                finally:
                    if temporary.exists():
                        try:
                            temporary.unlink()
                        except OSError:
                            pass
                audio_tracks[track] = wav_path

            self.manifest["audio_tracks"] = {
                track: str(path.relative_to(self.session_dir)) for track, path in sorted(audio_tracks.items())
            }
            self.manifest["ended_at"] = _utc_now()
            if capture_error is None:
                self.manifest["status"] = "ready"
                self.manifest["recording_outcome"] = "complete"
                self.manifest.pop("failure", None)
            else:
                self.manifest["status"] = "failed"
                self.manifest["recording_outcome"] = "partial"
                self.manifest["failure"] = {
                    "phase": "capture",
                    "error_class": type(capture_error).__name__,
                    "message": str(capture_error),
                    "occurred_at": _utc_now(),
                }
            write_session_manifest(self.manifest_path, self.manifest)
        except Exception as exc:
            self._record_failure(exc)
            raise

        for relative_path in tuple(self.manifest["pcm_journals"].values()):
            try:
                _session_file(self.session_dir, relative_path).unlink()
            except OSError:
                pass
        capture_dir = self.session_dir / ".capture"
        try:
            capture_dir.rmdir()
        except OSError:
            pass
        if not capture_dir.exists():
            self.manifest["pcm_journals"] = {}
            write_session_manifest(self.manifest_path, self.manifest)
        return audio_tracks
