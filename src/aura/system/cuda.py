import glob
import os
import site
import sys
import ctypes

from aura.system.platform import detect_runtime_platform, platform_cuda_guidance


CUDA_RUNTIME_GLOBS = (
    "nvidia/cuda_runtime/lib/libcudart.so*",
    "nvidia/cublas/lib/libcublas.so*",
    "nvidia/cublas/lib/libcublasLt.so*",
    "nvidia/cudnn/lib/libcudnn*.so*",
    "nvidia/npp/lib/libnpp*.so*",
    "nvidia/cuda_runtime/bin/cudart64_*.dll",
    "nvidia/cublas/bin/cublas64_*.dll",
    "nvidia/cublas/bin/cublasLt64_*.dll",
    "nvidia/cudnn/bin/cudnn64_*.dll",
    "nvidia/npp/bin/npp*.dll",
)
CUDA_REQUIRED_LIBS = ("libcublas.so.12", "libcublasLt.so.12", "libnppicc.so.12")
CUDA_REQUIRED_DLLS = ("cublas64_12.dll", "cublasLt64_12.dll", "nppicc64_12.dll")
CDLL_MODE = getattr(ctypes, "RTLD_GLOBAL", getattr(ctypes, "DEFAULT_MODE", 0))


def required_cuda_libraries():
    runtime = detect_runtime_platform()
    if runtime.is_windows:
        return CUDA_REQUIRED_DLLS
    return CUDA_REQUIRED_LIBS


def _load_library(lib_name: str):
    return ctypes.CDLL(lib_name, mode=CDLL_MODE)


def _candidate_site_packages():
    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    candidates = []

    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass

    try:
        user_site = site.getusersitepackages()
        if user_site:
            candidates.append(user_site)
    except Exception:
        pass

    candidates.extend(
        [
            os.path.join(sys.prefix, "lib", py_ver, "site-packages"),
            os.path.join(sys.prefix, "Lib", "site-packages"),
            os.path.join(os.path.dirname(sys.executable), "..", "lib", py_ver, "site-packages"),
            os.path.join(os.path.dirname(sys.executable), "..", "Lib", "site-packages"),
            os.path.join(os.path.dirname(__file__), "../../../.record", "lib", py_ver, "site-packages"),
        ]
    )

    normalized = []
    seen = set()
    for path in candidates:
        real_path = os.path.realpath(path)
        if real_path not in seen and os.path.isdir(real_path):
            seen.add(real_path)
            normalized.append(real_path)
    return normalized


def preload_cuda_runtime_libraries():
    cached = getattr(preload_cuda_runtime_libraries, "_cache", None)
    if cached is not None:
        return cached

    try:
        for lib_name in required_cuda_libraries():
            _load_library(lib_name)
        result = (True, "system")
        preload_cuda_runtime_libraries._cache = result
        return result
    except OSError:
        pass

    seen = set()
    for base in _candidate_site_packages():
        for pattern in CUDA_RUNTIME_GLOBS:
            for path in sorted(glob.glob(os.path.join(base, pattern))):
                real_path = os.path.realpath(path)
                if real_path in seen:
                    continue
                seen.add(real_path)
                try:
                    _load_library(real_path)
                except OSError:
                    continue

    try:
        for lib_name in required_cuda_libraries():
            _load_library(lib_name)
        result = (True, "bundled")
    except OSError as exc:
        runtime = detect_runtime_platform()
        result = (False, f"{runtime.label}: {exc}. {platform_cuda_guidance(runtime)}")

    preload_cuda_runtime_libraries._cache = result
    return result


def is_cuda_runtime_error(error_msg):
    lowered = str(error_msg).lower()
    needles = (
        "libcublas.so",
        "libcublaslt.so",
        "libcudnn",
        "libnpp",
        "cublas64",
        "cudnn64",
        "nppicc64",
        "cudart64",
        "cannot be loaded",
        "cannot open shared object file",
        "dynamic library",
        "dll",
    )
    return any(needle in lowered for needle in needles)
