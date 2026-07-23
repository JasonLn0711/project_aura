import datetime
import importlib.util
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from aura.asr.punctuation import PUNCTUATION_SETUP_GUIDANCE
from aura.config import DIARIZATION_MODEL_ID
from aura.diarization.pyannote_pipeline import HF_TOKEN_ENV, HUGGINGFACE_TOKEN_ENV, huggingface_token
from aura.llm.ollama_runtime import (
    DEFAULT_OLLAMA_HOST,
    check_ollama_command,
    ollama_tags,
    validate_localhost_host,
)
from aura.metadata import __version__
from aura.system.audio_diagnostics import AudioDiagnostics, collect_audio_diagnostics
from aura.system.gpu_diagnostics import GpuDiagnostics, collect_gpu_diagnostics
from aura.system.platform import RuntimePlatform, detect_runtime_platform
from summary.field_schemas import OLLAMA_MODEL_TAG, OLLAMA_REASONING_ENABLED


MIN_OUTPUT_FREE_BYTES = 1 << 30


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
class PunctuationDiagnostics:
    torch_available: bool = False
    transformers_available: bool = False

    @property
    def ready(self) -> bool:
        return self.torch_available and self.transformers_available

    @property
    def status_line(self) -> str:
        if self.ready:
            return "local model dependencies ready"
        missing = [
            name
            for name, ready in (("torch", self.torch_available), ("transformers", self.transformers_available))
            if not ready
        ]
        return f"rule fallback ready; missing {', '.join(missing)}. {PUNCTUATION_SETUP_GUIDANCE}"


@dataclass(frozen=True)
class OllamaDiagnostics:
    configured: bool = False
    host: str = ""
    model_tag: str = ""
    command_available: bool = False
    server_ready: bool = False
    model_available: bool = False
    detail: str = "not configured"

    @property
    def ready(self) -> bool:
        return self.configured and self.server_ready and self.model_available


@dataclass(frozen=True)
class RuntimeDiagnostics:
    platform: RuntimePlatform
    gpu: GpuDiagnostics
    audio: AudioDiagnostics
    diarization: DiarizationDiagnostics = DiarizationDiagnostics()
    punctuation: PunctuationDiagnostics = PunctuationDiagnostics()
    ollama: OllamaDiagnostics = OllamaDiagnostics()
    asr_model_status: str = "not loaded"
    output_folder: str = ""
    output_folder_writable: bool = False
    output_folder_free_bytes: int | None = None
    minimum_free_bytes: int = MIN_OUTPUT_FREE_BYTES

    @property
    def output_folder_space_ready(self) -> bool:
        return self.output_folder_free_bytes is not None and self.output_folder_free_bytes >= self.minimum_free_bytes

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


def collect_punctuation_diagnostics() -> PunctuationDiagnostics:
    return PunctuationDiagnostics(
        torch_available=_module_available("torch"),
        transformers_available=_module_available("transformers"),
    )


@dataclass(frozen=True)
class FirstLaunchCheck:
    key: str
    label: str
    ready: bool
    detail: str
    fix_guidance: str


def _output_folder_status(output_folder: str | os.PathLike[str]) -> tuple[str, bool, int | None]:
    selected = Path(output_folder).expanduser().resolve()
    if selected.exists() and not selected.is_dir():
        return str(selected), False, None
    probe = selected
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return str(selected), os.access(probe, os.W_OK), shutil.disk_usage(probe).free
    except OSError:
        return str(selected), False, None


def collect_ollama_diagnostics(host: str | None, model_tag: str | None) -> OllamaDiagnostics:
    if not host or not model_tag:
        return OllamaDiagnostics()
    command_available = check_ollama_command()
    try:
        validate_localhost_host(host)
        tags = ollama_tags(host, timeout_sec=1)
    except Exception as exc:
        return OllamaDiagnostics(
            configured=True,
            host=host,
            model_tag=model_tag,
            command_available=command_available,
            detail=str(exc) or type(exc).__name__,
        )
    if not isinstance(tags, dict):
        return OllamaDiagnostics(
            configured=True,
            host=host,
            model_tag=model_tag,
            command_available=command_available,
            detail="Ollama tags endpoint returned an invalid response.",
        )
    names = {
        str(model.get("name") or "")
        for model in tags.get("models") or []
        if isinstance(model, dict)
    }
    model_available = model_tag in names
    return OllamaDiagnostics(
        configured=True,
        host=host,
        model_tag=model_tag,
        command_available=command_available,
        server_ready=True,
        model_available=model_available,
        detail=(
            f"Local Ollama runtime ready with model {model_tag}."
            if model_available
            else f"Required local model tag not found: {model_tag}"
        ),
    )


def collect_runtime_diagnostics(
    asr_model_status: str = "not loaded",
    output_folder: str | os.PathLike[str] | None = None,
    minimum_free_bytes: int = MIN_OUTPUT_FREE_BYTES,
    ollama_host: str | None = DEFAULT_OLLAMA_HOST,
    ollama_model_tag: str | None = OLLAMA_MODEL_TAG,
) -> RuntimeDiagnostics:
    selected_output, output_writable, output_free_bytes = _output_folder_status(output_folder or os.getcwd())
    return RuntimeDiagnostics(
        platform=detect_runtime_platform(),
        gpu=collect_gpu_diagnostics(),
        audio=collect_audio_diagnostics(),
        diarization=collect_diarization_diagnostics(),
        punctuation=collect_punctuation_diagnostics(),
        ollama=collect_ollama_diagnostics(ollama_host, ollama_model_tag),
        asr_model_status=asr_model_status,
        output_folder=selected_output,
        output_folder_writable=output_writable,
        output_folder_free_bytes=output_free_bytes,
        minimum_free_bytes=minimum_free_bytes,
    )


def first_launch_checks(diagnostics: RuntimeDiagnostics) -> tuple[FirstLaunchCheck, ...]:
    ffmpeg_ready = bool(diagnostics.audio.ffmpeg_path or shutil.which("ffmpeg"))
    model_status = diagnostics.asr_model_status.strip().lower()
    model_ready = model_status.startswith("loaded")
    checks = [
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
            detail=(
                f"Selected output folder is writable: {diagnostics.output_folder or os.getcwd()}"
                if diagnostics.output_folder_writable
                else f"Selected output folder is not writable: {diagnostics.output_folder or os.getcwd()}"
            ),
            fix_guidance="Choose or move AURA to a writable folder before recording or importing media.",
        ),
        FirstLaunchCheck(
            key="disk_space",
            label="Output Disk Space",
            ready=diagnostics.output_folder_space_ready,
            detail=(
                f"{diagnostics.output_folder_free_bytes} bytes available; "
                f"{diagnostics.minimum_free_bytes} bytes required."
                if diagnostics.output_folder_free_bytes is not None
                else "Available disk space could not be read."
            ),
            fix_guidance="Choose an output folder with enough free disk space for the recording.",
        ),
        FirstLaunchCheck(
            key="asr_model",
            label="ASR Model Load",
            ready=model_ready,
            detail=diagnostics.asr_model_status,
            fix_guidance="Use Check-AURA.bat or reload the model after GPU/CUDA readiness is complete.",
        ),
    ]
    if diagnostics.ollama.configured:
        checks.extend(
            [
                FirstLaunchCheck(
                    key="ollama_command",
                    label="Ollama Command",
                    ready=diagnostics.ollama.command_available,
                    detail=(
                        "Ollama command is available on PATH."
                        if diagnostics.ollama.command_available
                        else "Ollama command is not available on PATH."
                    ),
                    fix_guidance="Install Ollama or add its command to PATH.",
                ),
                FirstLaunchCheck(
                    key="ollama_server",
                    label="Ollama Local Server",
                    ready=diagnostics.ollama.server_ready,
                    detail=f"{diagnostics.ollama.host}: {diagnostics.ollama.detail}",
                    fix_guidance="Start the local Ollama service, then refresh the runtime check.",
                ),
                FirstLaunchCheck(
                    key="ollama_model",
                    label="Ollama Summary Model",
                    ready=diagnostics.ollama.model_available,
                    detail=diagnostics.ollama.detail,
                    fix_guidance=f"Run: ollama pull {diagnostics.ollama.model_tag}",
                ),
            ]
        )
    return tuple(checks)


def activation_report_line(diagnostics: RuntimeDiagnostics) -> str:
    if diagnostics.gpu.cuda_ready:
        return "- CUDA runtime preload: complete"
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
            f"- Selected output folder: {diagnostics.output_folder or os.getcwd()}",
            f"- Selected output folder writable: {'yes' if diagnostics.output_folder_writable else 'no'}",
            f"- Output folder free bytes: {diagnostics.output_folder_free_bytes if diagnostics.output_folder_free_bytes is not None else 'unknown'}",
            f"- Output disk space status: {'ready' if diagnostics.output_folder_space_ready else 'needs attention'}",
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
    if diagnostics.ollama.configured:
        lines.extend(
            [
                "",
                "Local LLM / Ollama",
                f"- Host: {diagnostics.ollama.host}",
                f"- Command: {'available' if diagnostics.ollama.command_available else 'missing'}",
                f"- Server: {'ready' if diagnostics.ollama.server_ready else 'unavailable'}",
                f"- Required model tag: {diagnostics.ollama.model_tag}",
                f"- Reasoning: {'enabled' if OLLAMA_REASONING_ENABLED else 'disabled'} (think=true)",
                f"- Model tag: {'ready' if diagnostics.ollama.model_available else 'missing'}",
                f"- Detail: {diagnostics.ollama.detail}",
            ]
        )
    lines.extend(
        [
            "",
            "Traditional Chinese Punctuation",
            "- Rule fallback: ready",
            f"- torch import: {'ok' if diagnostics.punctuation.torch_available else 'missing'}",
            f"- transformers import: {'ok' if diagnostics.punctuation.transformers_available else 'missing'}",
            f"- Local model status: {diagnostics.punctuation.status_line}",
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


def build_runtime_report(
    asr_model_status: str = "not loaded",
    output_folder: str | os.PathLike[str] | None = None,
    minimum_free_bytes: int = MIN_OUTPUT_FREE_BYTES,
    ollama_host: str | None = DEFAULT_OLLAMA_HOST,
    ollama_model_tag: str | None = OLLAMA_MODEL_TAG,
) -> str:
    return format_runtime_report(
        collect_runtime_diagnostics(
            asr_model_status=asr_model_status,
            output_folder=output_folder,
            minimum_free_bytes=minimum_free_bytes,
            ollama_host=ollama_host,
            ollama_model_tag=ollama_model_tag,
        )
    )
