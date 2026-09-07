"""Optional FastEnhancer-B DNS 16 kHz wav2wav ONNX evaluation adapter."""
from functools import lru_cache
import os
from pathlib import Path

import numpy as np


@lru_cache(maxsize=1)
def load_session(path: str):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    return ort.InferenceSession(path, sess_options=options, providers=["CPUExecutionProvider"])


def enhance(audio: np.ndarray, sample_rate: int = 16000, *, session=None) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if sample_rate != 16000 or audio.ndim != 1 or not np.isfinite(audio).all():
        raise ValueError("FastEnhancer-B requires finite mono 16 kHz float PCM")
    if not len(audio):
        return audio.copy()
    if session is None:
        path = os.environ.get("AURA_FASTENHANCER_MODEL", "")
        if not path or not Path(path).is_file():
            raise RuntimeError("Set AURA_FASTENHANCER_MODEL to the official DNS 16 kHz FastEnhancer-B wav2wav ONNX file")
        session = load_session(path)
    inputs = {item.name: item for item in session.get_inputs()}
    if "wav_in" not in inputs or inputs["wav_in"].shape != [1, 256]:
        raise ValueError("Expected FastEnhancer-B wav2wav input [1, 256]")
    cache_names = sorted((name for name in inputs if name.startswith("cache_in_")), key=lambda name: int(name.rsplit("_", 1)[1]))
    states = {name: np.zeros(inputs[name].shape, dtype=np.float32) for name in cache_names}
    # State is local to this utterance; compensate the official 256-sample delay.
    padded = np.pad(audio, (0, 512))
    output = []
    for start in range(0, len(audio) + 256, 256):
        values = session.run(None, {"wav_in": padded[None, start:start + 256], **states})
        if len(values) != len(cache_names) + 1:
            raise ValueError("Unexpected FastEnhancer cache outputs")
        output.append(np.asarray(values[0]).reshape(-1))
        states = dict(zip(cache_names, values[1:]))
    result = np.concatenate(output)[256:256 + len(audio)]
    if len(result) != len(audio) or not np.isfinite(result).all():
        raise ValueError("FastEnhancer returned invalid audio")
    return np.clip(result, -1, 1).astype(np.float32)
