"""Commit a verified mixed M4A before removing session-owned working audio."""
import json
import math
import os
from pathlib import Path
import subprocess
import uuid

from aura.audio.normalization import require_ffmpeg, require_ffprobe
from aura.audio.recording_session import _fsync_directory, write_session_manifest


class AudioCleanupIncomplete(OSError):
    def __init__(self, cause, output, deleted, released):
        super().__init__(f"M4A is retained; audio cleanup needs a retry: {cause}")
        self.report = dict(status="incomplete", retained=str(output), deleted=deleted,
                           released_bytes=released, reason=str(self))


def session_file(directory: Path, name: str) -> Path:
    """Keep cleanup within this session, including when an ancestor is a symlink."""
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Audio path escapes its session: {name}")
    path = directory / relative
    if directory.is_symlink() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"Refusing redirected audio path: {path}")
    path.resolve().relative_to(directory.resolve())
    return path


def recording_audio_plan(manifest_path: str | Path) -> dict:
    manifest_path = Path(manifest_path)
    directory = manifest_path.parent
    manifest = json.loads(session_file(directory, manifest_path.name).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Recording manifest must be an object")
    if manifest.get("status") != "ready" or manifest.get("workflow") == "import":
        raise ValueError("Only stopped recording sessions are eligible for audio cleanup")
    tracks = manifest.get("audio_tracks", {})
    journals = manifest.get("pcm_journals", {})
    pending = manifest.get("audio_cleanup_pending", [])
    if (not isinstance(tracks, dict) or not isinstance(journals, dict)
            or not all(isinstance(name, str) for name in (*tracks.values(), *journals.values()))
            or not isinstance(pending, list) or not all(isinstance(name, str) for name in pending)):
        raise ValueError("Invalid recorded audio paths")
    mixed = tracks.get("mixed")
    if not isinstance(mixed, str):
        raise ValueError("No recorded mixed audio is registered")
    source = session_file(directory, mixed)
    if source.suffix.lower() not in (".wav", ".mp3", ".m4a") or not source.is_file():
        raise ValueError(f"Registered mixed source is unavailable: {source}")
    output = source.with_suffix(".m4a")
    session_file(directory, str(output.relative_to(directory)))
    removals = set(pending)
    for name in tracks.values():
        path = session_file(directory, name)
        # Only registered tracks and their exact-stem legacy delivery variants.
        for suffix in (".wav", ".mp3", ".m4a"):
            candidate = path.with_suffix(suffix)
            session_file(directory, str(candidate.relative_to(directory)))
            if candidate != output and candidate.is_file():
                removals.add(str(candidate.relative_to(directory)))
        if path != output and path.suffix.lower() in (".wav", ".mp3", ".m4a") and path.is_file():
            removals.add(name)
    for name in journals.values():
        path = session_file(directory, name)
        if path.suffix.lower() != ".pcm":
            raise ValueError(f"Unexpected PCM journal: {name}")
        if path.is_file():
            removals.add(name)
    paths = [session_file(directory, name) for name in sorted(removals)]
    if any(p == output or p.suffix.lower() not in (".wav", ".mp3", ".pcm", ".m4a") for p in paths):
        raise ValueError("Invalid pending audio cleanup entry")
    return dict(manifest=str(manifest_path), source=str(source), output=str(output),
                remove=[str(p.relative_to(directory)) for p in paths],
                removable_bytes=sum(p.stat().st_size for p in paths if p.is_file()))


def validate_m4a(path: str | Path, reference: str | Path | None = None) -> dict:
    path = Path(path)
    if path.is_symlink() or path.suffix.lower() != ".m4a" or not path.is_file():
        raise ValueError("A regular retained M4A file is required")
    ffprobe = require_ffprobe()
    if not ffprobe:
        raise RuntimeError("ffprobe is required before recording audio can be removed")
    def probe(audio):
        result = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                                 "stream=codec_type,codec_name,sample_rate,channels:format=duration",
                                 "-of", "json", str(audio)], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    info = probe(path)
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    duration = float(info.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0 or len(streams) != 1 or streams[0].get("codec_name") != "aac":
        raise ValueError(f"Not a nonempty AAC recording: {path}")
    if reference is not None and Path(reference) != path:
        original = probe(reference)
        source_duration = float(original.get("format", {}).get("duration", 0))
        if not math.isfinite(source_duration) or source_duration <= 0 or abs(source_duration - duration) > 0.1:
            raise ValueError(f"M4A duration does not match the mixed source: {path}")
        original_audio = [s for s in original.get("streams", []) if s.get("codec_type") == "audio"]
        if len(original_audio) != 1 or any(streams[0].get(k) != original_audio[0].get(k) for k in ("sample_rate", "channels")):
            raise ValueError(f"M4A track layout does not match the mixed source: {path}")
    # Decode every packet; a readable header alone does not establish a valid export.
    subprocess.run([require_ffmpeg(), "-nostdin", "-v", "error", "-xerror", "-threads", "1",
                    "-i", str(path), "-map", "0:a:0", "-f", "null", "-"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    return info


def prepare_recording_m4a(manifest_path: str | Path, target_dbfs: float = -20.0) -> Path:
    """Validate or atomically create delivery audio. Never remove source tracks."""
    from aura.audio.export import normalize_wav_to_recording_audio
    plan = recording_audio_plan(manifest_path)
    source, output = Path(plan["source"]), Path(plan["output"])
    if output.exists():
        manifest = json.loads(Path(manifest_path).read_text())
        if manifest.get("enhancement_strategy") == "reuse-v1" and not manifest.get("offline_enhancement"):
            raise RuntimeError("Existing M4A has no offline RE-USE receipt; original audio retained")
        # Preserve an invalid existing export and all sources for explicit diagnosis.
        validate_m4a(output, source)
        return output
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    enhanced = None
    encoding_source = source
    if manifest.get("enhancement_strategy") == "reuse-v1":
        from aura.audio.reuse import ReuseWorker
        enhanced = source.with_name(".reuse-offline.wav")
        manifest["enhancement_phase"] = "offline"
        write_session_manifest(manifest_path, manifest)
        def progress(value):
            manifest["enhancement_progress"] = value
            write_session_manifest(manifest_path, manifest)
        with ReuseWorker("offline", progress=progress, log_path=source.parent / "reuse-offline.log") as worker:
            receipt = worker.enhance_file(source, enhanced)
        manifest["offline_enhancement"] = receipt
        manifest["enhancement_phase"] = "encoding"
        manifest.setdefault("audio_cleanup_pending", []).append(enhanced.name)
        write_session_manifest(manifest_path, manifest)
        encoding_source = enhanced
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.m4a")
    try:
        normalize_wav_to_recording_audio(encoding_source, target_dbfs, "m4a", remove_source=False, output_path=temporary)
        validate_m4a(temporary, source)
        with temporary.open("rb") as audio:
            os.fsync(audio.fileno())
        os.replace(temporary, output)
        _fsync_directory(output.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def complete_recording_m4a(manifest_path: str | Path, output: str | Path, *, persist=None) -> dict:
    """Publish references to a prepared M4A, then perform retryable deletions.

    Call only after prepare_recording_m4a succeeds and pending ASR has drained.
    persist publishes the owning session database before any source is deleted.
    """
    plan = recording_audio_plan(manifest_path)
    output = Path(output)
    if output != Path(plan["output"]) or not output.is_file():
        raise ValueError("Export result is not the session's prepared mixed M4A")
    manifest_path = Path(manifest_path)
    directory = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("diarization") or {}).get("state") in ("failed", "loading", "ready", "running", "recovering"):
        raise ValueError("Diarization is unfinished; preserve source audio for recovery")
    if any(gap['status'] == 'pending' for gap in manifest.get('enhancement_gaps', [])):
        raise ValueError('Enhancement gaps remain unresolved; original audio retained for recovery')
    manifest["enhancement_phase"] = "committed"
    manifest["audio_tracks"] = {"mixed": str(output.relative_to(directory))}
    manifest["pcm_journals"] = {}
    manifest["audio_cleanup_pending"] = plan["remove"]
    write_session_manifest(manifest_path, manifest)
    segments_path = session_file(directory, "segments.json")
    if segments_path.exists():
        from aura.ui.transcript_io import write_json_file
        segments = json.loads(segments_path.read_text(encoding="utf-8"))
        if isinstance(segments, dict):
            segments["audio_path"] = str(output.resolve())
            write_json_file(segments_path, segments)
    if persist:
        persist(output)
    deleted, released = [], 0
    try:
        for name in plan["remove"]:
            path = session_file(directory, name)
            if path.is_file():
                size = path.stat().st_size
                path.unlink()
                deleted.append(str(path))
                released += size
        _fsync_directory(directory)
        manifest.pop("audio_cleanup_pending", None)
        write_session_manifest(manifest_path, manifest)
    except OSError as exc:
        raise AudioCleanupIncomplete(exc, output, deleted, released) from exc
    capture = directory / ".capture"
    if capture.is_dir() and not capture.is_symlink() and not any(capture.iterdir()):
        capture.rmdir()
    return dict(retained=str(output), deleted=deleted, released_bytes=released)
