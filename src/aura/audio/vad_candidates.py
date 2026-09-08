"""Explicit candidate adapters; product defaults remain independently controlled."""
from pathlib import Path
import numpy as np


class Silero621:
    def __init__(self, path):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])
        if {i.name for i in self.session.get_inputs()} != {"input", "state", "sr"}:
            raise ValueError("Expected the upstream Silero 6.2.1 input/state/sr interface")
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros(64, dtype=np.float32)
        self.pending = np.empty(0, dtype=np.float32)
        self.active = False

    def is_speech(self, pcm, sample_rate):
        if sample_rate != 16000 or len(pcm) % 2:
            raise ValueError("Silero requires aligned 16 kHz PCM16")
        self.pending = np.concatenate((self.pending, np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768))
        while len(self.pending) >= 512:
            frame, self.pending = self.pending[:512], self.pending[512:]
            prob, self.state = self.session.run(None, {"input": np.concatenate((self.context, frame))[None],
                "state": self.state, "sr": np.array(16000, dtype=np.int64)})
            self.context = frame[-64:].copy()
            self.active = float(np.asarray(prob).reshape(-1)[0]) >= (0.35 if self.active else 0.5)
        return self.active


class FireRedStream:
    def __init__(self, directory):
        from fireredvad import FireRedStreamVad, FireRedStreamVadConfig
        self.vad = FireRedStreamVad.from_pretrained(str(directory), FireRedStreamVadConfig(use_gpu=False))
        self.active = False

    def is_speech(self, pcm, sample_rate):
        if sample_rate != 16000 or len(pcm) % 2:
            raise ValueError("FireRed requires aligned 16 kHz PCM16")
        import torch
        with torch.inference_mode():
            frames = self.vad.detect_chunk(np.frombuffer(pcm, dtype="<i2").astype(np.float32))
        for frame in frames:
            if frame.is_speech_start:
                self.active = True
            if frame.is_speech_end:
                self.active = False
        return self.active
