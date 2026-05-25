import logging
import os
import shutil
import subprocess
import wave
from dataclasses import dataclass

import numpy as np
import pyaudio
import webrtcvad
from PyQt6.QtCore import QThread, pyqtSignal

from aura.audio.denoise import OFF_DENOISE_PRESET, normalize_denoise_preset, reduce_noise_safely
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
from aura.system.native_audio import no_alsa_err, suppress_native_stderr

logger = logging.getLogger(__name__)

MIX_ACTIVE_RMS_FLOOR = 80.0
MIX_MIN_GAIN = 0.5
MIX_MAX_GAIN = 3.0
MIX_HEADROOM = 0.8
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


def frames_for_duration_seconds(duration_seconds: float) -> int:
    if duration_seconds <= 0:
        return 0
    return int(np.ceil(duration_seconds * 1000 / CHUNK_MS))


def should_auto_stop_for_no_voice(no_voice_frames: int, limit_frames: int) -> bool:
    return limit_frames > 0 and no_voice_frames >= limit_frames


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
        return mix_audio_frames([input_source.read() for input_source in self.inputs])

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
        raw_data = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
        np_data = np.frombuffer(raw_data, dtype=np.int16)
        if self.channels > 1:
            np_data = np_data.reshape(-1, self.channels).mean(axis=1).astype(np.int16)
        return np_data

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
        capture_mode=DEFAULT_LIVE_CAPTURE_SOURCE,
    ):
        super().__init__()
        self.filename = filename
        self.transcriber = transcriber_thread
        self.capture_mode = capture_mode
        self.denoise_preset = normalize_denoise_preset(enable_denoise, denoise_preset)
        self.enable_denoise = self.denoise_preset != OFF_DENOISE_PRESET
        self.running = True
        self.vad = webrtcvad.Vad(VAD_LEVEL)
        self.full_frames = []
        self.full_frame_voice_flags = []
        self.min_speech_len_sec = 0.5
        self.max_segment_len_sec = 8.0
        self.energy_gate_rms = 550.0
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

        self.status_signal.emit(reader.description)
        silence_frames = 0
        no_voice_frames = 0
        speech_buffer = []
        min_silence_frames = int((1000 / CHUNK_MS) * self.min_speech_len_sec)
        max_speech_frames = int((1000 / CHUNK_MS) * self.max_segment_len_sec)
        no_voice_auto_stop_frames = frames_for_duration_seconds(self.no_voice_auto_stop_minutes * 60)

        while self.running:
            try:
                np_data = reader.read()
                vad_data = np_data.tobytes()

                self.waveform_signal.emit(np_data)

                is_speech = self.vad.is_speech(vad_data, SAMPLE_RATE)
                if not is_speech:
                    frame_rms = float(np.sqrt(np.mean(np_data.astype(np.float32) ** 2)))
                    if frame_rms >= self.energy_gate_rms:
                        is_speech = True

                self.full_frames.append(vad_data)
                self.full_frame_voice_flags.append(is_speech)
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
                break

        speech_buffer = self._flush_speech_buffer(speech_buffer)
        reader.close()

        frames_to_write = self.full_frames
        if self.auto_stopped_for_no_voice:
            frames_to_write, self.trimmed_trailing_no_voice_frames = trim_trailing_unvoiced_frames(
                self.full_frames,
                self.full_frame_voice_flags,
            )
            if self.trimmed_trailing_no_voice_frames:
                trimmed_seconds = self.trimmed_trailing_no_voice_frames * CHUNK_MS / 1000
                self.status_signal.emit(f"Trimmed {trimmed_seconds:.1f}s of trailing no-voice audio.")

        if not frames_to_write:
            self.finished_signal.emit("No audio recorded")
            return

        wav_path = self.filename + ".wav"
        os.makedirs(os.path.dirname(wav_path), exist_ok=True)
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(reader.sample_width)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames_to_write))
        self.finished_signal.emit(wav_path)
