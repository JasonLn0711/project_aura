# Project AURA: Ultimate Audio Assistant Refactor

![Status](https://img.shields.io/badge/Status-Refactor%20Baseline-blue?logo=github) ![CI](https://github.com/JasonLn0711/project_aura/actions/workflows/ci.yml/badge.svg) ![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) ![ASR Engine](https://img.shields.io/badge/ASR-faster--whisper-orange) ![UI](https://img.shields.io/badge/UI-PyQt6-9cf) ![VAD](https://img.shields.io/badge/VAD-WebRTC_VAD-success) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

Project AURA is a desktop audio assistant for real-time recording, Whisper-based transcription, batch file transcription, and smart audio splitting.

This repository is the clean Python refactor of the working `audio_assistant_v1.5.0.py` script from `record_audio_ubuntu`. It intentionally does **not** copy the recording archive, `.record/` virtual environment, temporary transcripts, or generated media files.

![Project AURA screenshot](./img/image.png)

## Project Status

The original `record_audio_ubuntu` folder mixed source code, runtime environment, and many generated recordings/transcripts. This sibling repository separates the maintainable application source from runtime data.

Use this repo for:

- source refactoring
- package structure
- tests and regression checks
- future Python releases

Keep historical recordings and generated transcripts in `record_audio_ubuntu` or another data folder.

The legacy one-file implementation is retained for audit and behavior comparison:

```text
docs/legacy_audio_assistant_v1.5.0.py
```

## Executive Summary

Project AURA integrates two core workflows:

1. **Real-time / file-based transcription** with timestamped logs.
2. **Smart audio splitting** that finds natural pause points to avoid cutting speech mid-sentence.

The app is designed for professional meeting and lecture workflows. It includes prompt-guided punctuation, optional background noise reduction, batch processing, and memory-management safeguards for heavier ASR workloads.

## Project Metadata

| Field | Value |
| --- | --- |
| Project Name | Project AURA / Ultimate Audio Assistant |
| Refactor Version | `1.8.0` |
| Current Release Tag | `v1.8.0` |
| ASR Model | `SoybeanMilk/faster-whisper-Breeze-ASR-25` |
| GitHub Repository | `JasonLn0711/project_aura` |
| Academic Affiliation | National Yang Ming Chiao Tung University (NYCU) |
| Project Lead | Jason Chia-Sheng Lin (PhD. Student) |
| License | MIT |

## Feature Implementation Checklist

| Feature Category | Implementation Details |
| --- | --- |
| Real-time Transcription | Live microphone recording plus streaming ASR via `faster-whisper`. |
| Batch Transcription | Import multiple audio/video files with queue scheduling and progress tracking. |
| Speaker Diarization | Optional imported-file speaker labeling through `pyannote.audio`, with configurable speaker-count bounds. |
| Real-time Denoising | Optional `noisereduce` processing before ASR for noisy environments. |
| Volume Normalization | Dynamically standardizes imported and recorded audio to a target dBFS, default `-20`, using a fast FFmpeg path when denoise is off. The FFmpeg path uses `CPU count - 6` worker threads, with a minimum of `1`, and reports clearly if CPU count cannot be detected. |
| Asynchronous Architecture | `ModelLoaderThread` prevents UI freezing during initialization and compute-type switching. |
| RTX/CUDA-only ASR | ASR model loading is pinned to `cuda`; CPU fallback is disabled so transcription never silently leaves the RTX GPU path. |
| System Tray Integration | Minimizes to background with `QSystemTrayIcon`. |
| Auto-update Checker | Background GitHub release check preserved from the original app. |
| Smart Splitting | Uses silence detection to cut near natural pauses and preserves original bitrate when possible. |
| Modern Desktop UI | PyQt6 tabs, live waveform visualization, and foldable Advanced Settings. |

![Project AURA batch UI](./img/image-1.png)

## What Changed In This Refactor

The original project used a monolithic script. This repo keeps the behavior but splits the code by responsibility:

```text
project_aura_refactor/
├── pyproject.toml
├── README.md
├── requirements.txt
├── docs/
│   ├── architecture_decisions.md
│   ├── denoise_upgrade_plan.md
│   ├── legacy_audio_assistant_v1.5.0.py
│   ├── refactor_plan.md
│   └── versioning.md
├── img/
│   ├── image.png
│   └── image-1.png
├── src/aura/
│   ├── app.py                    # QApplication entrypoint
│   ├── config.py                 # Runtime constants
│   ├── metadata.py               # Version and project metadata
│   ├── settings.py               # Testable runtime defaults
│   ├── asr/
│   │   ├── file_pipeline.py      # File prep, formatting, cancellation, and transcription services
│   │   └── threads.py            # Thin Qt wrappers for model loading, live ASR, batch file ASR
│   ├── audio/
│   │   ├── capture.py            # PyAudio/PulseAudio recording thread
│   │   ├── denoise.py            # Safe noisereduce wrapper
│   │   ├── export.py             # Recording normalization/export helpers
│   │   ├── splitter.py           # Thin Qt wrapper for smart audio splitting
│   │   └── splitter_pipeline.py  # Testable split-point detection and export service
│   ├── system/
│   │   ├── cuda.py               # CUDA runtime preload and required-library detection
│   │   ├── native_audio.py       # ALSA/JACK stderr suppression helpers
│   │   └── update_checker.py     # Background GitHub release check
│   └── ui/
│       ├── messages.py           # User-facing strings and dynamic UI message formatting
│       ├── main_window.py
│       ├── splitter_tab.py
│       └── transcription_tab.py
└── tests/
    ├── test_denoise.py
    └── test_prompt_defaults.py
```

## Fixed From The v1.5.0 Baseline

- Short live denoise buffers now use adaptive `n_fft`, `win_length`, and `hop_length`.
- Native JACK/PortAudio probe noise is suppressed during audio device initialization.
- The default prompt path is explicit and tested for both batch and live ASR.
- Runtime outputs are ignored without hiding source files.
- The app source is importable and testable as a package.
- File import transcription is extracted into a testable pipeline service outside the Qt thread.
- Smart audio splitting is extracted into a testable pipeline service outside the Qt thread.
- Runtime defaults and UI messages are centralized in testable modules.

## Environment Requirements

### Recommended Runtime

- OS: Ubuntu 22.04 / 24.04 desktop
- Python: 3.10+
- GPU: NVIDIA RTX / CUDA-capable GPU is required for ASR
- Audio stack: PulseAudio or PipeWire with PulseAudio compatibility

### System Packages

```bash
sudo apt-get update
sudo apt-get install -y portaudio19-dev python3-dev ffmpeg
```

`portaudio19-dev` and `python3-dev` are needed for PyAudio. `ffmpeg` is required by `pydub` for media import/export.

## Install

Use a fresh virtual environment in this repo:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

If you prefer the pinned legacy dependency list:

```bash
python -m pip install -r requirements.txt
```

Speaker diarization is optional because it adds heavyweight ML dependencies:

```bash
python -m pip install -e ".[diarization]"
export HUGGINGFACE_TOKEN=hf_your_token_here
```

Before using the default `pyannote/speaker-diarization-community-1` model, accept its Hugging Face terms for your account.

LLM summary is optional because it loads a local 9B model:

```bash
python -m pip install -e ".[summary]"
```

The default summary backend is `Qwen/Qwen3.5-9B` loaded with `bitsandbytes` int8 quantization on CUDA when available.

## Run

From this sibling repo:

```bash
python -m aura
```

or, after editable install:

```bash
aura
```

The packaged entrypoints are defined in `pyproject.toml`:

- `aura`
- `project-aura`

## UI Workflow

### Tab 1: Recording & Transcription

1. Wait for the background `ModelLoaderThread` to initialize the ASR model.
2. Open **Advanced Settings** to adjust target dBFS, compute type, beam size, language, initial prompt, denoise, optional speaker diarization, and optional LLM summary.
3. Click **Start Recording** for live recording and live transcription.
4. Click **Import Audio/Video** for batch transcription. Speaker diarization runs only on imported files when enabled.
   The import dialog lists common media containers including `mp3`, `mp4`, `m4a`, `wav`, `flac`, `mkv`, `mov`, `ogg`, `aac`, `wma`, `aiff`, `opus`, `webm`, `avi`, `m4v`, `3gp`, and `3g2`; the fallback **All Files** filter can still be used for other ffmpeg-supported media.
5. Enable **Summarize transcript after ASR** or click **Summarize Current Transcript** to append a local Qwen summary.
6. Click **Save Transcript** to write the transcript to disk, or **Clear Transcript** to clear the transcript pane and temporary backup after confirmation.

### Tab 2: Smart Splitter

1. Select source audio or video.
2. Select output folder.
3. Set target segment length and tolerance.
4. Start splitting to export chunks near natural pauses.

## Configuration Defaults

| Setting | Default |
| --- | --- |
| Sample Rate | `16000` |
| Chunk Size | `30 ms` / `480 samples` |
| VAD Level | `3` |
| ASR Model | `SoybeanMilk/faster-whisper-Breeze-ASR-25` |
| Device | `cuda` only; CPU fallback is disabled |
| Compute Type | `int8` on CUDA/RTX GPU by default |
| Target Volume | `-20 dBFS` |
| Denoise | Off in UI by default |
| Speaker Diarization | Off by default; imported-file range defaults to `2-6` speakers |
| LLM Summary | Off by default; `Qwen/Qwen3.5-9B` with int8 quantization when enabled |

## Runtime Files

Temporary transcription files are written outside the source tree by default:

```text
/tmp/project_aura/
```

Set `AURA_RUNTIME_DIR` to override this location:

```bash
export AURA_RUNTIME_DIR=/path/to/runtime
```

The runtime directory stores transient normalized WAV files and the live transcript backup. It is not intended for permanent recordings or final transcript exports.

## Default Prompt Behavior

The default file-transcription prompt is:

```text
這是一份專業的繁體中文會議紀錄，請務必根據語氣加上正確的全形標點符號。
```

It is loaded into the Advanced Settings prompt field at startup and is passed to both batch file transcription and live recording when recording starts.

The lower-level ASR threads also have explicit defaults:

- File transcription uses the Traditional Mandarin meeting-record prompt when no prompt is supplied.
- Live transcription uses `The following is a professional meeting record.` when no live prompt is supplied.
- If a caller explicitly passes an empty string, the app respects that as "no prompt".

## Speaker Diarization Behavior

Speaker diarization is an optional imported-file workflow. Live recording still uses the low-latency ASR queue without speaker labels.

When enabled in Advanced Settings, the file pipeline:

1. Decodes the source media with `pydub`.
2. Optionally applies the selected denoise preset.
3. Normalizes the file to the target dBFS and writes a temporary WAV under `AURA_RUNTIME_DIR`. The normal no-denoise path uses FFmpeg `volumedetect` plus `volume` filtering to avoid slow Python/pydub processing; FFmpeg is configured with `CPU count - 6` threads, with a minimum of `1`. CPU count detection tries `os.cpu_count()`, Linux CPU affinity, `nproc`, and `/proc/cpuinfo`; if all probes fail, the UI reports that CPU count is unavailable and uses one FFmpeg normalization thread. Denoise-enabled imports still use the Python audio path because denoise operates on an in-memory `AudioSegment`.
4. Runs `faster-whisper` transcription on that prepared WAV.
5. Runs `pyannote.audio` speaker diarization on the same prepared WAV.
6. Assigns each transcript segment to the speaker turn with the largest timestamp overlap.
7. Emits speaker-labeled lines such as:

```text
[00:01:12] SPEAKER_00: 今天先看這個案子。
[00:01:18] SPEAKER_01: 好，我補充一下背景。
```

The UI exposes a minimum and maximum speaker count. If both values are equal, AURA passes an exact `num_speakers` value to pyannote. If they differ, AURA passes `min_speakers` and `max_speakers`, which is safer when the meeting size is uncertain.

The default backend is `pyannote/speaker-diarization-community-1`. The implementation uses pyannote's exclusive diarization output when available because it is easier to reconcile with ASR timestamps.

Known limits:

- Speaker labels are anonymous (`SPEAKER_00`, `SPEAKER_01`) unless a future speaker-enrollment layer is added.
- Overlapped speech, far-field microphones, noisy rooms, and similar voices can still produce wrong labels.
- If `pyannote.audio` is not installed or no Hugging Face token is configured, imported-file transcription reports a clear setup error instead of failing silently.

## LLM Summary Behavior

LLM summary is an optional post-ASR workflow. It is intentionally separate from ASR so the app can still run on machines that do not have enough VRAM for a 9B model.

When enabled in Advanced Settings:

- imported-file transcription starts summary after each file's transcript is complete
- live recording schedules summary shortly after the user stops recording, giving the ASR queue a short drain window
- the **Summarize Current Transcript** button can run summary manually on the current transcript area

The default model is `Qwen/Qwen3.5-9B`. AURA loads it through `transformers` with `bitsandbytes` `load_in_8bit=True`, so the intended default is local CUDA int8 inference. Summary prompts require output in Taiwanese Traditional Chinese and ask for:

1. one-sentence summary
2. key points
3. decisions and consensus
4. action items with owner, task, and deadline when present
5. risks, questions, and follow-up items

If the optional summary dependencies are missing, the UI reports the install command instead of failing silently.

## Denoise Behavior

Live denoise is intentionally conservative and policy-driven:

- Denoise is represented internally as explicit presets: `off`, `light`, and `medium`.
- The Advanced Settings UI exposes these presets as a `Denoise Mode` combo box.
- Silent and near-silent buffers are returned unchanged.
- Very tiny buffers are skipped because spectral reduction has too little context.
- Non-silent `light` buffers use `noisereduce` in non-stationary mode with gentle reduction, `prop_decrease=0.35`.
- `medium` uses `prop_decrease=0.55`; it may affect speech detail more.
- FFT and hop sizes are capped dynamically so short live buffers cannot trigger `noverlap must be less than nperseg`.

For the model-based denoise roadmap, see `docs/denoise_upgrade_plan.md`. The short version is: keep `noisereduce` as the lightweight fallback, evaluate DeepFilterNet3 first for real-time ASR preprocessing, and evaluate ClearerVoice-Studio for offline imported-file enhancement.

On the current workstation using the legacy `.record` environment, rough timings were:

| Buffer | Approx. audio length | Runtime |
| --- | ---: | ---: |
| 480 samples | 30 ms | ~11 ms |
| 8,000 samples | 0.5 s | ~12 ms |
| 16,000 samples | 1.0 s | ~13 ms |
| 128,000 samples | 8.0 s | ~33 ms |

A synthetic 2-second noisy tone check improved estimated SNR by about `+0.43 dB` without NaN/Inf output. This is a smoke test, not a substitute for listening tests on real meeting audio.

## Test

The regression tests use the Python standard library:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

The repo also includes repeatable Make targets:

```bash
make check PYTHON=/path/to/python
make test PYTHON=/path/to/python
make compile PYTHON=/path/to/python
```

Current coverage includes:

- file transcription pipeline formatting, prep, cleanup, and cancellation behavior
- recording WAV-to-MP3 normalization/export behavior
- smart splitter extension handling, split-point selection, export, and progress callbacks
- multi-chunk splitter workflow behavior using synthetic audio
- runtime settings and UI message formatting defaults
- speaker diarization timestamp assignment and speaker-count argument handling
- LLM summary prompt and Qwen int8 default settings
- import smoke coverage for every `aura` package module
- short-buffer denoise stability
- denoise preset normalization and `off` bypass behavior
- silence denoise bypass
- synthetic signal preservation smoke check
- runtime temp path and backup cleanup behavior
- default prompt behavior for batch and live ASR
- transcribe keyword construction for language and prompt handling

GitHub Actions also runs compile and unit tests on pushes to `main`, `refactor/**`, and pull requests.

## Release Build

Build a source distribution and wheel from a clean checkout:

```bash
python -m pip install --upgrade build
python -m build
```

or use the repository command:

```bash
make build PYTHON=/path/to/python
```

Before tagging or publishing a release, run:

```bash
make check PYTHON=/path/to/python
```

Version bumps must follow the strict rule in [`docs/versioning.md`](docs/versioning.md). Use `make bump-version VERSION=X.Y.Z` to synchronize `pyproject.toml`, `src/aura/metadata.py`, and the README version rows in one dedicated version commit, then tag with the leading-`v` form such as `vX.Y.Z`.

## Troubleshooting

### GPU Out Of Memory

- Open Advanced Settings and keep Compute Type on `int8` for the default RTX GPU path.
- Close other GPU-heavy applications.
- The app releases model references, runs garbage collection, and clears CUDA cache during cleanup when PyTorch is available.

### CUDA Runtime Missing

The refactor keeps CUDA runtime preload logic in `src/aura/system/cuda.py`. If required CUDA libraries are unavailable, ASR model loading fails with a clear error. It does not fall back to CPU.

For `uv` installs on Linux x86_64, the project metadata includes NVIDIA cuBLAS
and cuDNN runtime wheels. Re-sync the environment after pulling this change:

```bash
uv sync
uv run aura
```

### JACK / ALSA Probe Noise

Linux audio backends can emit JACK/ALSA diagnostics even when the app uses PulseAudio successfully. The refactor suppresses native stderr during device probing and stream opening.

### Mic Device Issues

AURA prioritizes PulseAudio devices for automatic resampling. Confirm the microphone works in system settings and that PulseAudio/PipeWire is active.

### File Bloat In Smart Splitter

The splitter attempts to detect and reuse the original bitrate for MP3 export. Ensure `ffmpeg` is installed and visible on PATH.

## Migration Notes

- Do not copy `.record/`, generated recordings, transcripts, or split media into this repo.
- Keep large runtime outputs in `record_audio_ubuntu`, `outputs/`, or another data folder.
- Add only small, stable fixtures under `tests/fixtures/` when needed for regression tests.
- Use `docs/refactor_plan.md` for the next refactor phases.

## License

This project is licensed under the [MIT License](./LICENSE).

© 2026 Jason Chia-Sheng Lin (NYCU)
