import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyaudio
import webrtcvad
from PyQt6.QtCore import QThread, pyqtSignal

from aura.audio.denoise import OFF_DENOISE_PRESET, normalize_denoise_preset, reduce_noise_safely
from aura.audio.meeting_distance import (
    DEFAULT_MEETING_DISTANCE_MODE,
    apply_live_segment_agc,
    effective_denoise_preset_for_mode,
    meeting_distance_policy_for,
)
from aura.audio.recording_session import RecordingSession
from aura.config import (
    CHUNK_MS,
    CHUNK_SIZE,
    DEFAULT_LIVE_CAPTURE_SOURCE,
    LIVE_CAPTURE_MICROPHONE,
    LIVE_CAPTURE_SYSTEM,
    LIVE_CAPTURE_SYSTEM_MICROPHONE,
    SAMPLE_RATE,
    VAD_LEVEL,
)
from aura.settings import DEFAULT_SETTINGS
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


def should_treat_frame_as_speech(
    vad_is_speech: bool,
    frame_rms_value: float,
    has_active_segment: bool,
    consecutive_vad_miss_frames: int,
    energy_gate_rms: float,
    max_energy_bridge_frames: int,
) -> bool:
    if vad_is_speech:
        return True
    if not has_active_segment or max_energy_bridge_frames <= 0:
        return False
    return consecutive_vad_miss_frames <= max_energy_bridge_frames and frame_rms_value >= energy_gate_rms


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
        self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()


class AudioRecorderThread(QThread):
    waveform_signal = pyqtSignal(np.ndarray)
    finished_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(
        self,
        filename,
        transcriber_thread,
        enable_denoise=False,
        denoise_preset=None,
        meeting_distance_mode=DEFAULT_MEETING_DISTANCE_MODE,
        capture_mode=DEFAULT_LIVE_CAPTURE_SOURCE,
        max_segment_len_sec=DEFAULT_SETTINGS.live_max_segment_len_sec,
        energy_gate_rms=DEFAULT_SETTINGS.live_energy_gate_rms,
    ):
        super().__init__()
        self.filename = filename
        self.transcriber = transcriber_thread
        self.capture_mode = capture_mode
        self.meeting_distance_policy = meeting_distance_policy_for(meeting_distance_mode)
        selected_denoise = normalize_denoise_preset(enable_denoise, denoise_preset)
        self.denoise_preset = effective_denoise_preset_for_mode(
            self.meeting_distance_policy.mode,
            selected_denoise,
        )
        self.enable_denoise = self.denoise_preset != OFF_DENOISE_PRESET
        self.running = True
        self.vad = webrtcvad.Vad(VAD_LEVEL)
        self.full_frame_voice_flags = []
        self.recorded_frame_count = 0
        self.recording_session = None
        self.min_speech_len_sec = 0.5
        self.max_segment_len_sec = float(max_segment_len_sec)
        self.energy_gate_rms = (
            float(self.meeting_distance_policy.live_energy_gate_rms)
            if self.meeting_distance_policy.mode != DEFAULT_MEETING_DISTANCE_MODE
            else float(energy_gate_rms)
        )
        self.energy_bridge_ms = int(self.meeting_distance_policy.live_energy_bridge_ms)
        self.no_voice_auto_stop_minutes = NO_VOICE_AUTO_STOP_MINUTES
        self.auto_stopped_for_no_voice = False
        self.trimmed_trailing_no_voice_frames = 0

    def _flush_speech_buffer(self, speech_buffer):
        if not speech_buffer:
            return []

        audio_np = np.concatenate(speech_buffer).flatten().astype(np.float32) / 32768.0

        if self.enable_denoise:
            try:
                audio_np = reduce_noise_safely(audio_np, SAMPLE_RATE, preset=self.denoise_preset)
            except Exception as e:
                logger.warning("Denoising failed; continuing without denoise: %s", e)

        audio_np = apply_live_segment_agc(audio_np, self.meeting_distance_policy)
        padding_length = int(SAMPLE_RATE * 0.5)
        silence_padding = np.zeros(padding_length, dtype=np.float32)
        padded_audio_np = np.concatenate([audio_np, silence_padding])
        self.transcriber.add_audio(padded_audio_np)
        return []

    def _open_pulse_reader(self):
        if not shutil.which("pactl") or not shutil.which("parec"):
            return None
        sources = list_pulse_sources()
        default_source, default_sink = pulse_default_source_and_sink()
        selected = select_pulse_sources_for_mode(
            self.capture_mode,
            sources,
            default_source=default_source,
            default_sink=default_sink,
        )
        if not selected:
            return None
        if self.capture_mode == LIVE_CAPTURE_SYSTEM_MICROPHONE and len(selected) < 2:
            self.status_signal.emit("System+mic capture requested, but only one Pulse source was found; using that source.")
        reader = PulseCaptureReader(selected, self.capture_mode)
        reader.start()
        return reader

    def _open_pyaudio_reader(self):
        with no_alsa_err(), suppress_native_stderr():
            pa = pyaudio.PyAudio()
            target_device_index = None
            target_channels = 1

            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if "pulse" in info["name"].lower():
                    target_device_index = i
                    target_channels = int(info["maxInputChannels"]) if info["maxInputChannels"] > 0 else 1
                    break

            if target_device_index is not None:
                logger.info("Mounting PulseAudio virtual device index=%s channels=%s", target_device_index, target_channels)
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=target_channels,
                    rate=SAMPLE_RATE,
                    input=True,
                    input_device_index=target_device_index,
                    frames_per_buffer=CHUNK_SIZE,
                )
            else:
                logger.warning("Pulse device not found; trying system default input device")
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=CHUNK_SIZE,
                )
                target_channels = 1

        return PyAudioCaptureReader(pa, stream, target_channels)

    def _open_reader(self):
        try:
            reader = self._open_pulse_reader()
        except Exception as exc:
            logger.warning("Pulse source capture failed; falling back to PyAudio: %s", exc)
            self.status_signal.emit(f"Pulse source capture failed; using PyAudio default input. Detail: {exc}")
            reader = None
        if reader:
            return reader
        self.status_signal.emit("Pulse source selection unavailable; using PyAudio default input.")
        return self._open_pyaudio_reader()

    def run(self):
        try:
            reader = self._open_reader()
        except Exception as e:
            self.finished_signal.emit(f"Hardware mounting failed: {str(e)}")
            return

        try:
            filename = Path(self.filename)
            self.recording_session = RecordingSession.start(
                filename.parent / f"{filename.name}_session",
                recording_name=filename.name,
                capture_mode=self.capture_mode,
                sample_rate=SAMPLE_RATE,
                sample_width=reader.sample_width,
            )
        except Exception as e:
            reader.close()
            self.finished_signal.emit(f"Recording session failed: {str(e)}")
            return

        self.status_signal.emit(
            f"原始音訊正持續保存於 {self.recording_session.session_dir}"
        )
        if hasattr(self.transcriber, "reset_stream_elapsed"):
            self.transcriber.reset_stream_elapsed()
        self.status_signal.emit(reader.description)
        if self.meeting_distance_policy.mode != DEFAULT_MEETING_DISTANCE_MODE:
            self.status_signal.emit(
                "Meeting distance mode "
                f"{self.meeting_distance_policy.mode}: "
                f"{self.meeting_distance_policy.enhancement_backend} "
                f"({self.meeting_distance_policy.backend_role})."
            )
        silence_frames = 0
        no_voice_frames = 0
        speech_buffer = []
        min_silence_frames = int((1000 / CHUNK_MS) * self.min_speech_len_sec)
        max_speech_frames = int((1000 / CHUNK_MS) * self.max_segment_len_sec)
        max_energy_bridge_frames = frames_for_duration_seconds(self.energy_bridge_ms / 1000)
        no_voice_auto_stop_frames = frames_for_duration_seconds(self.no_voice_auto_stop_minutes * 60)
        consecutive_vad_miss_frames = 0
        capture_error = None

        while self.running:
            try:
                tracks = reader.read_tracks() if hasattr(reader, "read_tracks") else {"mixed": reader.read()}
                np_data = tracks["mixed"]
                vad_data = np_data.tobytes()
                self.recording_session.append_pcm(
                    {track: frame.tobytes() for track, frame in tracks.items()}
                )

                self.waveform_signal.emit(np_data)

                vad_is_speech = self.vad.is_speech(vad_data, SAMPLE_RATE)
                frame_rms_value = float(np.sqrt(np.mean(np_data.astype(np.float32) ** 2)))
                if vad_is_speech:
                    consecutive_vad_miss_frames = 0
                else:
                    consecutive_vad_miss_frames += 1
                is_speech = should_treat_frame_as_speech(
                    vad_is_speech=vad_is_speech,
                    frame_rms_value=frame_rms_value,
                    has_active_segment=bool(speech_buffer),
                    consecutive_vad_miss_frames=consecutive_vad_miss_frames,
                    energy_gate_rms=self.energy_gate_rms,
                    max_energy_bridge_frames=max_energy_bridge_frames,
                )

                self.full_frame_voice_flags.append(is_speech)
                self.recorded_frame_count += 1
                if is_speech:
                    speech_buffer.append(np_data)
                    silence_frames = 0
                    no_voice_frames = 0
                else:
                    silence_frames += 1
                    no_voice_frames += 1

                reached_silence_boundary = len(speech_buffer) > 0 and silence_frames > min_silence_frames
                reached_max_segment = len(speech_buffer) >= max_speech_frames
                if reached_silence_boundary or reached_max_segment:
                    speech_buffer = self._flush_speech_buffer(speech_buffer)
                    silence_frames = 0
                if should_auto_stop_for_no_voice(no_voice_frames, no_voice_auto_stop_frames):
                    self.auto_stopped_for_no_voice = True
                    self.status_signal.emit(
                        f"No human voice detected for {self.no_voice_auto_stop_minutes} minutes; "
                        "auto-stopping and trimming the trailing no-voice audio."
                    )
                    self.running = False
            except Exception as e:
                logger.exception("Audio loop stopped after error: %s", e)
                capture_error = e
                break

        speech_buffer = self._flush_speech_buffer(speech_buffer)
        try:
            reader.close()
        except Exception as e:
            logger.warning("Audio reader cleanup failed: %s", e)

        trim_trailing_frames = 0
        if self.auto_stopped_for_no_voice:
            last_voiced_frame = next(
                (
                    index
                    for index in range(len(self.full_frame_voice_flags) - 1, -1, -1)
                    if self.full_frame_voice_flags[index]
                ),
                -1,
            )
            self.trimmed_trailing_no_voice_frames = len(self.full_frame_voice_flags) - last_voiced_frame - 1
            trim_trailing_frames = self.trimmed_trailing_no_voice_frames
            if self.trimmed_trailing_no_voice_frames:
                trimmed_seconds = self.trimmed_trailing_no_voice_frames * CHUNK_MS / 1000
                self.status_signal.emit(f"Trimmed {trimmed_seconds:.1f}s of trailing no-voice audio.")

        if self.recording_session.manifest["status"] == "failed":
            self.finished_signal.emit(f"Recording failed: {capture_error}")
            return

        try:
            audio_tracks = self.recording_session.finalize(
                trim_trailing_frames=trim_trailing_frames,
                frame_samples=CHUNK_SIZE,
                capture_error=capture_error,
            )
        except Exception as e:
            logger.exception("Recording finalization failed: %s", e)
            self.finished_signal.emit(f"Recording finalization failed: {str(e)}")
            return

        if capture_error is not None and "mixed" in audio_tracks:
            message = (
                f"Partial recording preserved after {type(capture_error).__name__}: "
                f"{audio_tracks['mixed']}"
            )
            logger.warning(message)
            self.status_signal.emit(f"⚠️ {message}")
            self.finished_signal.emit(str(audio_tracks["mixed"]))
            return

        if self.recorded_frame_count <= trim_trailing_frames or "mixed" not in audio_tracks:
            self.finished_signal.emit("No audio recorded")
            return

        self.finished_signal.emit(str(audio_tracks["mixed"]))
