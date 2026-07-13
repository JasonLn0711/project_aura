# Architecture Decisions

## First-Principles Ownership Split

Project AURA is a desktop audio application, but its core value is not the UI framework. Its core value is reliable audio capture, preparation, transcription, splitting, and export.

Therefore, each layer has one owner:

- `src/aura/settings.py` owns runtime defaults that should be easy to inspect, override, and test.
- `src/aura/ui/messages.py` owns user-facing text and dynamic UI message formatting.
- `src/aura/asr/` owns transcription behavior and ASR worker orchestration.
- `src/aura/diarization/` owns optional speaker diarization backends and timestamp-based speaker assignment.
- `src/aura/llm/` owns optional local LLM post-processing such as transcript summaries.
- `src/aura/llm/` owns the supported local field-batch summary path; paired-corpus reports own claims about comparative model or retrieval quality.
- `src/aura/audio/` owns audio capture, denoise, export, and splitting behavior.
- `src/aura/scheduling.py` owns wall-clock scheduling calculations that can be tested without launching Qt.
- `src/aura/system/` owns platform/runtime concerns such as CUDA, native audio stderr, runtime paths, and update checks.
- `src/aura/ui/` owns widgets, signal wiring, and user interaction only.

The practical rule is: if a behavior can be tested without starting Qt, keep it outside `src/aura/ui/`.

## GPU-Only ASR Execution Contract

ASR owns one physical execution contract: inference runs on an activated GPU backend or the request stops at a clear activation gate. In AURA this means CUDA; `AppSettings`, model-loading threads, file and live transcription, GPU smoke checks, and ASR-backed evaluation entrypoints all preserve that requirement. A caller cannot request CPU ASR, and runtime failures remain visible instead of becoming slower CPU results.

The sibling Meetily product follows the same contract through platform GPU features: CUDA for the measured NVIDIA lane, Vulkan for the general Linux／Windows release lane, Metal for macOS, and CUDA Execution Provider for Parakeet. Backend selection is a release property with runtime verification. CPU／OpenBLAS ASR builds and ONNX CPU fallback are outside the supported architecture.

The evidence path is [`artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/`](../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/), with the complete event trail in [`docs/audit-events/2026-07-14-gpu-only-asr-live-benchmark/audit-event.md`](audit-events/2026-07-14-gpu-only-asr-live-benchmark/audit-event.md). A valid run records real audio, real inference output, backend identity, GPU-required marker, event timestamps, errors, GPU telemetry, latency, validity, and final decision. A model with an incompatible language contract remains `blocked_runtime`; another model's successful GPU run does not stand in for it.

## Current Refactor Direction

Keep extracting logic from UI classes into small service modules, then protect the service modules with fast synthetic-audio tests. This reduces the risk of changing the desktop UI while preserving behavior from the legacy one-file app.

The denoise policy is now explicit as presets: `off`, `light`, and `medium`. Advanced Settings exposes these as a `Denoise Mode` combo box while keeping `off` as the default.

Meeting distance is a higher-level capture-condition policy owned by `src/aura/audio/meeting_distance.py`. From first principles, distant speakers create low SNR and reverberation before ASR sees the signal, so the application needs a mode contract rather than a stronger global denoise default. Advanced Settings exposes `off`, `normal`, `far-speaker`, and `rescue-offline`. The mode supplies the minimum denoise floor, live VAD bridge/gate tuning, bounded live segment gain, backend-candidate metadata, and metrics fields. Optional imported-file DeepFilterNet3 and ClearVoice attempts belong in `src/aura/audio/enhancement_backends.py`, load heavy dependencies only when selected, and fall back to conservative `noisereduce` when unavailable. Because the current DeepFilterNet and ClearVoice packages depend on `numpy<2.0` while AURA uses `numpy>=2.0`, they stay outside the main dependency graph: DeepFilterNet through the external `deep-filter` CLI and ClearVoice through `AURA_CLEARVOICE_PYTHON`. WPE remains a later dereverberation validation layer until evaluation proves transcript-quality improvement.

Speaker diarization is an optional imported-file post-processing path. It intentionally stays outside the live recording loop, uses `pyannote.audio` behind an optional dependency boundary, and reconciles ASR segments with speaker turns by timestamp overlap.

LLM summary is also optional post-processing. It runs after ASR output exists, loads the Gemma 4 E4B FP8 summary backend through an optional dependency boundary, and forces summary prompts toward Taiwanese Traditional Chinese so summarization behavior is independent from the ASR language setting.

The supported summary path receives the corrected transcript, extracts nine fields through the approved local Gemma runner, validates the JSON contract, and renders Markdown deterministically. Comparative architectures activate after a measured gap and run real model inference on the same paired corpus. The retired deterministic Graph-RAG dry harness remains available in Git history as design provenance; it no longer occupies the active runtime or test surface.

Traditional Chinese punctuation restoration is a post-ASR readability layer, not an ASR decoding policy. From first principles, punctuation should improve the saved transcript without changing what the recognizer heard. Therefore `src/aura/asr/punctuation.py` owns Chinese-language/script detection, model-backed punctuation insertion, and deterministic fallback cleanup. File imports call it after ASR segments are collected and before diarization/formatting; live ASR calls it inside the transcriber thread; final recording save applies a no-model fallback so the UI thread never blocks on model download.

Domain glossary correction is a second post-ASR layer that runs at artifact-save time. The design keeps Breeze-ASR-25 output as `{base}_raw.txt`, writes `{base}_corrected.txt`, records accepted changes in `{base}_correction_log.json`, and uses the corrected transcript for final transcript and optional summary generation. The first implementation uses `rapidfuzz` with conservative category thresholds and `llm_verification: false`; it deliberately avoids natural-language rewriting and reserves LLM verification for a later gray-zone validation layer.

Transcript output is treated as a durable artifact set, not as UI text. From first principles, the user needs to know what was heard, what was summarized, where it was saved, and how long each stage took. Therefore:

- `src/aura/ui/transcript_io.py` owns raw/final/summary/metrics file naming and write behavior.
- `src/aura/asr/threads.py` records imported-file status events so FFmpeg normalization and ASR progress can be inspected after the run.
- `src/aura/ui/transcription_tab.py` owns interaction policy: auto-save after Stop Recording, clear the visible recording transcript after save, serialize batch summary/save before moving to the next import, expose Cancel Import, and show Open Output Folder only after an artifact exists.
- Advanced Settings owns output-location policy so transcript artifacts can stay beside the source/recording, go to a repo-local outputs folder, or go to a custom folder.

Live capture source selection belongs in `src/aura/audio/capture.py` because it is platform I/O, not ASR logic. The UI may request system-only, microphone-only, or system+microphone capture, but the capture layer owns PulseAudio/PipeWire source discovery, `parec` readers, PyAudio fallback, and mono mixing before VAD/ASR. Mixed live capture also performs RMS-based active-source balancing with limited gain and headroom so the microphone and system audio remain usable without amplifying silence or clipping speech.

The no-voice failsafe also belongs in `src/aura/audio/capture.py` because the capture loop is the only layer that sees every recorded frame and its voice/silence decision before WAV export. From first principles, a forgotten recording should stop because the audio stream has gone inactive, not because the UI guessed a duration. Therefore the recorder tracks continuous no-voice frames, auto-stops after 20 minutes, and trims the trailing no-voice frames before writing the WAV. The UI only reacts to the recorder thread finishing and then runs the normal ASR-drain, summary, and artifact-save flow.

Scheduled recording is an interaction policy, not a second recording pipeline. The UI owns arming/cancelling timers and disabling conflicting controls while a schedule is pending. `src/aura/scheduling.py` owns the testable wall-clock rules: start times resolve to the next matching `HH:mm`, and optional stop times must resolve strictly after the scheduled start, rolling to the next day when needed. When a timer fires, the UI calls the same live recording start/stop paths used by manual recording so transcript artifacts, summaries, normalization, and metrics stay consistent.

Windows native support follows the same ownership rule. Runtime diagnostics belong in `src/aura/system/` and scripts, while the UI displays summarized status, a runtime log, and copyable reports. The supported path is to prove RTX/CUDA activation first with `scripts/windows_gpu_smoke.py`, `scripts/runtime_report.py`, and `scripts/windows_asr_artifact_smoke.py`, then expose the same diagnostic facts in PyQt6. Platform-specific messages identify the missing activation layer for Linux native, WSL, Windows native, or Docker without allowing ASR to silently fall back to CPU.

Windows onboarding is a wrapper around the same validation path, not a second runtime. `Start-AURA.ps1` owns host setup orchestration for Python 3.11, `.venv`, dependencies, FFmpeg, NVIDIA driver visibility, GPU smoke checks, `diagnostic_report.txt`, and UI launch. `Check-AURA.ps1` reuses that path in check-only mode. The portable ZIP keeps the launch/check scripts at the archive root and keeps app source under `app/` so users can start from the folder root while the Python package remains editable and testable.

The Windows-friendly UI is a workstation surface, not a separate application. The transcription tab keeps the same PyQt6 code path while arranging the workflow as left-side commands, top runtime status, central transcript workspace, right-side artifact/export/summary/settings controls, and bottom runtime log. This keeps Windows usability improvements inside the existing tested workflow instead of creating a second UI stack.

First Launch Check status is derived from `src/aura/system/runtime_report.py`, not from duplicated UI logic. The UI maps those checks to status labels, Fix Guide buttons, setup-folder access, retry, and copy-report actions. This preserves the principle that testable readiness logic belongs outside Qt while the UI owns the user interaction.

The next high-value cleanup is to run the evaluation harness described in `docs/denoise_upgrade_plan.md` on a fixed private far-field clip set, then test DeepFilterNet3 and ClearVoice/ClearerVoice as optional model-based backends before promoting any new default.
