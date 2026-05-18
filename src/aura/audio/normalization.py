import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


MEAN_VOLUME_PATTERN = re.compile(r"mean_volume:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*dB")
RESERVED_CPU_COUNT = 6


class FfmpegUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CpuDetectionResult:
    count: int | None
    source: str

    @property
    def available(self) -> bool:
        return bool(self.count and self.count > 0)


def require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FfmpegUnavailable("ffmpeg is required for fast volume normalization.")
    return ffmpeg


def parse_mean_volume(output: str) -> float | None:
    match = MEAN_VOLUME_PATTERN.search(output)
    if not match:
        return None
    value = match.group(1)
    if value == "-inf":
        return -math.inf
    if value == "inf":
        return math.inf
    return float(value)


def gain_for_target_dbfs(mean_volume: float | None, target_dbfs: float) -> float:
    if mean_volume is None or not math.isfinite(mean_volume):
        return 0.0
    return float(target_dbfs) - mean_volume


def _positive_int(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def detect_cpu_count() -> CpuDetectionResult:
    detected = _positive_int(os.cpu_count())
    if detected:
        return CpuDetectionResult(detected, "os.cpu_count")

    if hasattr(os, "sched_getaffinity"):
        try:
            affinity_count = len(os.sched_getaffinity(0))
        except OSError:
            affinity_count = 0
        detected = _positive_int(affinity_count)
        if detected:
            return CpuDetectionResult(detected, "os.sched_getaffinity")

    nproc = shutil.which("nproc")
    if nproc:
        result = subprocess.run([nproc], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            detected = _positive_int(result.stdout.strip())
            if detected:
                return CpuDetectionResult(detected, "nproc")

    cpuinfo = Path("/proc/cpuinfo")
    try:
        if cpuinfo.exists():
            processor_count = sum(1 for line in cpuinfo.read_text(encoding="utf-8").splitlines() if line.startswith("processor"))
            detected = _positive_int(processor_count)
            if detected:
                return CpuDetectionResult(detected, "/proc/cpuinfo")
    except OSError:
        pass

    return CpuDetectionResult(None, "unavailable")


def normalization_thread_count(cpu_count: int | None = None, reserved_cpus: int = RESERVED_CPU_COUNT) -> int:
    available_cpus = _positive_int(cpu_count) if cpu_count is not None else detect_cpu_count().count
    if not available_cpus:
        return 1
    return max(1, int(available_cpus) - int(reserved_cpus))


def normalization_cpu_status(reserved_cpus: int = RESERVED_CPU_COUNT) -> str:
    detected = detect_cpu_count()
    threads = normalization_thread_count(detected.count, reserved_cpus)
    if not detected.available:
        return "CPU count unavailable; using 1 FFmpeg normalization thread."
    return (
        f"CPU count detected via {detected.source}: {detected.count}; "
        f"using {threads} FFmpeg normalization threads (reserved {reserved_cpus})."
    )


def ffmpeg_cpu_args(thread_count: int | None = None) -> list[str]:
    threads = normalization_thread_count() if thread_count is None else max(1, int(thread_count))
    return ["-threads", str(threads), "-filter_threads", str(threads)]


def measure_mean_volume_dbfs(input_path: str | Path) -> float | None:
    ffmpeg = require_ffmpeg()
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        *ffmpeg_cpu_args(),
        "-i",
        str(input_path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ffmpeg volume analysis failed")
    return parse_mean_volume(result.stderr)


def normalize_media_with_ffmpeg(
    input_path: str | Path,
    output_path: str | Path,
    target_dbfs: float,
    output_format: str,
    extra_output_args: list[str] | None = None,
) -> Path:
    ffmpeg = require_ffmpeg()
    input_path = Path(input_path)
    output_path = Path(output_path)
    gain_db = gain_for_target_dbfs(measure_mean_volume_dbfs(input_path), target_dbfs)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *ffmpeg_cpu_args(),
        "-i",
        str(input_path),
        "-vn",
        "-af",
        f"volume={gain_db:.3f}dB",
        *(extra_output_args or []),
        "-f",
        output_format,
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ffmpeg normalization failed")
    return output_path


def normalize_media_to_wav(input_path: str | Path, output_path: str | Path, target_dbfs: float) -> Path:
    return normalize_media_with_ffmpeg(
        input_path=input_path,
        output_path=output_path,
        target_dbfs=target_dbfs,
        output_format="wav",
        extra_output_args=["-c:a", "pcm_s16le"],
    )


def normalize_wav_to_mp3_with_ffmpeg(wav_path: str | Path, mp3_path: str | Path, target_dbfs: float) -> Path:
    return normalize_media_with_ffmpeg(
        input_path=wav_path,
        output_path=mp3_path,
        target_dbfs=target_dbfs,
        output_format="mp3",
        extra_output_args=["-c:a", "libmp3lame"],
    )
