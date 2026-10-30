import ctypes
import ctypes.util
import importlib
import importlib.metadata
import os
import shutil
import subprocess
from dataclasses import dataclass

from aura.system.cuda import preload_cuda_runtime_libraries
from aura.system.platform import detect_runtime_platform, platform_cuda_guidance


CUDA_LIBRARY_NAMES = (
    ("CUDA runtime", ("cudart64_12.dll", "libcudart.so.12", "cudart")),
    ("cuBLAS", ("cublas64_12.dll", "libcublas.so.12", "cublas")),
    ("cuBLASLt", ("cublasLt64_12.dll", "libcublasLt.so.12", "cublasLt")),
    ("cuDNN", ("cudnn64_9.dll", "cudnn64_8.dll", "libcudnn.so.9", "libcudnn.so.8", "cudnn")),
)


@dataclass(frozen=True)
class CommandCheck:
    executable: str
    available: bool
    returncode: int | None = None
    output: str = ""
    error: str = ""


@dataclass(frozen=True)
class GpuDiagnostics:
    nvidia_smi: CommandCheck
    faster_whisper_importable: bool
    faster_whisper_version: str | None
    ctranslate2_importable: bool
    ctranslate2_version: str | None
    cuda_runtime_ready: bool
    cuda_runtime_detail: str
    cuda_libraries: tuple[tuple[str, bool, str], ...]
    activation_guidance: str

    @property
    def gpu_detected(self) -> bool:
        return self.nvidia_smi.available and self.nvidia_smi.returncode == 0

    @property
    def import_ready(self) -> bool:
        return self.faster_whisper_importable and self.ctranslate2_importable

    @property
    def cuda_ready(self) -> bool:
        return self.cuda_runtime_ready

    @property
    def status_line(self) -> str:
        gpu_status = "GPU detected" if self.gpu_detected else "GPU not detected"
        cuda_status = "CUDA runtime ready" if self.cuda_ready else "CUDA runtime incomplete"
        import_status = "ASR imports ready" if self.import_ready else "ASR imports incomplete"
        return f"{gpu_status}; {cuda_status}; {import_status}"


def _version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _module_importable(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def run_nvidia_smi(timeout: int = 10) -> CommandCheck:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return CommandCheck(executable="nvidia-smi", available=False)
    command = [
        executable,
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:
        return CommandCheck(executable=executable, available=True, error=str(exc))
    return CommandCheck(
        executable=executable,
        available=True,
        returncode=result.returncode,
        output=result.stdout.strip(),
        error=result.stderr.strip(),
    )


def _try_load_library(names: tuple[str, ...]) -> tuple[bool, str]:
    for name in names:
        candidates = [name]
        found = ctypes.util.find_library(name)
        if found:
            candidates.insert(0, found)
        for candidate in candidates:
            try:
                ctypes.CDLL(candidate)
                return True, candidate
            except OSError:
                continue
    return False, "not found"


def collect_cuda_library_status() -> tuple[tuple[str, bool, str], ...]:
    results = []
    path_hint = os.environ.get("PATH", "")
    for label, names in CUDA_LIBRARY_NAMES:
        ready, detail = _try_load_library(names)
        if not ready and label == "CUDA runtime" and "CUDA_PATH" in os.environ:
            detail = f"not found; CUDA_PATH={os.environ['CUDA_PATH']}"
        elif not ready and not path_hint:
            detail = "not found; PATH is empty"
        results.append((label, ready, detail))
    return tuple(results)


def collect_gpu_diagnostics() -> GpuDiagnostics:
    runtime = detect_runtime_platform()
    runtime_ready, runtime_detail = preload_cuda_runtime_libraries()
    cuda_libraries = collect_cuda_library_status()
    if runtime_ready:
        cuda_libraries = tuple(
            (label, True, runtime_detail)
            if label == "CUDA runtime" and not ready
            else (label, ready, detail)
            for label, ready, detail in cuda_libraries
        )
    return GpuDiagnostics(
        nvidia_smi=run_nvidia_smi(),
        faster_whisper_importable=_module_importable("faster_whisper"),
        faster_whisper_version=_version("faster-whisper"),
        ctranslate2_importable=_module_importable("ctranslate2"),
        ctranslate2_version=_version("ctranslate2"),
        cuda_runtime_ready=runtime_ready,
        cuda_runtime_detail=runtime_detail,
        cuda_libraries=cuda_libraries,
        activation_guidance=platform_cuda_guidance(runtime),
    )
