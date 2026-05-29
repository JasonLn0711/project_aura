#!/usr/bin/env python3
"""Run a tiny CUDA ASR pass and verify transcript artifact output."""

import math
import struct
import tempfile
import wave
from pathlib import Path

from faster_whisper import WhisperModel

from aura.settings import DEFAULT_SETTINGS
from aura.system.gpu_diagnostics import collect_gpu_diagnostics
from aura.ui.transcript_io import transcript_artifact_paths, write_json_file, write_transcript_artifacts


def write_sample_wav(path: Path, seconds: float = 1.0, sample_rate: int = 16000):
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            value = int(0.18 * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
            frames.extend(struct.pack("<h", value))
        wav_file.writeframes(bytes(frames))


def main() -> int:
    diagnostics = collect_gpu_diagnostics()
    if not diagnostics.gpu_detected or not diagnostics.cuda_ready or not diagnostics.import_ready:
        print("RTX/CUDA prerequisites are incomplete.")
        print(diagnostics.status_line)
        print(diagnostics.activation_guidance)
        return 1

    with tempfile.TemporaryDirectory(prefix="aura_asr_artifact_smoke_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        sample_path = tmpdir_path / "sample_audio_smoke.wav"
        output_base = tmpdir_path / "artifact_smoke"
        write_sample_wav(sample_path)

        model = WhisperModel(DEFAULT_SETTINGS.model_id, device="cuda", compute_type="int8")
        segments, info = model.transcribe(str(sample_path), beam_size=1, language="en")
        lines = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                lines.append(f"[{segment.start:.2f}-{segment.end:.2f}] {text}")

        transcript = "\n".join(lines) or "[smoke] ASR completed with no speech segments."
        saved = write_transcript_artifacts(str(output_base), transcript)
        metrics_path = transcript_artifact_paths(str(output_base))["metrics"]
        saved["metrics"] = write_json_file(
            metrics_path,
            {
                "workflow": "windows_self_hosted_rtx_asr_artifact_smoke",
                "source_path": str(sample_path),
                "model_id": DEFAULT_SETTINGS.model_id,
                "device": "cuda",
                "compute_type": "int8",
                "language": getattr(info, "language", None),
                "segment_count": len(lines),
                "outputs": {name: str(path) for name, path in saved.items()},
            },
        )

        required_outputs = ("raw", "final", "metrics")
        missing = [name for name in required_outputs if name not in saved or not saved[name].exists()]
        empty = [name for name in required_outputs if name in saved and saved[name].stat().st_size <= 0]
        if missing or empty:
            print(f"Artifact smoke failed. missing={missing} empty={empty}")
            return 1

        print("ASR artifact smoke completed on cuda/int8.")
        for name in required_outputs:
            print(f"{name}: {saved[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
