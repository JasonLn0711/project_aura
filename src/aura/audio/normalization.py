import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


MEAN_VOLUME_PATTERN = re.compile(r"mean_volume:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*dB")
RESERVED_CPU_COUNT = 6
MP3_EXPORT_ARGS = ["-c:a", "libmp3lame", "-q:a", "0"]
ProgressCallback = Callable[[str], None]


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


def require_ffprobe() -> str | None:
    return shutil.which("ffprobe")


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


def normalization_filter_chain(gain_db: float) -> str:
    return f"volume={gain_db:.3f}dB,alimiter=limit=0.95"


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


def probe_duration_seconds(input_path: str | Path) -> float | None:
    ffprobe = require_ffprobe()
    if not ffprobe:
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    return duration if math.isfinite(duration) and duration > 0 else None


def emit_progress(callback: ProgressCallback | None, message: str):
    if callback:
        callback(message)


def measure_mean_volume_dbfs(input_path: str | Path, progress_callback: ProgressCallback | None = None) -> float | None:
    ffmpeg = require_ffmpeg()
    emit_progress(progress_callback, "🔎 Volume analysis pass 1/2: scanning audio level...")
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
    mean_volume = parse_mean_volume(result.stderr)
    if mean_volume is None or not math.isfinite(mean_volume):
        emit_progress(progress_callback, "🔎 Volume analysis complete: no finite mean volume; using 0.000 dB gain.")
    else:
        emit_progress(progress_callback, f"🔎 Volume analysis complete: mean {mean_volume:.1f} dBFS.")
    return mean_volume


def parse_out_time_ms(value: str) -> float | None:
    try:
        microseconds = int(value)
    except ValueError:
        return None
    return max(0.0, microseconds / 1_000_000)


def run_ffmpeg_with_progress(
    command: list[str],
    duration_seconds: float | None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    last_percent = -1
    stdout = ""
    stderr = ""
    if process.stdout:
        for line in process.stdout:
            stdout += line
            key, _, value = line.strip().partition("=")
            if key == "out_time_ms" and duration_seconds:
                elapsed_seconds = parse_out_time_ms(value)
                if elapsed_seconds is None:
                    continue
                percent = min(99, int((elapsed_seconds / duration_seconds) * 100))
                if percent >= last_percent + 5:
                    last_percent = percent
                    emit_progress(progress_callback, f"🔉 Volume normalization pass 2/2: {percent}%")

    _, stderr = process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "ffmpeg normalization failed")


def normalize_media_with_ffmpeg(
    input_path: str | Path,
    output_path: str | Path,
    target_dbfs: float,
    output_format: str,
    extra_output_args: list[str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    ffmpeg = require_ffmpeg()
    input_path = Path(input_path)
    output_path = Path(output_path)
    duration_seconds = probe_duration_seconds(input_path)
    if duration_seconds:
        emit_progress(progress_callback, f"⏱️ Media duration detected: {duration_seconds:.1f}s.")
    else:
        emit_progress(progress_callback, "⏱️ Media duration unavailable; showing stage progress only.")
    mean_volume = measure_mean_volume_dbfs(input_path, progress_callback)
    gain_db = gain_for_target_dbfs(mean_volume, target_dbfs)
    emit_progress(progress_callback, f"🎚️ Applying gain: {gain_db:.3f} dB toward target {target_dbfs:.1f} dBFS.")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-progress",
        "pipe:1",
        "-nostats",
        *ffmpeg_cpu_args(),
        "-i",
        str(input_path),
        "-vn",
        "-af",
        normalization_filter_chain(gain_db),
        *(extra_output_args or []),
        "-f",
        output_format,
        str(output_path),
    ]
    emit_progress(progress_callback, "🔉 Volume normalization pass 2/2: exporting normalized audio...")
    run_ffmpeg_with_progress(command, duration_seconds, progress_callback)
    emit_progress(progress_callback, "✅ Volume normalization complete.")
    return output_path


def normalize_media_to_wav(
    input_path: str | Path,
    output_path: str | Path,
    target_dbfs: float,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    return normalize_media_with_ffmpeg(
        input_path=input_path,
        output_path=output_path,
        target_dbfs=target_dbfs,
        output_format="wav",
        extra_output_args=["-c:a", "pcm_s16le"],
        progress_callback=progress_callback,
    )


def normalize_wav_to_mp3_with_ffmpeg(
    wav_path: str | Path,
    mp3_path: str | Path,
    target_dbfs: float,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    return normalize_media_with_ffmpeg(
        input_path=wav_path,
        output_path=mp3_path,
        target_dbfs=target_dbfs,
        output_format="mp3",
        extra_output_args=MP3_EXPORT_ARGS,
        progress_callback=progress_callback,
    )
