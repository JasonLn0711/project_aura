import datetime
import json
import os
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from aura.audio.recording_session import write_session_manifest
from aura.asr.punctuation import restore_chinese_punctuation_for_transcript
from asr_postprocess.fuzzy_corrector import DEFAULT_GLOSSARY_PATH, correct_transcript, write_correction_log


SUMMARY_MARKER = "===== LLM Summary ====="


@dataclass(frozen=True)
class PreparedTranscript:
    raw_text: str
    punctuated_text: str
    corrected_text: str
    content_sha256: str
    correction_log: tuple[dict[str, Any], ...] = ()
    punctuation_backend: str = "skipped"


@dataclass(frozen=True)
class TranscriptSession:
    directory: Path
    meeting_id: str


def ensure_transcript_session(
    base_path: str | Path,
    *,
    workflow: str,
    source_path: str | Path | None = None,
) -> TranscriptSession:
    base = Path(base_path)
    directory = base.with_name(f"{base.name}_session")
    manifest_path = directory / "session.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        meeting_id = str(payload.get("meeting_id") or "").strip()
        if not meeting_id:
            raise ValueError(f"Session manifest has no meeting_id: {manifest_path}")
        existing_source = payload.get("source_path")
        if existing_source and source_path and (
            Path(str(existing_source)).expanduser().resolve()
            != Path(source_path).expanduser().resolve()
        ):
            raise ValueError(
                f"Session manifest belongs to a different source: {manifest_path}"
            )
        return TranscriptSession(directory=directory, meeting_id=meeting_id)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    meeting_id = str(uuid4())
    write_session_manifest(
        manifest_path,
        {
            "schema_version": 1,
            "meeting_id": meeting_id,
            "status": "ready",
            "title": base.name,
            "workflow": workflow,
            "source_path": (
                str(Path(source_path).expanduser().resolve()) if source_path else None
            ),
            "started_at": now,
            "ended_at": now,
            "audio_tracks": {},
        },
    )
    return TranscriptSession(directory=directory, meeting_id=meeting_id)


def collision_safe_transcript_base_path(
    base_path: str | Path,
    source_path: str | Path,
) -> Path:
    base = Path(base_path)
    manifest_path = base.with_name(f"{base.name}_session") / "session.json"
    if not manifest_path.exists():
        return base
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    normalized_source = str(Path(source_path).expanduser().resolve())
    existing_source = payload.get("source_path")
    if existing_source and str(Path(existing_source).expanduser().resolve()) == normalized_source:
        return base
    suffix = sha256(normalized_source.encode("utf-8")).hexdigest()[:12]
    candidate = base.with_name(f"{base.name}_{suffix}")
    candidate_manifest = candidate.with_name(f"{candidate.name}_session") / "session.json"
    if candidate_manifest.exists():
        candidate_payload = json.loads(candidate_manifest.read_text(encoding="utf-8"))
        candidate_source = candidate_payload.get("source_path")
        if not candidate_source or (
            str(Path(candidate_source).expanduser().resolve()) != normalized_source
        ):
            raise ValueError(
                f"Collision-safe session belongs to a different source: {candidate_manifest}"
            )
    return candidate


def prepare_transcript(
    raw_transcript: str,
    *,
    language: str | None = None,
    enable_punctuation: bool = True,
    enable_punctuation_model: bool = False,
    enable_glossary_correction: bool = True,
    glossary_path: str | Path = DEFAULT_GLOSSARY_PATH,
) -> PreparedTranscript:
    raw_text = raw_transcript.strip()
    punctuation_result = restore_chinese_punctuation_for_transcript(
        raw_text,
        language=language,
        enable_model=enable_punctuation_model,
    ) if raw_text and enable_punctuation else None
    punctuated_text = punctuation_result.text if punctuation_result else raw_text
    correction_result = (
        correct_transcript(punctuated_text, glossary_path=glossary_path)
        if punctuated_text and enable_glossary_correction
        else None
    )
    corrected_text = correction_result.corrected_transcript if correction_result else punctuated_text
    return PreparedTranscript(
        raw_text=raw_text,
        punctuated_text=punctuated_text,
        corrected_text=corrected_text,
        content_sha256=sha256(corrected_text.encode("utf-8")).hexdigest(),
        correction_log=tuple(correction_result.correction_log) if correction_result else (),
        punctuation_backend=punctuation_result.backend if punctuation_result else "skipped",
    )


def transcript_text_for_save(content: str) -> str:
    cleaned = content.strip()
    if not cleaned:
        return ""
    return f"{cleaned}\n"


def _atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as target:
            target.write(text)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def write_transcript_file(file_path: str | Path, content: str) -> bool:
    text = transcript_text_for_save(content)
    if not text:
        return False
    path = Path(file_path)
    _atomic_write_text(path, text)
    return True


def summary_text_for_save(content: str) -> str:
    cleaned = content.strip()
    if not cleaned:
        return ""
    if SUMMARY_MARKER in cleaned:
        cleaned = cleaned.split(SUMMARY_MARKER, 1)[1].strip()
    return cleaned


def split_transcript_sections(content: str) -> tuple[str, str]:
    cleaned = content.strip()
    if SUMMARY_MARKER not in cleaned:
        return cleaned, ""
    raw, summary = cleaned.split(SUMMARY_MARKER, 1)
    return raw.strip(), summary.strip()


def final_transcript_text(raw_transcript: str, summary_text: str | None = None) -> str:
    raw = raw_transcript.strip()
    summary = summary_text_for_save(summary_text or "")
    if raw and summary:
        return f"{raw}\n\n{SUMMARY_MARKER}\n{summary}"
    if summary:
        return f"{SUMMARY_MARKER}\n{summary}"
    return raw


def transcript_artifact_paths(base_path: str | Path) -> dict[str, Path]:
    path = Path(base_path)
    return {
        "raw": path.with_name(f"{path.name}_raw.txt"),
        "corrected": path.with_name(f"{path.name}_corrected.txt"),
        "final": path.with_name(f"{path.name}_final.txt"),
        "summary": path.with_name(f"{path.name}_summary.txt"),
        "correction_log": path.with_name(f"{path.name}_correction_log.json"),
        "prepared": path.with_name(f"{path.name}_prepared_transcript.json"),
        "metrics": path.with_name(f"{path.name}_processing_metrics.json"),
        "event_log": path.with_name(f"{path.name}_event_log.json"),
        "runtime_log": path.with_name(f"{path.name}_runtime.log"),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def write_json_file(file_path: str | Path, payload: dict[str, Any]) -> Path:
    path = Path(file_path)
    return _atomic_write_text(
        path,
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def event_log_payload(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow": metrics.get("workflow"),
        "source_path": metrics.get("source_path"),
        "base_path": metrics.get("base_path"),
        "started_at": metrics.get("started_at"),
        "finished_at": metrics.get("finished_at"),
        "runtime_config": metrics.get("recording_runtime_config") or metrics.get("runtime_config") or {},
        "events": metrics.get("status_events", []),
    }


def write_event_log_file(base_path: str | Path, metrics: dict[str, Any]) -> Path:
    return write_json_file(transcript_artifact_paths(base_path)["event_log"], event_log_payload(metrics))


def write_transcript_artifacts(
    base_path: str | Path,
    raw_transcript: str | PreparedTranscript,
    summary_text: str | None = None,
    metrics: dict[str, Any] | None = None,
    enable_glossary_correction: bool = True,
    glossary_path: str | Path = DEFAULT_GLOSSARY_PATH,
    session: TranscriptSession | None = None,
) -> dict[str, Path]:
    paths = transcript_artifact_paths(base_path)
    saved: dict[str, Path] = {}
    prepared = raw_transcript if isinstance(raw_transcript, PreparedTranscript) else None
    raw_text = prepared.raw_text if prepared else raw_transcript

    if write_transcript_file(paths["raw"], raw_text):
        saved["raw"] = paths["raw"]

    transcript_for_final = prepared.corrected_text if prepared else raw_text
    correction_log: list[dict[str, Any]] = []
    if prepared:
        correction_log = list(prepared.correction_log)
        if write_transcript_file(paths["corrected"], transcript_for_final):
            saved["corrected"] = paths["corrected"]
        saved["correction_log"] = write_correction_log(paths["correction_log"], correction_log)
        prepared_path = session.directory / "prepared_transcript.json" if session else paths["prepared"]
        saved["prepared"] = write_json_file(prepared_path, asdict(prepared))
        if session:
            manifest_path = session.directory / "session.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if str(manifest.get("meeting_id") or "") != session.meeting_id:
                raise ValueError("prepared transcript meeting_id does not match session.json")
            manifest["prepared_transcript"] = prepared_path.name
            manifest["transcript_sha256"] = prepared.content_sha256
            write_session_manifest(manifest_path, manifest)
    elif raw_text.strip() and enable_glossary_correction:
        correction_result = correct_transcript(raw_text, glossary_path=glossary_path)
        transcript_for_final = correction_result.corrected_transcript
        correction_log = correction_result.correction_log
        if write_transcript_file(paths["corrected"], transcript_for_final):
            saved["corrected"] = paths["corrected"]
        saved["correction_log"] = write_correction_log(paths["correction_log"], correction_log)

    summary = summary_text_for_save(summary_text or "")
    if summary and write_transcript_file(paths["summary"], summary):
        saved["summary"] = paths["summary"]

    final_text = final_transcript_text(transcript_for_final, summary)
    if write_transcript_file(paths["final"], final_text):
        saved["final"] = paths["final"]

    if metrics is not None:
        if prepared:
            metrics["prepared_transcript_sha256"] = prepared.content_sha256
        metrics["glossary_correction"] = {
            "enabled": enable_glossary_correction,
            "llm_verification": False,
            "correction_count": len(correction_log),
            "method": "rapidfuzz",
        }
        if metrics.get("status_events"):
            saved["event_log"] = write_event_log_file(base_path, metrics)
        metrics_payload = dict(metrics)
        metrics_payload["outputs"] = {name: str(path) for name, path in saved.items()}
        saved["metrics"] = write_json_file(paths["metrics"], metrics_payload)

    return saved
