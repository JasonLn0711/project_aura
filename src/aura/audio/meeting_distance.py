from dataclasses import dataclass

import numpy as np

from aura.audio.denoise import DEFAULT_ACTIVE_DENOISE_PRESET, OFF_DENOISE_PRESET

MEETING_DISTANCE_OFF = "off"
MEETING_DISTANCE_NORMAL = "normal"
MEETING_DISTANCE_FAR_SPEAKER = "far-speaker"
MEETING_DISTANCE_RESCUE_OFFLINE = "rescue-offline"
DEFAULT_MEETING_DISTANCE_MODE = MEETING_DISTANCE_OFF

_DENOISE_STRENGTH = {
    OFF_DENOISE_PRESET: 0,
    DEFAULT_ACTIVE_DENOISE_PRESET: 1,
    "medium": 2,
}


@dataclass(frozen=True)
class MeetingDistancePolicy:
    mode: str
    denoise_preset: str
    live_energy_gate_rms: float
    live_energy_bridge_ms: int
    live_agc_enabled: bool
    live_agc_target_rms: float
    live_agc_max_gain: float
    enhancement_backend: str
    backend_role: str
    live_supported: bool
    import_supported: bool
    description: str

    def metadata(self) -> dict:
        return {
            "meeting_distance_mode": self.mode,
            "meeting_distance_description": self.description,
            "meeting_distance_denoise_preset": self.denoise_preset,
            "meeting_distance_live_energy_gate_rms": self.live_energy_gate_rms,
            "meeting_distance_live_energy_bridge_ms": self.live_energy_bridge_ms,
            "meeting_distance_live_agc_enabled": self.live_agc_enabled,
            "meeting_distance_live_agc_target_rms": self.live_agc_target_rms,
            "meeting_distance_live_agc_max_gain": self.live_agc_max_gain,
            "meeting_distance_enhancement_backend": self.enhancement_backend,
            "meeting_distance_backend_role": self.backend_role,
            "meeting_distance_live_supported": self.live_supported,
            "meeting_distance_import_supported": self.import_supported,
        }


MEETING_DISTANCE_POLICIES = {
    MEETING_DISTANCE_OFF: MeetingDistancePolicy(
        mode=MEETING_DISTANCE_OFF,
        denoise_preset=OFF_DENOISE_PRESET,
        live_energy_gate_rms=1000.0,
        live_energy_bridge_ms=120,
        live_agc_enabled=False,
        live_agc_target_rms=0.08,
        live_agc_max_gain=1.0,
        enhancement_backend="none",
        backend_role="preserve-original",
        live_supported=True,
        import_supported=True,
        description="Preserve the original signal; use when capture quality is already controlled.",
    ),
    MEETING_DISTANCE_NORMAL: MeetingDistancePolicy(
        mode=MEETING_DISTANCE_NORMAL,
        denoise_preset=DEFAULT_ACTIVE_DENOISE_PRESET,
        live_energy_gate_rms=1000.0,
        live_energy_bridge_ms=120,
        live_agc_enabled=False,
        live_agc_target_rms=0.08,
        live_agc_max_gain=1.0,
        enhancement_backend="noisereduce-light",
        backend_role="normal-room-baseline",
        live_supported=True,
        import_supported=True,
        description="Normal meeting-room preprocessing: light denoise plus existing volume normalization.",
    ),
    MEETING_DISTANCE_FAR_SPEAKER: MeetingDistancePolicy(
        mode=MEETING_DISTANCE_FAR_SPEAKER,
        denoise_preset="medium",
        live_energy_gate_rms=650.0,
        live_energy_bridge_ms=240,
        live_agc_enabled=True,
        live_agc_target_rms=0.08,
        live_agc_max_gain=4.0,
        enhancement_backend="deepfilternet3-candidate",
        backend_role="near-real-time-candidate",
        live_supported=True,
        import_supported=True,
        description=(
            "Far-speaker fallback: preserve weak speech turns with a longer VAD bridge, "
            "moderate denoise, and bounded live segment gain."
        ),
    ),
    MEETING_DISTANCE_RESCUE_OFFLINE: MeetingDistancePolicy(
        mode=MEETING_DISTANCE_RESCUE_OFFLINE,
        denoise_preset="medium",
        live_energy_gate_rms=650.0,
        live_energy_bridge_ms=240,
        live_agc_enabled=True,
        live_agc_target_rms=0.08,
        live_agc_max_gain=4.0,
        enhancement_backend="clearvoice-mossformer-candidate",
        backend_role="offline-import-rescue-candidate",
        live_supported=False,
        import_supported=True,
        description=(
            "Offline rescue profile for difficult imported recordings; model-based enhancement "
            "must be promoted only after transcript-quality evaluation."
        ),
    ),
}


def normalize_meeting_distance_mode(mode: str | None) -> str:
    normalized = (mode or DEFAULT_MEETING_DISTANCE_MODE).strip().lower()
    if normalized not in MEETING_DISTANCE_POLICIES:
        raise ValueError(f"Unknown meeting distance mode: {mode}")
    return normalized


def meeting_distance_policy_for(mode: str | None) -> MeetingDistancePolicy:
    return MEETING_DISTANCE_POLICIES[normalize_meeting_distance_mode(mode)]


def effective_denoise_preset_for_mode(mode: str | None, selected_preset: str | None) -> str:
    policy_preset = meeting_distance_policy_for(mode).denoise_preset
    selected = selected_preset or OFF_DENOISE_PRESET
    if selected not in _DENOISE_STRENGTH:
        raise ValueError(f"Unknown denoise preset: {selected_preset}")
    if policy_preset == OFF_DENOISE_PRESET:
        return selected
    return max((policy_preset, selected), key=lambda preset: _DENOISE_STRENGTH[preset])


def apply_live_segment_agc(audio_np: np.ndarray, policy: MeetingDistancePolicy) -> np.ndarray:
    """Bounded speech-segment gain for ASR input; this does not improve SNR."""
    if not policy.live_agc_enabled or audio_np.size == 0:
        return audio_np

    float_audio = audio_np.astype(np.float32, copy=False)
    rms = float(np.sqrt(np.mean(float_audio * float_audio)))
    if rms <= 1e-6 or rms >= policy.live_agc_target_rms:
        return audio_np

    gain = min(policy.live_agc_max_gain, policy.live_agc_target_rms / rms)
    if gain <= 1.0:
        return audio_np

    boosted = np.clip(float_audio * gain, -0.95, 0.95)
    return boosted.astype(np.float32, copy=False)
