import datetime
import importlib.util
import os
import shutil
import sys
from dataclasses import dataclass

from aura.config import DIARIZATION_MODEL_ID
from aura.diarization.pyannote_pipeline import HF_TOKEN_ENV, HUGGINGFACE_TOKEN_ENV, huggingface_token
from aura.metadata import __version__
from aura.system.audio_diagnostics import AudioDiagnostics, collect_audio_diagnostics
from aura.system.gpu_diagnostics import GpuDiagnostics, collect_gpu_diagnostics
from aura.system.platform import RuntimePlatform, detect_runtime_platform


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


@dataclass(frozen=True)
class DiarizationDiagnostics:
    model_id: str = DIARIZATION_MODEL_ID
    pyannote_available: bool = False
    torch_available: bool = False
    torch_cuda_available: bool = False
    token_available: bool = False

    @property
    def ready(self) -> bool:
        return self.pyannote_available and self.torch_available and self.token_available

    @property
    def status_line(self) -> str:
        missing = []
        if not self.pyannote_available:
            missing.append("pyannote.audio")
        if not self.torch_available:
            missing.append("torch")
        if not self.token_available:
            missing.append(f"{HUGGINGFACE_TOKEN_ENV} or {HF_TOKEN_ENV}")
        if missing:
            return "needs setup: " + ", ".join(missing)
        if self.torch_cuda_available:
            return "ready with CUDA-capable torch"
        return "ready; torch is installed but CUDA is not available"


@dataclass(frozen=True)
class RuntimeDiagnostics:
    platform: RuntimePlatform
    gpu: GpuDiagnostics
    audio: AudioDiagnostics
    diarization: DiarizationDiagnostics = DiarizationDiagnostics()
    asr_model_status: str = "not loaded"
    output_folder_writable: bool = False

    @property
    def gpu_status(self) -> str:
        return "ready" if self.gpu.gpu_detected else "not detected"

    @property
    def cuda_status(self) -> str:
        return "ready" if self.gpu.cuda_ready else "incomplete"

    @property
    def audio_status(self) -> str:
        return self.audio.status_line


def collect_diarization_diagnostics() -> DiarizationDiagnostics:
    torch_available = _module_available("torch")
    torch_cuda_available = False
    if torch_available:
        try:
            import torch

            torch_cuda_available = bool(torch.cuda.is_available())
        except Exception:
            torch_cuda_available = False
    return DiarizationDiagnostics(
        pyannote_available=_module_available("pyannote.audio"),
        torch_available=torch_available,
        torch_cuda_available=torch_cuda_available,
        token_available=bool(huggingface_token()),
    )


@dataclass(frozen=True)
class FirstLaunchCheck:
    key: str
    label: str
    ready: bool
    detail: str
    fix_guidance: str


def collect_runtime_diagnostics(asr_model_status: str = "not loaded") -> RuntimeDiagnostics:
    return RuntimeDiagnostics(
        platform=detect_runtime_platform(),
        gpu=collect_gpu_diagnostics(),
        audio=collect_audio_diagnostics(),
        diarization=collect_diarization_diagnostics(),
        asr_model_status=asr_model_status,
        output_folder_writable=os.access(os.getcwd(), os.W_OK),
    )


def first_launch_checks(diagnostics: RuntimeDiagnostics) -> tuple[FirstLaunchCheck, ...]:
    ffmpeg_ready = bool(diagnostics.audio.ffmpeg_path or shutil.which("ffmpeg"))
    model_status = diagnostics.asr_model_status.strip().lower()
    model_ready = model_status.startswith("loaded")
    return (
        FirstLaunchCheck(
            key="gpu",
            label="GPU Ready",
            ready=diagnostics.gpu.gpu_detected,
            detail=diagnostics.gpu.nvidia_smi.output or diagnostics.gpu.nvidia_smi.error or "No GPU reported.",
            fix_guidance="Install or update the NVIDIA driver, then confirm nvidia-smi lists the RTX GPU.",
        ),
        FirstLaunchCheck(
            key="cuda",
            label="CUDA Ready",
            ready=diagnostics.gpu.cuda_ready,
            detail=diagnostics.gpu.cuda_runtime_detail,
            fix_guidance=diagnostics.gpu.activation_guidance,
        ),
        FirstLaunchCheck(
            key="ffmpeg",
            label="FFmpeg Ready",
            ready=ffmpeg_ready,
            detail=diagnostics.audio.ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg is not on PATH.",
            fix_guidance="Install FFmpeg and make sure both ffmpeg and ffprobe are available on PATH.",
        ),
        FirstLaunchCheck(
            key="microphone",
            label="Microphone Ready",
            ready=bool(diagnostics.audio.input_devices),
            detail=diagnostics.audio.status_line,
            fix_guidance="Connect or enable a microphone/audio input device and allow Windows microphone access.",
        ),
        FirstLaunchCheck(
            key="output",
            label="Output Folder",
            ready=diagnostics.output_folder_writable,
            detail="Current working folder is writable." if diagnostics.output_folder_writable else "Current folder is not writable.",
            fix_guidance="Choose or move AURA to a writable folder before recording or importing media.",
        ),
        FirstLaunchCheck(
            key="asr_model",
            label="ASR Model Load",
            ready=model_ready,
            detail=diagnostics.asr_model_status,
            fix_guidance="Use Check-AURA.bat or reload the model after GPU/CUDA readiness is complete.",
        ),
    )


def activation_report_line(diagnostics: RuntimeDiagnostics) -> str:
    if diagnostics.gpu.cuda_ready:
        return "- Activation status: complete"
    return f"- Activation guidance: {diagnostics.gpu.activation_guidance}"


def format_runtime_report(diagnostics: RuntimeDiagnostics) -> str:
    gpu = diagnostics.gpu
    audio = diagnostics.audio
    platform = diagnostics.platform
    lines = [
        "Project AURA Runtime Diagnostic Report",
        f"Generated: {datetime.datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"AURA version: {__version__}",
        "",
        "Platform",
        f"- Environment: {platform.label}",
        f"- OS: {platform.system} {platform.release}",
        f"- Machine: {platform.machine}",
        f"- Python: {platform.python_version}",
        f"- Executable: {sys.executable}",
        "",
        "GPU / CUDA",
        f"- nvidia-smi: {'available' if gpu.nvidia_smi.available else 'missing'}",
        f"- GPU detected: {'yes' if gpu.gpu_detected else 'no'}",
        f"- nvidia-smi output: {gpu.nvidia_smi.output or gpu.nvidia_smi.error or 'none'}",
        f"- CUDA runtime status: {'ready' if gpu.cuda_ready else 'incomplete'}",
        f"- CUDA runtime detail: {gpu.cuda_runtime_detail}",
        f"- faster-whisper import: {'ok' if gpu.faster_whisper_importable else 'failed'}",
        f"- faster-whisper version: {gpu.faster_whisper_version or 'unknown'}",
        f"- ctranslate2 import: {'ok' if gpu.ctranslate2_importable else 'failed'}",
        f"- ctranslate2 version: {gpu.ctranslate2_version or 'unknown'}",
    ]
    for label, ready, detail in gpu.cuda_libraries:
        lines.append(f"- {label}: {'visible' if ready else 'missing'} ({detail})")
    lines.extend(
        [
            f"- ASR model load status: {diagnostics.asr_model_status}",
            f"- Current output folder writable: {'yes' if diagnostics.output_folder_writable else 'no'}",
            activation_report_line(diagnostics),
            "",
            "Audio / FFmpeg",
            f"- FFmpeg: {audio.ffmpeg_path or shutil.which('ffmpeg') or 'missing'}",
            f"- PyAudio import: {'ok' if audio.pyaudio_available else 'failed'}",
            f"- Audio input devices: {len(audio.input_devices)}",
            f"- Audio output devices: {len(audio.output_devices)}",
            f"- Audio detail: {audio.status_line}",
        ]
    )
    if audio.input_devices:
        lines.append("- Input device names: " + "; ".join(audio.input_devices[:8]))
    if audio.output_devices:
        lines.append("- Output device names: " + "; ".join(audio.output_devices[:8]))
    lines.extend(
        [
            "",
            "Optional Speaker Diarization",
            f"- Model: {diagnostics.diarization.model_id}",
            f"- pyannote.audio import: {'ok' if diagnostics.diarization.pyannote_available else 'missing'}",
            f"- torch import: {'ok' if diagnostics.diarization.torch_available else 'missing'}",
            f"- torch CUDA: {'available' if diagnostics.diarization.torch_cuda_available else 'not available'}",
            f"- Hugging Face token: {'configured' if diagnostics.diarization.token_available else 'missing'}",
            f"- Diarization status: {diagnostics.diarization.status_line}",
        ]
    )
    lines.extend(["", "First Launch Check"])
    for check in first_launch_checks(diagnostics):
        lines.append(f"- {check.label}: {'ready' if check.ready else 'needs attention'} ({check.detail})")
    return "\n".join(lines)


def build_runtime_report(asr_model_status: str = "not loaded") -> str:
    return format_runtime_report(collect_runtime_diagnostics(asr_model_status=asr_model_status))
