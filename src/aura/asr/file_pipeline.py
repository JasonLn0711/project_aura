import gc
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pydub import AudioSegment

from aura.audio.denoise import OFF_DENOISE_PRESET, normalize_denoise_preset, reduce_audio_segment_noise
from aura.audio.enhancement_backends import enhance_import_audio_if_available
from aura.audio.meeting_distance import (
    DEFAULT_MEETING_DISTANCE_MODE,
    effective_denoise_preset_for_mode,
    meeting_distance_policy_for,
)
from aura.audio.normalization import FfmpegUnavailable, normalize_media_to_wav, normalization_cpu_status
from aura.asr.punctuation import restore_chinese_punctuation, should_restore_traditional_chinese_punctuation
from aura.diarization.pyannote_pipeline import DiarizationSettings, diarize_audio_file, validate_diarization_runtime
from aura.diarization.speaker_assignment import (
    UNKNOWN_SPEAKER,
    TranscriptSegment,
    assign_speakers,
    overlap_seconds,
)
from aura.review import (
    FINAL,
    LOW_CONFIDENCE_FLAG,
    LOW_CONFIDENCE_LOGPROB,
    SPEAKER_OVERLAP_FLAG,
    UNKNOWN_SPEAKER_FLAG,
    ReviewSegment,
    stable_segment_id,
)
from aura.settings import DEFAULT_SETTINGS
from aura.system.cuda import is_cuda_runtime_error
from aura.system.platform import detect_runtime_platform, platform_cuda_guidance
from aura.system.runtime_paths import append_transcript_backup, temp_normalized_path


class FileTranscriptionCancelled(RuntimeError):
    pass


@dataclass
class CancellationToken:
    cancelled: bool = False

    def request_cancel(self):
        self.cancelled = True

    def raise_if_cancelled(self):
        if self.cancelled:
            raise FileTranscriptionCancelled("File transcription cancelled.")


@dataclass(frozen=True)
class FileTranscriptionSettings:
    target_dbfs: float = DEFAULT_SETTINGS.target_dbfs
    beam_size: int = DEFAULT_SETTINGS.beam_size
    initial_prompt: str | None = DEFAULT_SETTINGS.file_initial_prompt
    language: str | None = DEFAULT_SETTINGS.language
    meeting_distance_mode: str = DEFAULT_SETTINGS.meeting_distance_mode
    enable_denoise: bool = DEFAULT_SETTINGS.denoise_enabled
    denoise_preset: str = DEFAULT_SETTINGS.denoise_preset
    diarization: DiarizationSettings = field(default_factory=DiarizationSettings)
    chinese_punctuation_enabled: bool = DEFAULT_SETTINGS.chinese_punctuation_enabled

    def __post_init__(self):
        meeting_distance_policy_for(self.meeting_distance_mode)
        selected_denoise = normalize_denoise_preset(self.enable_denoise, self.denoise_preset)
        object.__setattr__(
            self,
            "denoise_preset",
            effective_denoise_preset_for_mode(self.meeting_distance_mode, selected_denoise),
        )


@dataclass(frozen=True)
class FileTranscriptionResult:
    file_name: str
    lines: list[str] = field(default_factory=list)
    segments: list[ReviewSegment] = field(default_factory=list)
    cancelled: bool = False


def resolve_initial_prompt(prompt, default_prompt=DEFAULT_SETTINGS.file_initial_prompt):
    """Use the default prompt only when the caller did not provide a value."""
    if prompt is None:
        return default_prompt
    return str(prompt).strip()


def build_transcribe_kwargs(beam_size=5, language="zh", initial_prompt=None, condition_on_previous_text=True):
    kwargs = {
        "beam_size": int(beam_size) if beam_size else 5,
        "condition_on_previous_text": condition_on_previous_text,
    }
    if language:
        kwargs["language"] = language
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt
    return kwargs


def format_timestamp(seconds: float) -> str:
    h, m = divmod(int(seconds), 3600)
    m, s = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_segment(segment, speaker: str | None = None) -> str:
    timestamp = format_timestamp(segment.start)
    if speaker:
        return f"[{timestamp}] {speaker}: {segment.text}"
    return f"[{timestamp}] {segment.text}"


def transcript_segment_from_whisper(segment) -> TranscriptSegment:
    start = float(segment.start)
    end = float(getattr(segment, "end", start))
    if end < start:
        end = start
    raw_logprob = getattr(segment, "avg_logprob", None)
    try:
        asr_logprob = float(raw_logprob) if raw_logprob is not None else None
    except (TypeError, ValueError):
        asr_logprob = None
    return TranscriptSegment(
        start=start,
        end=end,
        text=str(segment.text),
        asr_logprob=asr_logprob,
    )


def restore_transcript_segments_punctuation(
    transcript_segments: list[TranscriptSegment],
    language: str | None,
    status_callback: Callable[[str], None] | None = None,
) -> list[TranscriptSegment]:
    combined_text = "".join(segment.text for segment in transcript_segments)
    if not should_restore_traditional_chinese_punctuation(combined_text, language):
        return transcript_segments

    if status_callback:
        status_callback("🔤 Restoring Traditional Chinese punctuation...")

    restored_segments = []
    backend = "skipped"
    detail = ""
    for segment in transcript_segments:
        result = restore_chinese_punctuation(segment.text, language=language)
        restored_segments.append(
            TranscriptSegment(
                start=segment.start,
                end=segment.end,
                text=result.text,
                asr_logprob=segment.asr_logprob,
            )
        )
        if result.backend == "model":
            backend = "model"
        elif backend == "skipped" and result.backend == "rule_fallback":
            backend = "rule_fallback"
        if result.detail and not detail:
            detail = result.detail

    if status_callback and backend != "skipped":
        if backend == "model":
            status_callback("✅ Traditional Chinese punctuation restored with the local model.")
        elif detail:
            status_callback(f"⚠️ Punctuation model unavailable; used rule fallback. Detail: {detail}")
        else:
            status_callback("✅ Traditional Chinese punctuation normalized with rule fallback.")

    return restored_segments


def normalize_file_transcription_error(error: Exception) -> str:
    error_msg = str(error)
    lower_msg = error_msg.lower()
    if is_cuda_runtime_error(error_msg):
        runtime = detect_runtime_platform()
        return (
            "This machine has not completed Project AURA RTX/CUDA activation.\n"
            "ASR is required to run on the RTX/CUDA GPU, and CPU fallback is disabled.\n\n"
            f"Environment: {runtime.label}\n"
            f"CUDA detail: {error_msg}\n"
            f"Next check: {platform_cuda_guidance(runtime)}\n\n"
            "After fixing the runtime, reload the model and import the file again."
        )
    if "ffmpeg" in lower_msg or "ffprobe" in lower_msg:
        return (
            f"{error_msg}\n\nImported media decoding depends on ffmpeg/ffprobe. "
            "Please install them and try again."
        )
    return error_msg


def prepare_import_audio(
    file_path: str,
    settings: FileTranscriptionSettings,
    temp_path: Path,
    cancellation: CancellationToken | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> Path:
    cancellation = cancellation or CancellationToken()
    file_name = os.path.basename(file_path)
    audio = None
    normalized = None
    enhanced_path = None
    try:
        if status_callback:
            status_callback(f"🔊 Preparing {file_name} for transcription...")
        cancellation.raise_if_cancelled()
        policy = meeting_distance_policy_for(settings.meeting_distance_mode)
        if status_callback and settings.meeting_distance_mode != DEFAULT_MEETING_DISTANCE_MODE:
            status_callback(
                f"🎚️ Meeting distance mode `{policy.mode}` selected "
                f"({policy.enhancement_backend}; {policy.backend_role})."
            )
        source_path = Path(file_path)
        denoise_preset = settings.denoise_preset
        enhanced_path = temp_path.with_name(f"{temp_path.stem}_enhanced.wav")
        enhancement = enhance_import_audio_if_available(
            input_path=source_path,
            output_path=enhanced_path,
            meeting_distance_mode=settings.meeting_distance_mode,
        )
        if enhancement.status != "not_requested" and status_callback:
            status_callback(
                f"🎚️ Import enhancement {enhancement.backend}: {enhancement.status} "
                f"({enhancement.note}; {enhancement.runtime_seconds:.3f}s)."
            )
        if enhancement.succeeded:
            source_path = enhancement.output_path
            denoise_preset = OFF_DENOISE_PRESET
            if status_callback:
                status_callback("🎚️ Model-based enhancement completed; skipping fallback noisereduce.")

        if denoise_preset == OFF_DENOISE_PRESET:
            if status_callback:
                status_callback(f"🔉 Fast-normalizing volume for {file_name} with FFmpeg...")
                status_callback(f"🧮 {normalization_cpu_status()}")
            try:
                result = normalize_media_to_wav(
                    str(source_path),
                    temp_path,
                    settings.target_dbfs,
                    progress_callback=status_callback,
                )
                cancellation.raise_if_cancelled()
                return result
            except (FfmpegUnavailable, RuntimeError):
                if status_callback:
                    status_callback(f"🔉 FFmpeg fast normalization unavailable; using Python path for {file_name}...")

        with open(source_path, "rb") as source:
            audio = AudioSegment.from_file(source)

        if denoise_preset != OFF_DENOISE_PRESET:
            if status_callback:
                status_callback(f"🧹 Applying {denoise_preset} denoise to {file_name}...")
            cancellation.raise_if_cancelled()
            audio = reduce_audio_segment_noise(audio, preset=denoise_preset)

        if status_callback:
            status_callback(f"🔉 Normalizing volume for {file_name}...")
        cancellation.raise_if_cancelled()
        normalized = audio.apply_gain(settings.target_dbfs - audio.dBFS)
        with temp_path.open("wb") as target:
            normalized.export(target, format="wav")
        cancellation.raise_if_cancelled()
        return temp_path
    finally:
        if audio:
            del audio
        if normalized:
            del normalized
        if enhanced_path and enhanced_path.exists():
            enhanced_path.unlink()
        gc.collect()


def transcribe_prepared_file(model, prepared_path: Path, settings: FileTranscriptionSettings):
    return model.transcribe(
        str(prepared_path),
        **build_transcribe_kwargs(
            beam_size=settings.beam_size,
            language=settings.language,
            initial_prompt=settings.initial_prompt,
            condition_on_previous_text=True,
        ),
    )


def transcribe_file(
    model,
    file_path: str,
    settings: FileTranscriptionSettings,
    worker_id,
    cancellation: CancellationToken | None = None,
    status_callback: Callable[[str], None] | None = None,
    line_callback: Callable[[str], None] | None = None,
    diarization_runner: Callable[[Path, DiarizationSettings], list] | None = None,
) -> FileTranscriptionResult:
    cancellation = cancellation or CancellationToken()
    file_name = os.path.basename(file_path)
    temp_path = temp_normalized_path(worker_id)
    lines = []
    try:
        if diarization_runner is None:
            validate_diarization_runtime(settings.diarization)
        prepared_path = prepare_import_audio(
            file_path=file_path,
            settings=settings,
            temp_path=temp_path,
            cancellation=cancellation,
            status_callback=status_callback,
        )
        segments, info = transcribe_prepared_file(model, prepared_path, settings)
        transcript_segments = []
        detected_language = getattr(info, "language", None) or settings.language

        for segment in segments:
            cancellation.raise_if_cancelled()
            transcript_segments.append(transcript_segment_from_whisper(segment))

        if settings.chinese_punctuation_enabled:
            transcript_segments = restore_transcript_segments_punctuation(
                transcript_segments,
                language=detected_language,
                status_callback=status_callback,
            )
        cancellation.raise_if_cancelled()

        speaker_turns = []
        if settings.diarization.enabled:
            if status_callback:
                status_callback(
                    f"👥 Identifying speakers "
                    f"({settings.diarization.min_speakers}-{settings.diarization.max_speakers})..."
                )
            cancellation.raise_if_cancelled()
            runner = diarization_runner or diarize_audio_file
            speaker_turns = runner(prepared_path, settings.diarization)
            cancellation.raise_if_cancelled()
            labeled_segments = assign_speakers(transcript_segments, speaker_turns)
            formatted_lines = [
                format_segment(item.transcript, speaker=item.speaker)
                for item in labeled_segments
            ]
            speakers = [item.speaker for item in labeled_segments]
        else:
            formatted_lines = [format_segment(segment) for segment in transcript_segments]
            speakers = [UNKNOWN_SPEAKER] * len(transcript_segments)

        review_segments = [
            ReviewSegment(
                segment_id=stable_segment_id(index, round(segment.start * 1000)),
                start_ms=round(segment.start * 1000),
                end_ms=max(round(segment.start * 1000), round(segment.end * 1000)),
                text=segment.text,
                speaker=speakers[index],
                state=FINAL,
                asr_logprob=segment.asr_logprob,
                review_flags=tuple(
                    flag
                    for flag, active in (
                        (
                            UNKNOWN_SPEAKER_FLAG,
                            speakers[index] == UNKNOWN_SPEAKER,
                        ),
                        (
                            SPEAKER_OVERLAP_FLAG,
                            len(
                                {
                                    turn.speaker
                                    for turn in speaker_turns
                                    if overlap_seconds(
                                        segment.start,
                                        segment.end,
                                        turn.start,
                                        turn.end,
                                    )
                                    > 0
                                }
                            )
                            > 1,
                        ),
                        (
                            LOW_CONFIDENCE_FLAG,
                            segment.asr_logprob is not None
                            and segment.asr_logprob
                            < LOW_CONFIDENCE_LOGPROB,
                        ),
                    )
                    if active
                ),
            )
            for index, segment in enumerate(transcript_segments)
        ]

        for formatted_text in formatted_lines:
            cancellation.raise_if_cancelled()
            lines.append(formatted_text)
            if line_callback:
                line_callback(formatted_text)
            append_transcript_backup(formatted_text)

        if status_callback:
            if cancellation.cancelled:
                status_callback(f"⚠️ Cancelled transcribing {file_name}")
            else:
                status_callback(f"✅ Finished transcribing {file_name}")
        return FileTranscriptionResult(
            file_name=file_name,
            lines=lines,
            segments=review_segments,
            cancelled=cancellation.cancelled,
        )
    finally:
        if temp_path.exists():
            temp_path.unlink()
