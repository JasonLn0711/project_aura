"""Validate retained mixed audio before releasing recording intermediates."""
import json
import os
from pathlib import Path
import subprocess


def validate_m4a(path, reference=None):
    path = Path(path)
    if path.is_symlink() or path.suffix.lower() != ".m4a" or not path.is_file():
        raise ValueError("A regular retained M4A file is required")
    def probe(p):
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,codec_name,sample_rate,channels", "-of", "json", str(p)],
            capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    info = probe(path)
    streams = [s for s in info["streams"] if s.get("codec_type") == "audio"]
    if len(streams) != 1 or streams[0]["codec_name"] != "aac":
        raise ValueError("Retained M4A must contain one AAC audio stream")
    duration = float(info["format"]["duration"])
    if duration <= 0:
        raise ValueError("Retained audio is empty")
    if reference:
        original = probe(reference)
        audio = next(s for s in original["streams"] if s.get("codec_type") == "audio")
        if abs(duration - float(original["format"]["duration"])) > 0.1:
            raise ValueError("Retained audio duration differs from its source")
        if any(streams[0][k] != audio[k] for k in ("sample_rate", "channels")):
            raise ValueError("Retained audio track layout differs from its source")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "2",
        "-i", str(path), "-map", "0:a:0", "-f", "null", "-"], check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return info


def recording_audio_files(root, sid):
    root = Path(root).resolve()
    import uuid
    if str(uuid.UUID(sid)) != sid:
        raise ValueError("Invalid session ID")
    for area in ("sessions", "capture_sources"):
        directory = root / area / sid
        if directory.is_symlink() or (directory.exists() and directory.resolve() != directory):
            raise ValueError("Redirected recording directory")
        for parent, dirs, files in os.walk(directory, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(parent) / d).is_symlink()]
            for name in files:
                path = Path(parent) / name
                if not path.is_symlink() and path.suffix.lower() in (".wav", ".pcm", ".m4a", ".mp3"):
                    yield path


def retain_mixed_m4a(root, session, persist=None):
    root = Path(root).resolve()
    sid = session["id"]
    path = Path(session["artifacts"]["m4a"])
    if path.parent.resolve() != root / "sessions" / sid:
        raise ValueError("Retained audio must belong to this session")
    reference = session["artifacts"].get("wav")
    validate_m4a(path, reference if reference and Path(reference).is_file() else None)
    if any(i["status"] == "pending" for i in session.get("asr_issues", [])):
        return []  # Recovery inputs remain until outstanding ASR work succeeds.
    candidates = []
    for audio in recording_audio_files(root, sid):
        if audio == path:
            continue
        if "capture_sources" in audio.relative_to(root).parts:
            manifest_path = next((p / "session.json" for p in audio.parents
                if p != root and (p / "session.json").is_file()), None)
            if not manifest_path or json.loads(manifest_path.read_text()).get("status") != "ready":
                continue  # The producer may still be finalizing its own journal.
        candidates.append(audio)
    # Publish valid references before unlinking their former targets.
    for area in ("sessions", "capture_sources"):
        directory = root / area / sid
        for manifest in directory.rglob("session.json"):
            if manifest.is_symlink() or manifest.resolve() != manifest:
                raise ValueError("Redirected recording manifest")
            data = json.loads(manifest.read_text())
            if area == "capture_sources" and data.get("status") != "ready":
                continue
            data.update(audio_tracks={"mixed": path.name} if area == "sessions" else {},
                        pcm_journals={}, retained_audio_path=str(path))
            from aura.audio.recording_session import write_session_manifest
            write_session_manifest(manifest, data)
    segments = root / "sessions" / sid / "segments.json"
    if segments.is_symlink():
        raise ValueError("Redirected segments manifest")
    if segments.is_file():
        from aura.ui.transcript_io import write_json_file
        data = json.loads(segments.read_text())
        data["audio_path"] = str(path)
        write_json_file(segments, data)
    session["artifacts"].pop("wav", None)
    if persist:
        persist(session)
    for audio in candidates:
        audio.unlink(missing_ok=True)
    return [str(p) for p in candidates]
