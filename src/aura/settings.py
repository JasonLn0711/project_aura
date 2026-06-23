from dataclasses import dataclass

from aura.config import (
    CHINESE_PUNCTUATION_MODEL_ID,
    COMPUTE_TYPE,
    DEFAULT_LIVE_CAPTURE_SOURCE,
    DEFAULT_LIVE_PROMPT,
    DEFAULT_PROMPT,
    DEVICE,
    DIARIZATION_MODEL_ID,
    MODEL_ID,
    SUMMARY_MODEL_ID,
)
from aura.audio.meeting_distance import DEFAULT_MEETING_DISTANCE_MODE


@dataclass(frozen=True)
class AppSettings:
    model_id: str = MODEL_ID
    device: str = DEVICE
    compute_type: str = COMPUTE_TYPE
    target_dbfs: float = -20.0
    beam_size: int = 5
    language: str | None = "zh"
    live_capture_source: str = DEFAULT_LIVE_CAPTURE_SOURCE
    meeting_distance_mode: str = DEFAULT_MEETING_DISTANCE_MODE
    live_max_segment_len_sec: float = 16.0
    live_energy_gate_rms: float = 1000.0
    recording_audio_format: str = "m4a"
    file_initial_prompt: str | None = DEFAULT_PROMPT
    live_initial_prompt: str | None = DEFAULT_LIVE_PROMPT
    denoise_enabled: bool = False
    denoise_preset: str = "off"
    speaker_diarization_enabled: bool = False
    speaker_min_speakers: int = 2
    speaker_max_speakers: int = 6
    speaker_diarization_model: str = DIARIZATION_MODEL_ID
    speaker_diarization_device: str = DEVICE
    speaker_diarization_use_exclusive: bool = True
    llm_summary_enabled: bool = False
    llm_summary_model: str = SUMMARY_MODEL_ID
    llm_summary_quantization: str = "ollama_q4_K_M_local_tag"
    llm_summary_max_new_tokens: int = 768
    llm_summary_temperature: float = 0.2
    chinese_punctuation_enabled: bool = True
    chinese_punctuation_model: str = CHINESE_PUNCTUATION_MODEL_ID
    splitter_target_minutes: int = 40
    splitter_tolerance_minutes: int = 5


DEFAULT_SETTINGS = AppSettings()
