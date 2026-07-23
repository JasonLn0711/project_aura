import gc
import logging
from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment

from aura.audio.normalization import (
    FfmpegUnavailable,
    MP3_EXPORT_ARGS,
    normalize_media_with_ffmpeg,
    normalization_cpu_status,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecordingAudioFormat:
    key: str
    suffix: str
    codec: str
    ffmpeg_format: str
    ffmpeg_args: list[str]
    pydub_format: str
    pydub_parameters: list[str]


M4A_EXPORT_ARGS = ["-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"]
RECORDING_AUDIO_FORMATS = {
    "m4a": RecordingAudioFormat(
        key="m4a",
        suffix=".m4a",
        codec="aac",
        ffmpeg_format="ipod",
        ffmpeg_args=M4A_EXPORT_ARGS,
        pydub_format="ipod",
        pydub_parameters=M4A_EXPORT_ARGS,
    ),
    "mp3": RecordingAudioFormat(
        key="mp3",
        suffix=".mp3",
        codec="libmp3lame",
        ffmpeg_format="mp3",
        ffmpeg_args=MP3_EXPORT_ARGS,
        pydub_format="mp3",
        pydub_parameters=MP3_EXPORT_ARGS,
    ),
}


def recording_audio_format_spec(audio_format: str) -> RecordingAudioFormat:
    try:
        return RECORDING_AUDIO_FORMATS[audio_format]
    except KeyError as exc:
        supported = ", ".join(sorted(RECORDING_AUDIO_FORMATS))
        raise ValueError(f"Unsupported recording audio format: {audio_format}. Supported formats: {supported}") from exc


def audio_path_for_wav(wav_path: str | Path, audio_format: str = "m4a") -> Path:
    return Path(wav_path).with_suffix(recording_audio_format_spec(audio_format).suffix)


def mp3_path_for_wav(wav_path: str | Path) -> Path:
    return audio_path_for_wav(wav_path, "mp3")


def normalize_wav_to_recording_audio(
    wav_path: str | Path,
    target_dbfs: float,
    audio_format: str = "m4a",
    *,
    remove_source: bool = True,
) -> Path:
    wav_path = Path(wav_path)
    spec = recording_audio_format_spec(audio_format)
    output_path = audio_path_for_wav(wav_path, spec.key)
    try:
        logger.info("Recording normalization CPU budget: %s", normalization_cpu_status())
        normalize_media_with_ffmpeg(
            input_path=wav_path,
            output_path=output_path,
            target_dbfs=target_dbfs,
            output_format=spec.ffmpeg_format,
            extra_output_args=spec.ffmpeg_args,
        )
        if remove_source and wav_path.exists():
            wav_path.unlink()
        return output_path
    except (FfmpegUnavailable, RuntimeError):
        pass

    audio = None
    normalized = None
    try:
        with wav_path.open("rb") as source:
            audio = AudioSegment.from_wav(source)
        normalized = audio.apply_gain(target_dbfs - audio.dBFS)
        with output_path.open("wb") as target:
            normalized.export(target, format=spec.pydub_format, parameters=spec.pydub_parameters)
        if remove_source and wav_path.exists():
            wav_path.unlink()
        return output_path
    finally:
        if audio:
            del audio
        if normalized:
            del normalized
        gc.collect()


def normalize_wav_to_mp3(wav_path: str | Path, target_dbfs: float) -> Path:
    return normalize_wav_to_recording_audio(wav_path, target_dbfs, "mp3")
