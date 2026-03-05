# Project AURA: Ultimate Audio Assistant (全方位錄音助理)

![CI Status](https://img.shields.io/badge/Status-Prototype-informational?logo=github) ![Python Version](https://img.shields.io/badge/Python-3.12.3-blue?logo=python) ![ASR Engine](https://img.shields.io/badge/ASR-faster--whisper-orange) ![UI](https://img.shields.io/badge/UI-PyQt6-9cf) ![VAD](https://img.shields.io/badge/VAD-WebRTC_VAD-success) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

![alt text](./img/image.png)
## Executive Summary & Project Metadata

**Project AURA** is a dual-core desktop assistant that integrates:

1) **Real-time / file-based transcription** (ASR) with timestamped logs  
2) **Smart audio splitting** that finds natural pause points to avoid cutting speech mid-sentence

Designed for professional environments, this project features prompt-guided punctuation, background noise reduction, batch processing, and robust memory management for heavy AI workloads.

- **Project Name**: Project AURA (Ultimate Audio Assistant)
- **Academic Affiliation**: National Yang Ming Chiao Tung University (NYCU)
- **Project Lead**: Jason Chia-Sheng Lin (PhD. Student)
- **Release Version**: `2.1.0` (Major Update)
- **Versioning Strategy**: Semantic Versioning (MAJOR / MINOR / PATCH)

---

## 🆕 What's New in v2.1.0

This version introduces significant stability improvements, batch processing capabilities, and advanced audio pre-processing.

### 🚀 Performance & Stability

* **Asynchronous Model Loading**: Introduced `ModelLoaderThread` to load Whisper models in the background, preventing UI freezes during startup or setting changes.
* **Memory Optimization**: Implemented aggressive garbage collection (`gc.collect()`) and CUDA cache clearing after processing to prevent Out-of-Memory (OOM) errors.
* **Defensive Programming**: Added safety checks (using `hasattr`) in `closeEvent` to ensure the application shuts down cleanly even if threads are in an inconsistent state.

### 🎙️ Audio Processing Enhancements

* **Real-Time Denoising**: Integrated `noisereduce` for spectral subtraction. Users can now toggle denoising to filter out background hums (like fans or AC) before VAD and transcription.
* **Volume Normalization**: Added a dynamic normalization layer that standardizes all audio to a user-defined target dBFS (default -20), ensuring consistent results for quiet or loud speakers.
* **Intelligent VAD Placement**: Denoising is performed *before* Voice Activity Detection (VAD) to improve speech detection accuracy in noisy environments.

### 🛠️ UI & Workflow

* **Batch Transcription**: Now supports multi-file selection with a dedicated queue system and progress bar.
* **Advanced Settings Container**: A new foldable UI section allows customization of `Beam Size`, `Initial Prompt`, `Language`, and `Compute Type` (float16/int8).
* **System Tray Integration**: The application can now minimize to the system tray, allowing long transcription tasks to run in the background without cluttering the taskbar.
* **Auto-Update Checker**: Integrated `UpdateCheckerThread` to notify users of new releases available on GitHub.
![alt text](./img/image-1.png)

---

## Feature Implementation Checklist

| Feature Category | Implementation Details |
| :--- | :--- |
| **Real-time Transcription** | Live microphone recording + streaming ASR via `faster-whisper`. |
| **Batch Transcription** | Import multiple audio/video files with queue scheduling and progress tracking. |
| **Real-Time Denoising** | `noisereduce` integration for spectral subtraction before ASR to ensure clean audio. |
| **Volume Normalization** | Dynamically standardizes imported and recorded audio to a target dBFS (e.g., -20 dBFS). |
| **Asynchronous Architecture** | `ModelLoaderThread` prevents UI freezing during initialization and compute-type switching. |
| **Advanced Memory Management** | Aggressive garbage collection (`gc.collect()`) and CUDA cache clearing to prevent OOM errors. |
| **System Tray Integration** | Minimizes to background (`QSystemTrayIcon`) for uninterrupted long-running transcription tasks. |
| **Auto-Update Checker** | Background thread automatically checks the GitHub API for new releases. |
| **Smart Splitting** | Uses silence detection to cut near natural pauses; auto-detects original bitrate to prevent file bloat. |
| **Modern Desktop UI** | PyQt6 tabs, live waveform visualization, and a foldable "Advanced Settings" container. |

---

## 1. Project Introduction

Taking meeting notes from long recordings is expensive and error-prone. **Project AURA** turns raw audio into structured artifacts with high efficiency.

AURA provides two UI tabs:

- **📝 Recording & Transcription**: Record mic audio, view live waveforms, process batches of files, and manage advanced model settings (Language, Beam Size, Target dBFS, Compute Type).
- **✂️ Smart Splitter**: Choose a file + output folder, pick a target length & tolerance, and export segmented chunks without cutting off sentences.

---

## 2. Repository Structure

```text
project_aura/
├── project_aura.py             # Main application (UI + ASR + VAD + Splitter + Threads)
├── project_aura_zh.py          # Support for traditional Mandarin UI
├── requirements.txt          # Python dependencies
└── README.md                 # This documentation

```

> Note: Large audio outputs, `temp_transcript.txt`, and temporary WAV files are intentionally excluded from Git tracking and are auto-cleaned by the application.

---

## 3. Environment Requirements

### 3.1 Recommended Runtime

* **OS**: Ubuntu 22.04 / 24.04 (Desktop)
* **Python**: 3.10+ (recommended 3.11)
* **GPU (Optional but recommended)**: NVIDIA CUDA-capable GPU for faster ASR

### 3.2 Core Python Dependencies

Install via `requirements.txt`:

* `faster-whisper` (ASR Engine)
* `pyaudio` + PulseAudio / ALSA (Audio input)
* `webrtcvad` (Speech detection)
* `pydub` (Audio loading/export & volume normalization)
* `pyqt6`, `pyqtgraph`, `qt-material` (UI & System Tray)
* `noisereduce`, `requests` (Denoising & Auto-updater)

---

## 4. Installation Steps

### 4.1 System Packages (Ubuntu)

```bash
sudo apt-get update

# Audio I/O (PyAudio)
sudo apt-get install -y portaudio19-dev python3-dev

# ffmpeg is required for pydub to read and process media formats
sudo apt-get install -y ffmpeg

```

### 4.2 Create a Virtual Environment (Recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

```

### 4.3 Install Python Dependencies

```bash
pip install -r requirements.txt

```

---

## 5. Execution Commands & UI Workflow

### 5.1 Run the App

```bash
python project_aura.py

```

### 5.2 Expected UI Workflow

**Tab 1 — Recording & Transcription**

1. **Async Loading**: Wait for the background `ModelLoaderThread` to initialize (UI remains responsive).
2. **Advanced Settings**: Click **▶ Show Advanced Settings** to adjust Target dBFS, Compute Type (`float16`/`int8`), Language, and toggle Real-time Denoise.
3. **Record**: Click **🎙️ Start Recording**. Waveform updates live. Minimize to System Tray if needed.
4. **Batch Import**: Click **📁 Import Audio/Video** to select multiple files. A progress bar will track the queue.
5. **Save**: Save transcripts via **💾 Save transcript (.txt)**.

**Tab 2 — Smart Splitter**

1. Select input file (mp3/wav/m4a/mp4/flac).
2. Select output folder.
3. Set target length (minutes) + tolerance.
4. Click **Start** to export intelligently split audio chunks.

---

## 6. Configuration (Key Defaults)

* **Sample Rate**: `16000`
* **VAD Level**: `3` (aggressive)
* **Target Volume**: `-20.0 dBFS` (dynamically standardizes loud/quiet speakers)
* **Model**: `SoybeanMilk/faster-whisper-Breeze-ASR-25`
* **Compute Type**: UI selectable (`float16` for GPU, `int8` for CPU)
* **Denoise**: Disabled by default (Enable in UI for noisy environments)

---

## 7. Troubleshooting

### 7.1 "Out of Memory" (OOM) Errors on GPU

If the app crashes or throws an OOM error during model load or batch processing:

* Open **Advanced Settings** and change Compute Type to `int8`.
* Ensure no other heavy VRAM applications are running.
* The app now includes aggressive GC and `torch.cuda.empty_cache()` to mitigate this between files.

### 7.2 File Bloat in Smart Splitter

If your exported files are larger than the original:

* The app now utilizes `mediainfo` to automatically detect and match the original bitrate instead of forcing 192k. Ensure `ffmpeg` is properly installed on your system.

### 7.3 Mic Device Issues (Linux)

* AURA prioritizes **PulseAudio** devices for automatic resampling. Confirm your system microphone works in system settings and that PulseAudio/PipeWire is active.

---

## 8. License

This project is licensed under the **MIT License**.

© 2026 Jason Chia-Sheng Lin (NYCU)
