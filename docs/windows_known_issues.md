# Windows Known Issues

Last updated: 2026-05-29 for Project AURA `v1.13.0`.

## CUDA activation

AURA requires RTX/CUDA activation for ASR. If `windows_gpu_smoke.py` reports incomplete CUDA runtime,
check the NVIDIA driver, CUDA DLL visibility, cuBLAS/cuDNN DLLs, and `ctranslate2` GPU support.

## FFmpeg

Imported media requires `ffmpeg` and `ffprobe` on `PATH`. The runtime report lists whether FFmpeg is visible.

## Audio devices

Windows system-audio capture depends on host device support. Microphone capture is the first supported path;
system audio and system+microphone should show setup guidance when the device layer is unavailable.

## Packaging

The first Windows artifact is a portable ZIP release. A full installer should wait until CUDA runtime
checks and model-load smoke tests are stable on an RTX Windows machine.

The portable builder creates `sample_audio/aura_smoke_1s.wav` for packaging and import smoke checks. Real
speech samples should stay outside git and be attached only to release validation runs when licensing allows it.

The `v1.13.0` portable ZIP is an onboarding artifact, not a full installer. `Start-AURA.bat` and
`Check-AURA.bat` still require Python 3.11, FFmpeg, and a working NVIDIA driver to be installed on the host.
