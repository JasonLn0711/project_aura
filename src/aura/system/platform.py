import os
import platform as python_platform
from dataclasses import dataclass
from pathlib import Path


WINDOWS_NATIVE = "windows_native"
WSL = "wsl"
LINUX_NATIVE = "linux_native"
DOCKER_CONTAINER = "docker_container"
OTHER = "other"


@dataclass(frozen=True)
class RuntimePlatform:
    kind: str
    system: str
    release: str
    machine: str
    python_version: str
    is_windows: bool
    is_wsl: bool
    is_docker: bool

    @property
    def label(self) -> str:
        labels = {
            WINDOWS_NATIVE: "Windows native",
            WSL: "WSL",
            LINUX_NATIVE: "Linux native",
            DOCKER_CONTAINER: "Docker container",
            OTHER: "Other",
        }
        return labels.get(self.kind, self.kind)


def _file_contains(path: str, needle: str) -> bool:
    try:
        return needle.lower() in Path(path).read_text(errors="ignore").lower()
    except OSError:
        return False


def is_wsl_environment() -> bool:
    if python_platform.system().lower() != "linux":
        return False
    release = python_platform.release().lower()
    return "microsoft" in release or _file_contains("/proc/version", "microsoft")


def is_docker_environment() -> bool:
    if os.environ.get("container"):
        return True
    if Path("/.dockerenv").exists():
        return True
    return _file_contains("/proc/1/cgroup", "docker") or _file_contains("/proc/1/cgroup", "kubepods")


def detect_runtime_platform() -> RuntimePlatform:
    system = python_platform.system()
    system_lower = system.lower()
    release = python_platform.release()
    machine = python_platform.machine()
    is_windows = system_lower == "windows"
    is_wsl = is_wsl_environment()
    is_docker = is_docker_environment()

    if is_windows:
        kind = WINDOWS_NATIVE
    elif is_wsl:
        kind = WSL
    elif is_docker:
        kind = DOCKER_CONTAINER
    elif system_lower == "linux":
        kind = LINUX_NATIVE
    else:
        kind = OTHER

    return RuntimePlatform(
        kind=kind,
        system=system,
        release=release,
        machine=machine,
        python_version=python_platform.python_version(),
        is_windows=is_windows,
        is_wsl=is_wsl,
        is_docker=is_docker,
    )


def platform_cuda_guidance(runtime: RuntimePlatform | None = None) -> str:
    runtime = runtime or detect_runtime_platform()
    if runtime.kind == WINDOWS_NATIVE:
        return "Check the NVIDIA driver, CUDA DLL visibility, cuBLAS/cuDNN DLLs, and ctranslate2 GPU support."
    if runtime.kind == WSL:
        return "Check /dev/dxg, /usr/lib/wsl/lib/nvidia-smi, the Windows NVIDIA driver, and WSL-visible CUDA libraries."
    if runtime.kind == DOCKER_CONTAINER:
        return "Start the container with --gpus all and confirm the NVIDIA container runtime exposes CUDA libraries."
    if runtime.kind == LINUX_NATIVE:
        return "Check that CUDA, cuBLAS, and cuDNN runtime libraries are installed or available from Python wheels."
    return "Check NVIDIA driver, CUDA runtime libraries, and ctranslate2 GPU support for this platform."
