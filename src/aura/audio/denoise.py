from dataclasses import dataclass

import numpy as np
import noisereduce as nr
from pydub import AudioSegment

from aura.config import SAMPLE_RATE

MIN_DENOISE_SAMPLES = 64
SILENCE_RMS_THRESHOLD = 1e-6
DEFAULT_ACTIVE_DENOISE_PRESET = "light"
OFF_DENOISE_PRESET = "off"


@dataclass(frozen=True)
class DenoisePolicy:
    name: str
    prop_decrease: float
    description: str


DENOISE_POLICIES = {
    OFF_DENOISE_PRESET: DenoisePolicy(
        name=OFF_DENOISE_PRESET,
        prop_decrease=0.0,
        description="No denoise; preserve the original audio.",
    ),
    DEFAULT_ACTIVE_DENOISE_PRESET: DenoisePolicy(
        name=DEFAULT_ACTIVE_DENOISE_PRESET,
        prop_decrease=0.35,
        description="Conservative denoise for normal noisy rooms.",
    ),
    "medium": DenoisePolicy(
        name="medium",
        prop_decrease=0.55,
        description="Stronger denoise for noisier environments; may affect speech detail.",
    ),
}


def normalize_denoise_preset(enable_denoise: bool = False, preset: str | None = None) -> str:
    if preset and preset != OFF_DENOISE_PRESET:
        if preset not in DENOISE_POLICIES:
            raise ValueError(f"Unknown denoise preset: {preset}")
        return preset
    return DEFAULT_ACTIVE_DENOISE_PRESET if enable_denoise else OFF_DENOISE_PRESET


def denoise_policy_for(preset: str) -> DenoisePolicy:
    try:
        return DENOISE_POLICIES[preset]
    except KeyError as exc:
        raise ValueError(f"Unknown denoise preset: {preset}") from exc


def reduce_noise_safely(
    audio_np: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    preset: str = DEFAULT_ACTIVE_DENOISE_PRESET,
) -> np.ndarray:
    """Run noisereduce on live buffers without invalid short-window STFT settings."""
    policy = denoise_policy_for(preset)
    if policy.name == OFF_DENOISE_PRESET:
        return audio_np
    if audio_np.size < MIN_DENOISE_SAMPLES:
        return audio_np
    if float(np.sqrt(np.mean(audio_np.astype(np.float32) ** 2))) < SILENCE_RMS_THRESHOLD:
        return audio_np

    n_fft = min(1024, int(audio_np.size))
    hop_length = max(1, n_fft // 4)

    return nr.reduce_noise(
        y=audio_np,
        sr=sample_rate,
        stationary=False,
        prop_decrease=policy.prop_decrease,
        n_fft=n_fft,
        win_length=n_fft,
        hop_length=hop_length,
    )


def reduce_audio_segment_noise(
    audio: AudioSegment,
    preset: str = DEFAULT_ACTIVE_DENOISE_PRESET,
) -> AudioSegment:
    """Apply the safe denoise policy to an AudioSegment while preserving channels."""
    if denoise_policy_for(preset).name == OFF_DENOISE_PRESET:
        return audio

    audio = audio.set_sample_width(2)
    samples = np.array(audio.get_array_of_samples(), dtype=np.int16)

    if audio.channels > 1:
        samples = samples.reshape((-1, audio.channels))
        denoised_channels = [
            reduce_noise_safely(samples[:, channel_idx].astype(np.float32), audio.frame_rate, preset=preset)
            for channel_idx in range(audio.channels)
        ]
        denoised = np.stack(denoised_channels, axis=1)
    else:
        denoised = reduce_noise_safely(samples.astype(np.float32), audio.frame_rate, preset=preset)

    denoised = np.clip(denoised, -32768, 32767).astype(np.int16)
    return audio._spawn(denoised.tobytes())
