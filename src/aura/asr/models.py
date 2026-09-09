"""The two supported ASR runtimes; imports and CUDA ownership stay in the worker."""
import importlib.util
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from aura.config import MODEL_ID

PARAKEET = "parakeet-tdt-0.6b-v2"
PARAKEET_ID = "nvidia/" + PARAKEET
PARAKEET_REVISION = "ae9ad07059c7c739ffaf932226a8fe64ae2620b0"
MODEL_KEYS = ("breeze", PARAKEET)
PARAKEET_DEFAULTS = dict(language="en", prompt="", hotwords="", punctuation=False, beam_size=5)
INSTALL_GUIDANCE = "On the Linux Python 3.12 server: uv sync --locked --extra cli --extra server --extra parakeet --inexact"
DOWNLOAD_GUIDANCE = f"On the server: aura models download {PARAKEET}"


def checkpoint(download=False):
    from huggingface_hub import hf_hub_download
    return hf_hub_download(PARAKEET_ID, PARAKEET + ".nemo", revision=PARAKEET_REVISION,
                           local_files_only=not download)


def capabilities():
    supported = sys.platform == "linux" and sys.version_info >= (3, 12)
    dependency = importlib.util.find_spec("nemo") is not None
    cached = False
    try:
        cached = Path(checkpoint()).is_file()
    except (ImportError, OSError, ValueError):
        pass
    return {
        "breeze": dict(model=MODEL_ID, languages=["zh", "en", "auto"], backend="faster-whisper",
                       prompt=True, hotwords=True, beam_size=True, chinese_punctuation=True),
        PARAKEET: dict(model=PARAKEET_ID, revision=PARAKEET_REVISION, languages=["en"], backend="nemo",
                       prompt=False, hotwords=False, beam_size=False, chinese_punctuation=False,
                       platform_supported=supported, dependencies_installed=dependency,
                       checkpoint_cached=cached, runtime_probe="not_performed",
                       install=INSTALL_GUIDANCE, download=DOWNLOAD_GUIDANCE),
    }


def download_model(key):
    if key != PARAKEET:
        raise ValueError("This download command supports " + PARAKEET)
    try:
        return checkpoint(download=True)
    except ImportError as exc:
        raise RuntimeError(INSTALL_GUIDANCE) from exc


class ParakeetModel:
    """Adapt NeMo timestamps to AURA's existing segment contract."""

    def __init__(self):
        if sys.platform != "linux" or sys.version_info < (3, 12):
            raise RuntimeError("Parakeet requires a Linux Python 3.12+ CUDA server; connect remotely from Windows.")
        try:
            import torch
            import nemo.collections.asr as nemo_asr
        except ImportError as exc:
            raise RuntimeError(f"{INSTALL_GUIDANCE}. Import detail: {exc}") from exc
        if not torch.cuda.is_available():
            raise RuntimeError("Parakeet requires an available PyTorch CUDA device; CPU fallback is disabled.")
        try:
            path = checkpoint()
        except (OSError, ValueError) as exc:
            raise RuntimeError(DOWNLOAD_GUIDANCE) from exc
        self.model = nemo_asr.models.ASRModel.restore_from(path, map_location=torch.device("cuda"))
        self.model = self.model.float().eval()
        self.model.change_attention_model(self_attention_model="rel_pos_local_attn", att_context_size=[128, 128])
        self.model.change_subsampling_conv_chunking_factor(1)

    def transcribe(self, audio, **kwargs):
        import numpy as np
        import soundfile as sf
        import torch
        if kwargs.get("language", "en") != "en" or kwargs.get("initial_prompt") or kwargs.get("hotwords"):
            raise ValueError("Parakeet supports English without Whisper prompts or hotwords.")
        if isinstance(audio, (str, Path)):
            audio, rate = sf.read(audio, dtype="float32")
            if rate != 16000:
                raise ValueError("Parakeet input must be 16 kHz mono audio")
        audio = np.asarray(audio, dtype=np.float32)
        if audio.ndim != 1 or not np.isfinite(audio).all():
            raise ValueError("Parakeet input must be finite mono audio")
        if not len(audio):
            return [], SimpleNamespace(language="en")
        with torch.inference_mode():
            outputs = self.model.transcribe([audio], batch_size=1, num_workers=0,
                                           timestamps=True, return_hypotheses=True, verbose=False)
        if len(outputs) != 1:
            raise RuntimeError("Parakeet returned an unexpected hypothesis count")
        return parakeet_segments(outputs[0], len(audio) / 16000), SimpleNamespace(language="en")


def parakeet_segments(hypothesis, duration):
    from aura.diarization.speaker_assignment import TranscriptSegment
    stamps = (getattr(hypothesis, "timestamp", None) or {}).get("segment", [])
    if str(getattr(hypothesis, "text", "")).strip() and not stamps:
        raise RuntimeError("Parakeet returned text without segment timestamps")
    segments = []
    for stamp in stamps:
        start, end = float(stamp["start"]), float(stamp["end"])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end <= duration + .1):
            raise RuntimeError("Parakeet returned invalid segment timestamps")
        if segments and start < segments[-1].start:
            raise RuntimeError("Parakeet returned unordered segment timestamps")
        segments.append(TranscriptSegment(min(start, duration), min(end, duration), str(stamp["segment"])))
    return segments


def load_model(key):
    if key == PARAKEET:
        return ParakeetModel()
    if key != "breeze":
        raise ValueError("Unknown ASR model")
    from aura.system.cuda import preload_cuda_runtime_libraries
    ready, detail = preload_cuda_runtime_libraries()
    if not ready:
        raise RuntimeError(f"RTX/CUDA activation required: {detail}")
    from faster_whisper import WhisperModel
    return WhisperModel(MODEL_ID, device="cuda", compute_type="int8", local_files_only=True)


def runtime_receipt(key):
    from importlib.metadata import version
    if key == PARAKEET:
        return dict(worker_pid=os.getpid(), asr_model=key, model=PARAKEET_ID, revision=PARAKEET_REVISION, device="cuda",
                    compute_type="float32", backend="nemo", backend_version=version("nemo-toolkit"),
                    torch_version=version("torch"), attention="rel_pos_local_attn", attention_context=[128, 128],
                    subsampling_chunking_factor=1, batch_size=1, num_workers=0)
    return dict(worker_pid=os.getpid(), asr_model="breeze", model=MODEL_ID, device="cuda", compute_type="int8",
                backend="faster-whisper", backend_version=version("faster-whisper"))
