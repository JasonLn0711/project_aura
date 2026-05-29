#!/usr/bin/env python3
"""Validate that Project AURA can load faster-whisper on CUDA."""

import sys

from aura.settings import DEFAULT_SETTINGS
from aura.system.gpu_diagnostics import collect_gpu_diagnostics
from aura.system.runtime_report import build_runtime_report


def _print_section(title: str):
    print(f"\n== {title} ==")


def main() -> int:
    _print_section("nvidia-smi")
    diagnostics = collect_gpu_diagnostics()
    if not diagnostics.nvidia_smi.available:
        print("nvidia-smi: missing")
    else:
        print(diagnostics.nvidia_smi.output or diagnostics.nvidia_smi.error or "nvidia-smi returned no output")

    _print_section("Python imports")
    print(f"faster_whisper: {'ok' if diagnostics.faster_whisper_importable else 'failed'}")
    print(f"ctranslate2: {'ok' if diagnostics.ctranslate2_importable else 'failed'}")

    _print_section("CUDA runtime")
    print(f"runtime ready: {diagnostics.cuda_runtime_ready}")
    print(f"runtime detail: {diagnostics.cuda_runtime_detail}")
    for label, ready, detail in diagnostics.cuda_libraries:
        print(f"{label}: {'visible' if ready else 'missing'} ({detail})")

    failures = []
    if not diagnostics.gpu_detected:
        failures.append("GPU was not detected through nvidia-smi.")
    if not diagnostics.faster_whisper_importable:
        failures.append("Python cannot import faster_whisper.")
    if not diagnostics.ctranslate2_importable:
        failures.append("Python cannot import ctranslate2.")
    if not diagnostics.cuda_runtime_ready:
        failures.append("CUDA runtime/cuBLAS/cuDNN activation is incomplete.")

    if failures:
        _print_section("Result")
        for failure in failures:
            print(f"- {failure}")
        print(f"- Next check: {diagnostics.activation_guidance}")
        _print_section("Diagnostic report")
        print(build_runtime_report(asr_model_status="not attempted; prerequisite check failed"))
        return 1

    _print_section("WhisperModel CUDA load")
    try:
        from faster_whisper import WhisperModel

        WhisperModel(DEFAULT_SETTINGS.model_id, device="cuda", compute_type="int8")
    except Exception as exc:
        print(f"model load failed: {exc}")
        _print_section("Diagnostic report")
        print(build_runtime_report(asr_model_status=f"failed: {exc}"))
        return 1

    print(f"model load ok: {DEFAULT_SETTINGS.model_id} on cuda/int8")
    _print_section("Diagnostic report")
    print(build_runtime_report(asr_model_status="loaded on cuda/int8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
