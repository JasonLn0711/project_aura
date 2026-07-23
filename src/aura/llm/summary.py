from dataclasses import dataclass
from pathlib import Path

from summary.field_schemas import BASE_MODEL_ID
from summary.layered_summary_pipeline import generate_layered_summary, save_layered_outputs


DEFAULT_SUMMARY_MODEL = BASE_MODEL_ID


@dataclass(frozen=True)
class SummarySettings:
    session_dir: str = ""
    meeting_id: str = ""
    evidence_segments: tuple[dict[str, object], ...] = ()
    transcript_sha256: str = ""


def transcript_has_content(transcript: str) -> bool:
    return bool(transcript and transcript.strip())


def summarize_transcript(transcript: str, settings: SummarySettings | None = None) -> str:
    settings = settings or SummarySettings()
    if not transcript_has_content(transcript):
        return ""
    result = generate_layered_summary(transcript)
    if settings.session_dir or settings.meeting_id:
        if not settings.session_dir or not settings.meeting_id:
            raise ValueError("session_dir and meeting_id must be configured together")
        save_layered_outputs(
            result,
            meeting_id=settings.meeting_id,
            segments=list(settings.evidence_segments),
            session_dir=Path(settings.session_dir),
            transcript_sha256=settings.transcript_sha256,
        )
    else:
        save_layered_outputs(
            result,
            segments=list(settings.evidence_segments),
            transcript_sha256=settings.transcript_sha256,
        )
    return result.markdown


def format_summary_block(summary: str) -> str:
    return "\n\n===== LLM Summary =====\n" + summary.strip()
