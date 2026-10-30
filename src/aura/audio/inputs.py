"""Qt-independent audio device discovery, capture, and mixing."""
import logging
import shutil
import subprocess
from dataclasses import dataclass
import numpy as np
import pyaudio
from aura.config import (SAMPLE_RATE, CHUNK_SIZE, CHUNK_MS, LIVE_CAPTURE_MICROPHONE,
                         LIVE_CAPTURE_SYSTEM, LIVE_CAPTURE_SYSTEM_MICROPHONE)
from aura.system.native_audio import no_alsa_err, suppress_native_stderr

logger = logging.getLogger(__name__)

MIX_ACTIVE_RMS_FLOOR = 80.0
MIX_MIN_GAIN = 0.5
MIX_MAX_GAIN = 3.0
MIX_HEADROOM = 0.8
ENERGY_BRIDGE_MS = 120
NO_VOICE_AUTO_STOP_MINUTES = 20


@dataclass(frozen=True)
class PulseSource:
    index: str
    name: str
    driver: str
    sample_spec: str
    state: str


def parse_pactl_sources(output: str) -> list[PulseSource]:
    sources = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            parts = line.split(maxsplit=4)
        if len(parts) < 5:
            continue
        sources.append(
            PulseSource(
                index=parts[0],
                name=parts[1],
                driver=parts[2],
                sample_spec=parts[3],
                state=parts[4],
            )
        )
    return sources


def pactl_info_value(output: str, label: str) -> str | None:
    prefix = f"{label}:"
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def list_pulse_sources() -> list[PulseSource]:
    if not shutil.which("pactl"):
        return []
    result = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    return parse_pactl_sources(result.stdout)


def pulse_default_source_and_sink() -> tuple[str | None, str | None]:
    if not shutil.which("pactl"):
        return None, None
    result = subprocess.run(["pactl", "info"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None, None
    return (
        pactl_info_value(result.stdout, "Default Source"),
        pactl_info_value(result.stdout, "Default Sink"),
    )


def is_monitor_source(source: PulseSource) -> bool:
    name = source.name.lower()
    return name.endswith(".monitor") or ".monitor" in name


def _first_running(sources: list[PulseSource]) -> PulseSource | None:
    for source in sources:
        if source.state.upper() == "RUNNING":
            return source
    return sources[0] if sources else None


def select_system_pulse_source(
    sources: list[PulseSource],
    default_sink: str | None = None,
) -> PulseSource | None:
    monitor_sources = [source for source in sources if is_monitor_source(source)]
    if default_sink:
        default_monitor = f"{default_sink}.monitor"
        for source in monitor_sources:
            if source.name == default_monitor:
                return source
    return _first_running(monitor_sources)


def select_microphone_pulse_source(
    sources: list[PulseSource],
    default_source: str | None = None,
) -> PulseSource | None:
    microphone_sources = [source for source in sources if not is_monitor_source(source)]
    if default_source:
        for source in microphone_sources:
            if source.name == default_source:
                return source
    preferred_tokens = ("mic", "microphone", "headset", "usb", "analog", "alsa_input")
    for source in microphone_sources:
        name = source.name.lower()
        if any(token in name for token in preferred_tokens):
            return source
    return _first_running(microphone_sources)


def select_pulse_sources_for_mode(
    mode: str,
    sources: list[PulseSource],
    default_source: str | None = None,
    default_sink: str | None = None,
) -> list[PulseSource]:
    if mode == LIVE_CAPTURE_MICROPHONE:
        microphone = select_microphone_pulse_source(sources, default_source)
        return [microphone] if microphone else []
    if mode == LIVE_CAPTURE_SYSTEM:
        system = select_system_pulse_source(sources, default_sink)
        return [system] if system else []

    system = select_system_pulse_source(sources, default_sink)
    microphone = select_microphone_pulse_source(sources, default_source)
    selected = []
    for source in (system, microphone):
        if source and source.name not in {item.name for item in selected}:
            selected.append(source)
    return selected


def frame_rms(frame: np.ndarray) -> float:
    if len(frame) == 0:
        return 0.0
    float_frame = frame.astype(np.float32)
    return float(np.sqrt(np.mean(float_frame * float_frame)))


def gain_for_rms(source_rms: float, target_rms: float) -> float:
    if source_rms < MIX_ACTIVE_RMS_FLOOR or target_rms <= 0:
        return 1.0
    return float(np.clip(target_rms / source_rms, MIX_MIN_GAIN, MIX_MAX_GAIN))


def balance_audio_frames(frames: list[np.ndarray]) -> list[np.ndarray]:
    if not frames:
        return []

    min_length = min(len(frame) for frame in frames)
    if min_length <= 0:
        return []

    trimmed_frames = [frame[:min_length].astype(np.float32) for frame in frames]
    rms_values = [frame_rms(frame) for frame in trimmed_frames]
    active_indices = [index for index, rms in enumerate(rms_values) if rms >= MIX_ACTIVE_RMS_FLOOR]
    if not active_indices:
        return []

    if len(active_indices) == 1:
        return [trimmed_frames[active_indices[0]]]

    target_rms = float(np.median([rms_values[index] for index in active_indices]))
    return [
        trimmed_frames[index] * gain_for_rms(rms_values[index], target_rms)
        for index in active_indices
    ]


def mix_audio_frames(frames: list[np.ndarray]) -> np.ndarray:
    if not frames:
        return np.zeros(CHUNK_SIZE, dtype=np.int16)
    if len(frames) == 1:
        return frames[0].astype(np.int16, copy=False)

    output_length = min(len(frame) for frame in frames)
    balanced_frames = balance_audio_frames(frames)
    if not balanced_frames:
        if output_length <= 0:
            output_length = CHUNK_SIZE
        return np.zeros(output_length, dtype=np.int16)

    if len(balanced_frames) == 1:
        return np.clip(balanced_frames[0], -32768, 32767).astype(np.int16)

    stacked = np.stack(balanced_frames, axis=0)
    mixed = stacked.sum(axis=0) * (MIX_HEADROOM / len(balanced_frames))
    return np.clip(mixed, -32768, 32767).astype(np.int16)


def track_audio_frames(
    mode: str,
    sources: list[PulseSource],
    frames: list[np.ndarray],
) -> dict[str, np.ndarray]:
    if len(sources) != len(frames):
        raise ValueError("sources and frames must have the same length")
    tracks = {"mixed": mix_audio_frames(frames)}
    if mode == LIVE_CAPTURE_SYSTEM:
        if frames:
            tracks["system"] = frames[0]
        return tracks
    if mode == LIVE_CAPTURE_MICROPHONE:
        if frames:
            tracks["microphone"] = frames[0]
        return tracks
    for source, frame in zip(sources, frames):
        tracks.setdefault("system" if is_monitor_source(source) else "microphone", frame)
    return tracks


def frames_for_duration_seconds(duration_seconds: float) -> int:
    if duration_seconds <= 0:
        return 0
    return int(np.ceil(duration_seconds * 1000 / CHUNK_MS))


def should_auto_stop_for_no_voice(no_voice_frames: int, limit_frames: int) -> bool:
    return limit_frames > 0 and no_voice_frames >= limit_frames


from aura.audio.vad import should_treat_frame_as_speech


def trim_trailing_unvoiced_frames(frames: list[bytes], voiced_flags: list[bool]) -> tuple[list[bytes], int]:
    if len(frames) != len(voiced_flags):
        raise ValueError("frames and voiced_flags must have the same length")
    for index in range(len(voiced_flags) - 1, -1, -1):
        if voiced_flags[index]:
            trimmed_count = len(frames) - index - 1
            return frames[: index + 1], trimmed_count
    return [], len(frames)


class PulseRawInput:
    def __init__(self, source: PulseSource):
        self.source = source
        self.process = None

    def start(self):
        parec = shutil.which("parec")
        if not parec:
            raise RuntimeError("parec is not available")
        command = [
            parec,
            "--device",
            self.source.name,
            "--format",
            "s16le",
            "--rate",
            str(SAMPLE_RATE),
            "--channels",
            "1",
            "--latency-msec",
            str(CHUNK_MS),
        ]
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def read(self) -> np.ndarray:
        if not self.process or not self.process.stdout:
            raise RuntimeError(f"Pulse source is not running: {self.source.name}")
        expected_bytes = CHUNK_SIZE * 2
        raw = self.process.stdout.read(expected_bytes)
        if len(raw) != expected_bytes:
            raise RuntimeError(f"Pulse source stopped: {self.source.name}")
        return np.frombuffer(raw, dtype=np.int16)

    def close(self):
        if not self.process:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=1)


class PulseCaptureReader:
    sample_width = 2

    def __init__(self, sources: list[PulseSource], mode: str):
        self.inputs = [PulseRawInput(source) for source in sources]
        self.mode = mode

    @property
    def description(self) -> str:
        names = " + ".join(input_source.source.name for input_source in self.inputs)
        return f"Live capture source: {self.mode} ({names})"

    def start(self):
        try:
            for input_source in self.inputs:
                input_source.start()
        except Exception:
            self.close()
            raise

    def read(self) -> np.ndarray:
        return self.read_tracks()["mixed"]

    def read_tracks(self) -> dict[str, np.ndarray]:
        frames = [input_source.read() for input_source in self.inputs]
        sources = [input_source.source for input_source in self.inputs]
        return track_audio_frames(self.mode, sources, frames)

    def close(self):
        for input_source in self.inputs:
            input_source.close()


class PyAudioCaptureReader:
    def __init__(self, pa, stream, channels):
        self.pa = pa
        self.stream = stream
        self.channels = channels
        self.sample_width = pa.get_sample_size(pyaudio.paInt16)

    @property
    def description(self) -> str:
        return "Live capture source: PyAudio default input"

    def start(self):
        return None

    def read(self) -> np.ndarray:
        return self.read_tracks()["mixed"]

    def read_tracks(self) -> dict[str, np.ndarray]:
        raw_data = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
        np_data = np.frombuffer(raw_data, dtype=np.int16)
        if self.channels > 1:
            np_data = np_data.reshape(-1, self.channels).mean(axis=1).astype(np.int16)
        return {"mixed": np_data}

    def close(self):
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        if self.pa is not None:
            self.pa.terminate()
            self.pa = None


def open_audio_reader(mode):
    """Select the requested source explicitly; use native input for microphones."""
    if shutil.which("pactl") and shutil.which("parec"):
        source, sink = pulse_default_source_and_sink()
        selected = select_pulse_sources_for_mode(mode, list_pulse_sources(), source, sink)
        required = 2 if mode == LIVE_CAPTURE_SYSTEM_MICROPHONE else 1
        if len(selected) != required:
            raise RuntimeError(f"Requested {mode} capture sources are unavailable")
        reader = PulseCaptureReader(selected, mode)
        reader.start()
        return reader
    if mode != LIVE_CAPTURE_MICROPHONE:
        raise RuntimeError("System audio capture requires PulseAudio/PipeWire on this host")
    with no_alsa_err(), suppress_native_stderr():
        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                             input=True, frames_per_buffer=CHUNK_SIZE)
        except BaseException:
            pa.terminate()
            raise
    return PyAudioCaptureReader(pa, stream, 1)
