# Windows Known Issues

## CUDA activation

AURA requires RTX/CUDA activation for ASR. If `windows_gpu_smoke.py` reports incomplete CUDA runtime,
check the NVIDIA driver, CUDA DLL visibility, cuBLAS/cuDNN DLLs, and `ctranslate2` GPU support.

## FFmpeg

Imported media requires `ffmpeg` and `ffprobe` on `PATH`. The runtime report lists whether FFmpeg is visible.

## Audio devices

Windows system-audio capture depends on host device support. Microphone capture is the first supported path;
system audio and system+microphone should show setup guidance when the device layer is unavailable.

## Packaging

The first Windows artifact is a portable developer release. A full installer should wait until CUDA runtime
checks and model-load smoke tests are stable on an RTX Windows machine.
