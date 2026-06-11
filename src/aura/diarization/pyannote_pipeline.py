import importlib.util
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from aura.diarization.speaker_assignment import SpeakerTurn
from aura.system.cuda import preload_cuda_runtime_libraries


DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"
HUGGINGFACE_TOKEN_ENV = "HUGGINGFACE_TOKEN"
HF_TOKEN_ENV = "HF_TOKEN"
AURA_HF_TOKEN_FILE_ENV = "AURA_HF_TOKEN_FILE"
DEFAULT_HF_TOKEN_SECRET_PATH = Path.home() / ".codex" / "secrets" / "project-aura-hf.env"


class DiarizationDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiarizationSettings:
    enabled: bool = False
    min_speakers: int = 2
    max_speakers: int = 6
    model_id: str = DEFAULT_DIARIZATION_MODEL
    device: str = "cuda"
    use_exclusive: bool = True

    def __post_init__(self):
        if self.min_speakers < 1:
            raise ValueError("min_speakers must be at least 1")
        if self.max_speakers < self.min_speakers:
            raise ValueError("max_speakers must be greater than or equal to min_speakers")


def _token_from_env_file(path: Path) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            parts = shlex.split(stripped, posix=True)
        except ValueError:
            continue
        if parts and parts[0] == "export":
            parts = parts[1:]
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if key in {HUGGINGFACE_TOKEN_ENV, HF_TOKEN_ENV} and value:
                return value
    return None


def local_hf_token_secret_paths() -> tuple[Path, ...]:
    configured_path = os.environ.get(AURA_HF_TOKEN_FILE_ENV)
    if configured_path:
        return (Path(configured_path).expanduser(),)
    return (DEFAULT_HF_TOKEN_SECRET_PATH,)


def huggingface_token() -> str | None:
    token = os.environ.get(HUGGINGFACE_TOKEN_ENV) or os.environ.get(HF_TOKEN_ENV)
    if token:
        return token
    for path in local_hf_token_secret_paths():
        token = _token_from_env_file(path)
        if token:
            return token
    return None


def pyannote_audio_available() -> bool:
    try:
        return importlib.util.find_spec("pyannote.audio") is not None
    except ModuleNotFoundError:
        return False


def validate_diarization_runtime(settings: DiarizationSettings):
    if not settings.enabled:
        return
    if not pyannote_audio_available():
        raise DiarizationDependencyError(
            "Speaker diarization requires the optional `pyannote.audio` dependency. "
            "Install it with `python -m pip install -e .[diarization]`."
        )
    if not huggingface_token():
        raise DiarizationDependencyError(
            "Speaker diarization requires a Hugging Face access token. "
            f"Set `{HUGGINGFACE_TOKEN_ENV}` or `{HF_TOKEN_ENV}` after accepting the pyannote model terms."
        )


def pipeline_kwargs(settings: DiarizationSettings) -> dict:
    if settings.min_speakers == settings.max_speakers:
        return {"num_speakers": settings.min_speakers}
    return {
        "min_speakers": settings.min_speakers,
        "max_speakers": settings.max_speakers,
    }


def _load_pyannote_pipeline(settings: DiarizationSettings):
    validate_diarization_runtime(settings)

    if settings.device == "cuda":
        preload_cuda_runtime_libraries()

    from pyannote.audio import Pipeline
    token = huggingface_token()

    pipeline = Pipeline.from_pretrained(settings.model_id, token=token)

    if settings.device == "cuda":
        try:
            import torch

            if torch.cuda.is_available():
                pipeline.to(torch.device("cuda"))
        except ImportError:
            pass

    return pipeline


def _annotation_from_output(output, use_exclusive: bool):
    if use_exclusive and hasattr(output, "exclusive_speaker_diarization"):
        return output.exclusive_speaker_diarization
    if hasattr(output, "speaker_diarization"):
        return output.speaker_diarization
    return output


def speaker_turns_from_annotation(annotation) -> list[SpeakerTurn]:
    turns = []

    if hasattr(annotation, "itertracks"):
        iterator = annotation.itertracks(yield_label=True)
        for segment, _track, speaker in iterator:
            turns.append(SpeakerTurn(float(segment.start), float(segment.end), str(speaker)))
        return turns

    for turn, speaker in annotation:
        turns.append(SpeakerTurn(float(turn.start), float(turn.end), str(speaker)))
    return turns


def pipeline_audio_input(audio_path: str | Path):
    import torchaudio

    waveform, sample_rate = torchaudio.load(str(audio_path))
    return {"waveform": waveform, "sample_rate": sample_rate}


def diarize_audio_file(audio_path: str | Path, settings: DiarizationSettings) -> list[SpeakerTurn]:
    pipeline = _load_pyannote_pipeline(settings)
    output = pipeline(pipeline_audio_input(audio_path), **pipeline_kwargs(settings))
    annotation = _annotation_from_output(output, settings.use_exclusive)
    return speaker_turns_from_annotation(annotation)
