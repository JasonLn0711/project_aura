import datetime
import logging
import os
import queue
import time

from faster_whisper import WhisperModel
from PyQt6.QtCore import QThread, pyqtSignal

from aura.audio.denoise import OFF_DENOISE_PRESET, normalize_denoise_preset
from aura.asr.file_pipeline import (
    CancellationToken,
    FileTranscriptionCancelled,
    FileTranscriptionSettings,
    build_transcribe_kwargs,
    format_timestamp,
    normalize_file_transcription_error,
    resolve_initial_prompt,
    transcribe_file,
)
from aura.config import SAMPLE_RATE
from aura.asr.punctuation import restore_chinese_punctuation
from aura.settings import DEFAULT_SETTINGS
from aura.diarization.pyannote_pipeline import DiarizationSettings
from aura.system.cuda import is_cuda_runtime_error, preload_cuda_runtime_libraries
from aura.system.platform import detect_runtime_platform, platform_cuda_guidance
from aura.system.runtime_paths import append_transcript_backup

logger = logging.getLogger(__name__)

REQUIRED_ASR_DEVICE = "cuda"


def live_asr_telemetry_message(
    chunk_duration_seconds: float,
    queue_size: int,
    elapsed_seconds: float,
) -> str:
    realtime_factor = elapsed_seconds / chunk_duration_seconds if chunk_duration_seconds > 0 else 0.0
    backlog = queue_size > 0
    return (
        "Live ASR telemetry: "
        f"chunk_duration={chunk_duration_seconds:.3f}s "
        f"queue_size={queue_size} "
        f"asr_elapsed={elapsed_seconds:.3f}s "
        f"realtime_factor={realtime_factor:.2f} "
        f"queue_backlog={'yes' if backlog else 'no'}"
    )


def live_asr_telemetry_event(
    chunk_duration_seconds: float,
    queue_size: int,
    elapsed_seconds: float,
) -> dict:
    realtime_factor = elapsed_seconds / chunk_duration_seconds if chunk_duration_seconds > 0 else 0.0
    return {
        "category": "live_asr_telemetry",
        "message": live_asr_telemetry_message(chunk_duration_seconds, queue_size, elapsed_seconds),
        "chunk_duration_seconds": round(chunk_duration_seconds, 3),
        "queue_size": int(queue_size),
        "asr_elapsed_seconds": round(elapsed_seconds, 3),
        "realtime_factor": round(realtime_factor, 3),
        "queue_backlog": queue_size > 0,
    }


def cuda_required_error(detail: str) -> str:
    runtime = detect_runtime_platform()
    return (
        "This machine has not completed Project AURA RTX/CUDA activation. "
        "ASR is configured to require the NVIDIA RTX/CUDA GPU, and CPU fallback is disabled.\n\n"
        f"Environment: {runtime.label}\n"
        f"CUDA detail: {detail}\n\n"
        f"Next check: {platform_cuda_guidance(runtime)}\n"
        "After fixing the runtime, reload the model."
    )


class FileTranscriberThread(QThread):
    text_updated = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(
        self,
        model,
        file_path,
        target_dbfs=DEFAULT_SETTINGS.target_dbfs,
        beam_size=DEFAULT_SETTINGS.beam_size,
        initial_prompt=None,
        language=DEFAULT_SETTINGS.language,
        meeting_distance_mode=DEFAULT_SETTINGS.meeting_distance_mode,
        enable_denoise=DEFAULT_SETTINGS.denoise_enabled,
        denoise_preset=DEFAULT_SETTINGS.denoise_preset,
        enable_speaker_diarization=DEFAULT_SETTINGS.speaker_diarization_enabled,
        min_speakers=DEFAULT_SETTINGS.speaker_min_speakers,
        max_speakers=DEFAULT_SETTINGS.speaker_max_speakers,
    ):
        super().__init__()
        resolved_denoise_preset = normalize_denoise_preset(enable_denoise, denoise_preset)
        self.model = model
        self.file_path = file_path
        self.settings = FileTranscriptionSettings(
            target_dbfs=target_dbfs,
            beam_size=beam_size,
            initial_prompt=resolve_initial_prompt(initial_prompt),
            language=language,
            meeting_distance_mode=meeting_distance_mode,
            enable_denoise=resolved_denoise_preset != OFF_DENOISE_PRESET,
            denoise_preset=resolved_denoise_preset,
            diarization=DiarizationSettings(
                enabled=enable_speaker_diarization,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
                model_id=DEFAULT_SETTINGS.speaker_diarization_model,
                device=DEFAULT_SETTINGS.speaker_diarization_device,
                use_exclusive=DEFAULT_SETTINGS.speaker_diarization_use_exclusive,
            ),
        )
        self.cancellation = CancellationToken()
        self.result_lines = []
        self.result_segments = []
        self.status_events = []

    @property
    def initial_prompt(self):
        return self.settings.initial_prompt

    @property
    def enable_denoise(self):
        return self.settings.denoise_preset != OFF_DENOISE_PRESET

    @property
    def cancel_requested(self):
        return self.cancellation.cancelled

    def request_cancel(self):
        self.cancellation.request_cancel()

    def _raise_if_cancelled(self):
        self.cancellation.raise_if_cancelled()

    def emit_status(self, message: str):
        self.status_events.append(
            {
                "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "message": message,
            }
        )
        self.status_updated.emit(message)

    def run(self):
        self.emit_status("⏳ Analyzing audio file, please wait...")
        file_name = os.path.basename(self.file_path)
        try:
            result = transcribe_file(
                model=self.model,
                file_path=self.file_path,
                settings=self.settings,
                worker_id=id(self),
                cancellation=self.cancellation,
                status_callback=self.emit_status,
                line_callback=self.text_updated.emit,
            )
            self.result_lines = result.lines
            self.result_segments = result.segments
        except FileTranscriptionCancelled:
            self.emit_status(f"⚠️ Cancelled transcribing {file_name}")
        except Exception as e:
            if self.cancel_requested:
                self.emit_status(f"⚠️ Cancelled transcribing {file_name}")
            else:
                self.emit_status(f"❌ Failed to transcribe {file_name}")
                self.error_signal.emit(f"{file_name}\n\n{normalize_file_transcription_error(e)}")
        finally:
            self.finished_signal.emit()


class ModelLoaderThread(QThread):
    """Load the Whisper model asynchronously to avoid UI freezes."""

    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, device, compute_type):
        super().__init__()
        self.requested_device = device
        self.device = REQUIRED_ASR_DEVICE
        self.compute_type = compute_type
        self.actual_device = REQUIRED_ASR_DEVICE
        self.actual_compute_type = compute_type
        self.runtime_note = ""

    def run(self):
        try:
            if self.requested_device != REQUIRED_ASR_DEVICE:
                self.status_signal.emit(
                    f"⚠️ ASR is pinned to {REQUIRED_ASR_DEVICE}; ignoring requested device "
                    f"`{self.requested_device}`."
                )

            runtime_ready, runtime_source = preload_cuda_runtime_libraries()
            if runtime_ready:
                self.runtime_note = f"CUDA runtime source: {runtime_source}"
            else:
                self.runtime_note = cuda_required_error(runtime_source)
                self.error_signal.emit(self.runtime_note)
                return

            self.status_signal.emit(
                f"🚀 Loading ASR model on required RTX/CUDA GPU "
                f"({self.actual_device}/{self.actual_compute_type})..."
            )
            model = WhisperModel(
                DEFAULT_SETTINGS.model_id,
                device=REQUIRED_ASR_DEVICE,
                compute_type=self.actual_compute_type,
            )
            self.finished_signal.emit(model)
        except Exception as e:
            error_msg = str(e)
            if is_cuda_runtime_error(error_msg):
                error_msg = cuda_required_error(error_msg)
            if "out of memory" in error_msg.lower():
                error_msg = "Insufficient GPU memory. Try switching to int8 precision or closing other programs."
            self.error_signal.emit(error_msg)


class TranscriberThread(QThread):
    text_updated = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    telemetry_updated = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.audio_queue = queue.Queue()
        self.running = True
        self.processing = False
        self.model = None
        self.device = DEFAULT_SETTINGS.device
        self.compute_type = DEFAULT_SETTINGS.compute_type
        self.live_beam_size = DEFAULT_SETTINGS.beam_size
        self.live_language = DEFAULT_SETTINGS.language
        self.live_initial_prompt = DEFAULT_SETTINGS.live_initial_prompt
        self.live_chinese_punctuation_enabled = DEFAULT_SETTINGS.chinese_punctuation_enabled
        self.punctuation_status_emitted = False
        self._stream_elapsed_seconds = 0.0

    def update_live_settings(
        self,
        beam_size=DEFAULT_SETTINGS.beam_size,
        language=DEFAULT_SETTINGS.language,
        initial_prompt=None,
    ):
        self.live_beam_size = int(beam_size) if beam_size else DEFAULT_SETTINGS.beam_size
        self.live_language = language
        self.live_initial_prompt = resolve_initial_prompt(initial_prompt, DEFAULT_SETTINGS.live_initial_prompt)

    def run(self):
        while self.running:
            try:
                if self.model is None:
                    time.sleep(0.5)
                    continue

                audio_data = self.audio_queue.get(timeout=1)
                transcribe_kwargs = build_transcribe_kwargs(
                    beam_size=self.live_beam_size,
                    language=self.live_language,
                    initial_prompt=self.live_initial_prompt,
                    condition_on_previous_text=False,
                )

                self.processing = True
                queue_size = self.audio_queue.qsize()
                chunk_duration_seconds = len(audio_data) / SAMPLE_RATE
                chunk_start_seconds = self._stream_elapsed_seconds
                self._stream_elapsed_seconds += chunk_duration_seconds
                asr_started_at = time.perf_counter()
                segments, info = self.model.transcribe(audio_data, **transcribe_kwargs)
                detected_language = getattr(info, "language", None) or self.live_language
                text_segment = "".join([s.text for s in segments])
                asr_elapsed_seconds = time.perf_counter() - asr_started_at
                telemetry = live_asr_telemetry_event(chunk_duration_seconds, queue_size, asr_elapsed_seconds)
                logger.info(telemetry["message"])
                self.telemetry_updated.emit(telemetry)
                if self.live_chinese_punctuation_enabled:
                    punctuation_result = restore_chinese_punctuation(text_segment, language=detected_language)
                    text_segment = punctuation_result.text
                    if punctuation_result.backend != "skipped" and not self.punctuation_status_emitted:
                        if punctuation_result.backend == "model":
                            self.status_updated.emit("🔤 Traditional Chinese punctuation restored with the local model.")
                        elif punctuation_result.detail:
                            self.status_updated.emit(
                                f"⚠️ Punctuation model unavailable; using rule fallback. Detail: {punctuation_result.detail}"
                            )
                        else:
                            self.status_updated.emit("🔤 Traditional Chinese punctuation normalized with rule fallback.")
                        self.punctuation_status_emitted = True
                if text_segment.strip():
                    timestamp = format_timestamp(chunk_start_seconds)
                    formatted_text = f"[{timestamp}] {text_segment}"
                    self.text_updated.emit(formatted_text)
                    append_transcript_backup(formatted_text)
            except queue.Empty:
                continue
            except Exception as e:
                err = f"Live transcription error: {e}"
                logger.exception(err)
                self.status_updated.emit(f"⚠️ {err}")
            finally:
                self.processing = False

    def add_audio(self, audio_np):
        self.audio_queue.put(audio_np)

    def reset_stream_elapsed(self):
        self._stream_elapsed_seconds = 0.0

    def is_idle(self):
        return self.audio_queue.empty() and not self.processing

    def stop(self):
        self.running = False
