import gc
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pydub import AudioSegment

from aura.audio.denoise import OFF_DENOISE_PRESET, normalize_denoise_preset, reduce_audio_segment_noise
from aura.audio.normalization import FfmpegUnavailable, normalize_media_to_wav, normalization_cpu_status
from aura.diarization.pyannote_pipeline import DiarizationSettings, diarize_audio_file
from aura.diarization.speaker_assignment import TranscriptSegment, assign_speakers
from aura.settings import DEFAULT_SETTINGS
from aura.system.cuda import is_cuda_runtime_error
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
    enable_denoise: bool = DEFAULT_SETTINGS.denoise_enabled
    denoise_preset: str = DEFAULT_SETTINGS.denoise_preset
    diarization: DiarizationSettings = field(default_factory=DiarizationSettings)

    def __post_init__(self):
        object.__setattr__(
            self,
            "denoise_preset",
            normalize_denoise_preset(self.enable_denoise, self.denoise_preset),
        )


@dataclass(frozen=True)
class FileTranscriptionResult:
    file_name: str
    lines: list[str] = field(default_factory=list)
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
    return TranscriptSegment(start=start, end=end, text=str(segment.text))


def normalize_file_transcription_error(error: Exception) -> str:
    error_msg = str(error)
    lower_msg = error_msg.lower()
    if is_cuda_runtime_error(error_msg):
        return (
            "CUDA runtime is incomplete on this machine.\n"
            "ASR is required to run on the RTX/CUDA GPU, but a CUDA runtime library is missing.\n\n"
            "CPU fallback is disabled. Install CUDA/cuBLAS/cuDNN support in this uv environment, "
            "then reload the model and import the file again."
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
    try:
        if status_callback:
            status_callback(f"🔊 Preparing {file_name} for transcription...")
        cancellation.raise_if_cancelled()

        if settings.denoise_preset == OFF_DENOISE_PRESET:
            if status_callback:
                status_callback(f"🔉 Fast-normalizing volume for {file_name} with FFmpeg...")
                status_callback(f"🧮 {normalization_cpu_status()}")
            try:
                result = normalize_media_to_wav(file_path, temp_path, settings.target_dbfs)
                cancellation.raise_if_cancelled()
                return result
            except (FfmpegUnavailable, RuntimeError):
                if status_callback:
                    status_callback(f"🔉 FFmpeg fast normalization unavailable; using Python path for {file_name}...")

        with open(file_path, "rb") as source:
            audio = AudioSegment.from_file(source)

        if settings.denoise_preset != OFF_DENOISE_PRESET:
            if status_callback:
                status_callback(f"🧹 Applying {settings.denoise_preset} denoise to {file_name}...")
            cancellation.raise_if_cancelled()
            audio = reduce_audio_segment_noise(audio, preset=settings.denoise_preset)

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
        prepared_path = prepare_import_audio(
            file_path=file_path,
            settings=settings,
            temp_path=temp_path,
            cancellation=cancellation,
            status_callback=status_callback,
        )
        segments, info = transcribe_prepared_file(model, prepared_path, settings)
        transcript_segments = []

        for segment in segments:
            cancellation.raise_if_cancelled()
            transcript_segments.append(transcript_segment_from_whisper(segment))

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
        else:
            formatted_lines = [format_segment(segment) for segment in transcript_segments]

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
        return FileTranscriptionResult(file_name=file_name, lines=lines, cancelled=cancellation.cancelled)
    finally:
        if temp_path.exists():
            temp_path.unlink()
