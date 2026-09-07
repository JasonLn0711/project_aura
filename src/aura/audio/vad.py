"""Stateful speech detection and continuous, source-timed ASR intervals."""

from collections import deque
from dataclasses import dataclass
import math
import time

import numpy as np

from aura.config import SAMPLE_RATE


@dataclass(frozen=True)
class AudioChunk:
    samples: np.ndarray
    start_sample: int
    end_sample: int
    terminal: bool = True
    queued_at: float = 0.0

    def __post_init__(self):
        if self.samples.ndim != 1 or self.start_sample < 0 or self.end_sample - self.start_sample != len(self.samples):
            raise ValueError("Audio chunk must contain a continuous, ordered source interval")


class SileroStreamVAD:
    """Use faster-whisper's bundled v6 ONNX weights with per-stream state."""

    def __init__(self, threshold: float = 0.5, release_threshold: float = 0.35):
        if not 0 <= release_threshold <= threshold <= 1:
            raise ValueError("VAD thresholds must satisfy 0 <= release <= onset <= 1")
        self.threshold = threshold
        self.release_threshold = release_threshold
        from faster_whisper.vad import get_vad_model

        self.session = get_vad_model().session
        names = {item.name for item in self.session.get_inputs()}
        if names != {"input", "h", "c"}:
            raise RuntimeError("Unsupported bundled Silero ONNX interface; expected input/h/c")
        self.h = np.zeros((1, 1, 128), dtype=np.float32)
        self.c = np.zeros_like(self.h)
        self.context = np.zeros(64, dtype=np.float32)
        self.pending = np.empty(0, dtype=np.float32)
        self.active = False
        self.probability = 0.0

    def is_speech(self, pcm: bytes, sample_rate: int) -> bool:
        if sample_rate != SAMPLE_RATE or len(pcm) % 2:
            raise ValueError("VAD requires 16 kHz, signed 16-bit mono PCM")
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        self.pending = np.concatenate((self.pending, samples))
        while len(self.pending) >= 512:
            frame, self.pending = self.pending[:512], self.pending[512:]
            prediction, self.h, self.c = self.session.run(None, {
                "input": np.concatenate((self.context, frame))[None, :],
                "h": self.h, "c": self.c,
            })
            self.context = frame[-64:].copy()
            self.probability = float(np.asarray(prediction).reshape(-1)[0])
            self.active = self.probability >= (self.release_threshold if self.active else self.threshold)
        return self.active


class SpeechIntervals:
    def __init__(self, frame_samples: int, max_seconds: float = 12.0,
                 pre_roll_ms: int = 320, silence_ms: int = 800):
        if frame_samples <= 0 or max_seconds <= 0 or pre_roll_ms < 0 or silence_ms <= 0:
            raise ValueError("Invalid speech interval settings")
        self.pre_roll = deque(maxlen=math.ceil(pre_roll_ms * SAMPLE_RATE / 1000 / frame_samples))
        self.max_samples = int(max_seconds * SAMPLE_RATE)
        self.silence_limit = math.ceil(silence_ms * SAMPLE_RATE / 1000)
        self.position = 0
        self.start = 0
        self.frames = []
        self.silence_samples = 0
        self.continuing = False

    @property
    def active(self):
        return bool(self.frames) or self.continuing

    def push(self, frame: np.ndarray, speech: bool) -> AudioChunk | None:
        if frame.ndim != 1 or not len(frame):
            raise ValueError("Expected nonempty mono PCM frame")
        frame = frame.copy()
        if not self.active:
            if not speech:
                self.pre_roll.append(frame)
                self.position += len(frame)
                return None
            self.frames = list(self.pre_roll)
            self.start = self.position - sum(map(len, self.frames))
            self.pre_roll.clear()
        self.frames.append(frame)
        self.position += len(frame)
        self.silence_samples = 0 if speech else self.silence_samples + len(frame)
        terminal = self.silence_samples >= self.silence_limit
        if terminal or self.position - self.start >= self.max_samples:
            return self._flush(terminal)
        return None

    def _flush(self, terminal: bool) -> AudioChunk | None:
        if not self.frames:
            return None
        samples = np.concatenate(self.frames).astype(np.float32) / 32768.0
        chunk = AudioChunk(samples, self.start, self.position, terminal, time.monotonic())
        self.frames = []
        self.start = self.position
        self.continuing = not terminal
        if terminal:
            self.silence_samples = 0
        return chunk

    def finish(self) -> AudioChunk | None:
        return self._flush(True)
