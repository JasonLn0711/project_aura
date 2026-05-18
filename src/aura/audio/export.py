import gc
from pathlib import Path

from pydub import AudioSegment

from aura.audio.normalization import FfmpegUnavailable, normalize_wav_to_mp3_with_ffmpeg


def mp3_path_for_wav(wav_path: str | Path) -> Path:
    return Path(wav_path).with_suffix(".mp3")


def normalize_wav_to_mp3(wav_path: str | Path, target_dbfs: float) -> Path:
    wav_path = Path(wav_path)
    mp3_path = mp3_path_for_wav(wav_path)
    try:
        normalize_wav_to_mp3_with_ffmpeg(wav_path, mp3_path, target_dbfs)
        if wav_path.exists():
            wav_path.unlink()
        return mp3_path
    except (FfmpegUnavailable, RuntimeError):
        pass

    audio = None
    normalized = None
    try:
        with wav_path.open("rb") as source:
            audio = AudioSegment.from_wav(source)
        normalized = audio.apply_gain(target_dbfs - audio.dBFS)
        with mp3_path.open("wb") as target:
            normalized.export(target, format="mp3")
        if wav_path.exists():
            wav_path.unlink()
        return mp3_path
    finally:
        if audio:
            del audio
        if normalized:
            del normalized
        gc.collect()
