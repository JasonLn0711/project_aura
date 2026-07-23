import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment

from aura.audio.meeting_distance import (
    MEETING_DISTANCE_FAR_SPEAKER,
    MEETING_DISTANCE_RESCUE_OFFLINE,
    MeetingDistancePolicy,
    meeting_distance_policy_for,
)

DEEPFILTERNET3_BACKEND = "deepfilternet3"
CLEARVOICE_BACKEND = "clearvoice-mossformer2-se-48k"
CLEARVOICE_PYTHON_ENV = "AURA_CLEARVOICE_PYTHON"


@dataclass(frozen=True)
class EnhancementResult:
    backend: str
    status: str
    output_path: Path | None
    note: str
    runtime_seconds: float

    @property
    def succeeded(self) -> bool:
        return self.status == "ok" and self.output_path is not None


def import_enhancement_backend_for_policy(policy: MeetingDistancePolicy) -> str | None:
    if policy.mode == MEETING_DISTANCE_FAR_SPEAKER:
        return DEEPFILTERNET3_BACKEND
    if policy.mode == MEETING_DISTANCE_RESCUE_OFFLINE:
        return CLEARVOICE_BACKEND
    return None


def _result(backend: str, status: str, output_path: Path | None, note: str, started_at: float) -> EnhancementResult:
    return EnhancementResult(
        backend=backend,
        status=status,
        output_path=output_path,
        note=note,
        runtime_seconds=round(time.perf_counter() - started_at, 3),
    )


def _export_deepfilternet_input(input_path: Path, work_dir: Path) -> Path:
    source_path = work_dir / "deepfilternet_input_48k.wav"
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_sample_width(2).set_frame_rate(48000)
    audio.export(source_path, format="wav")
    return source_path


def _enhance_with_deepfilternet(input_path: Path, output_path: Path, started_at: float) -> EnhancementResult:
    deep_filter = shutil.which("deep-filter")
    if not deep_filter:
        return _result(
            DEEPFILTERNET3_BACKEND,
            "skipped",
            None,
            "deep-filter CLI is not installed",
            started_at,
        )

    work_dir = output_path.parent / f"{output_path.stem}_deepfilternet"
    work_dir.mkdir(parents=True, exist_ok=True)
    source_path = _export_deepfilternet_input(input_path, work_dir)
    before = {path.resolve() for path in work_dir.glob("*.wav")}
    command = [deep_filter, "-o", str(work_dir), str(source_path)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    candidates = [
        path
        for path in work_dir.glob("*.wav")
        if path.resolve() not in before and path.resolve() != source_path.resolve()
    ]
    if not candidates:
        candidates = [path for path in work_dir.glob("*.wav") if path.resolve() != source_path.resolve()]
    if not candidates:
        return _result(
            DEEPFILTERNET3_BACKEND,
            "skipped",
            None,
            "deep-filter completed without a wav output",
            started_at,
        )
    enhanced_path = max(candidates, key=lambda path: path.stat().st_mtime)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(enhanced_path, output_path)
    return _result(DEEPFILTERNET3_BACKEND, "ok", output_path, "deep-filter CLI", started_at)


def _enhance_with_clearvoice(input_path: Path, output_path: Path, started_at: float) -> EnhancementResult:
    try:
        from clearvoice import ClearVoice
    except ImportError:
        clearvoice_python = os.environ.get(CLEARVOICE_PYTHON_ENV, "").strip()
        if not clearvoice_python:
            return _result(
                CLEARVOICE_BACKEND,
                "skipped",
                None,
                (
                    "clearvoice package is not installed in the AURA environment; "
                    f"set {CLEARVOICE_PYTHON_ENV} to an isolated ClearVoice Python"
                ),
                started_at,
            )
        script_path = Path(__file__).with_name("run_clearvoice_enhancement.py")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [clearvoice_python, str(script_path), str(input_path), str(output_path)]
        subprocess.run(command, check=True, capture_output=True, text=True)
        return _result(
            CLEARVOICE_BACKEND,
            "ok",
            output_path,
            f"ClearVoice external runner via {CLEARVOICE_PYTHON_ENV}",
            started_at,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    clearvoice = ClearVoice(task="speech_enhancement", model_names=["MossFormer2_SE_48K"])
    output_wav = clearvoice(input_path=str(input_path), online_write=False)
    clearvoice.write(output_wav, output_path=str(output_path))
    return _result(CLEARVOICE_BACKEND, "ok", output_path, "ClearVoice MossFormer2_SE_48K", started_at)


def enhance_import_audio_if_available(
    input_path: str | Path,
    output_path: str | Path,
    meeting_distance_mode: str,
) -> EnhancementResult:
    started_at = time.perf_counter()
    input_path = Path(input_path)
    output_path = Path(output_path)
    policy = meeting_distance_policy_for(meeting_distance_mode)
    backend = import_enhancement_backend_for_policy(policy)
    if backend is None:
        return _result("none", "not_requested", None, "no model-based import enhancement for this mode", started_at)

    try:
        if backend == DEEPFILTERNET3_BACKEND:
            return _enhance_with_deepfilternet(input_path, output_path, started_at)
        if backend == CLEARVOICE_BACKEND:
            return _enhance_with_clearvoice(input_path, output_path, started_at)
    except Exception as exc:
        return _result(backend, "skipped", None, str(exc), started_at)

    return _result(backend, "skipped", None, f"unsupported backend: {backend}", started_at)
