import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyaudio
import webrtcvad
from aura.audio.vad import SileroStreamVAD, SpeechIntervals
from PyQt6.QtCore import QThread, pyqtSignal

from aura.audio.denoise import OFF_DENOISE_PRESET, normalize_denoise_preset
from aura.audio.meeting_distance import (
    DEFAULT_MEETING_DISTANCE_MODE,
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

from aura.audio.inputs import *  # Historical capture imports remain compatible.

logger = logging.getLogger(__name__)

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
        self.transcriber.live_denoise_preset = self.denoise_preset
        self.transcriber.live_audio_policy = self.meeting_distance_policy
        self.running = True
        self.vad = None
        self.vad_backend = "silero-v6"
        self.last_voiced_frame = -1
        self.recorded_frame_count = 0
        self.recording_session = None
        self.min_speech_len_sec = 0.8
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

    def _submit_chunk(self, chunk):
        if chunk is None:
            return
        self.transcriber.add_audio(chunk)

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
        if self.vad is None:
            try:
                self.vad = SileroStreamVAD()
            except Exception as exc:
                self.vad = webrtcvad.Vad(VAD_LEVEL)
                self.vad_backend = "webrtc"
                self.status_signal.emit(f"Neural VAD unavailable; using WebRTC fallback: {exc}")
        self.status_signal.emit(f"Live VAD: {self.vad_backend}")
        intervals = SpeechIntervals(CHUNK_SIZE, self.max_segment_len_sec,
                                    silence_ms=round(self.min_speech_len_sec * 1000))
        no_voice_frames = 0
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

                try:
                    vad_is_speech = self.vad.is_speech(vad_data, SAMPLE_RATE)
                except Exception as exc:
                    if self.vad_backend == "webrtc":
                        raise
                    self.vad = webrtcvad.Vad(VAD_LEVEL)
                    self.vad_backend = "webrtc"
                    self.status_signal.emit(f"Neural VAD failed; using WebRTC fallback: {exc}")
                    vad_is_speech = self.vad.is_speech(vad_data, SAMPLE_RATE)
                frame_rms_value = float(np.sqrt(np.mean(np_data.astype(np.float32) ** 2)))
                if vad_is_speech:
                    consecutive_vad_miss_frames = 0
                else:
                    consecutive_vad_miss_frames += 1
                is_speech = should_treat_frame_as_speech(
                    vad_is_speech=vad_is_speech,
                    frame_rms_value=frame_rms_value,
                    has_active_segment=intervals.active,
                    consecutive_vad_miss_frames=consecutive_vad_miss_frames,
                    energy_gate_rms=self.energy_gate_rms,
                    max_energy_bridge_frames=max_energy_bridge_frames,
                )

                if is_speech:
                    self.last_voiced_frame = self.recorded_frame_count
                self.recorded_frame_count += 1
                no_voice_frames = 0 if is_speech else no_voice_frames + 1
                self._submit_chunk(intervals.push(np_data, is_speech))
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

        self._submit_chunk(intervals.finish())
        try:
            reader.close()
        except Exception as e:
            logger.warning("Audio reader cleanup failed: %s", e)

        trim_trailing_frames = 0
        if self.auto_stopped_for_no_voice:
            self.trimmed_trailing_no_voice_frames = self.recorded_frame_count - self.last_voiced_frame - 1
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
