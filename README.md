# Project AURA: Local Desktop Audio Assistant

![Status](https://img.shields.io/badge/Status-Maintained-brightgreen?logo=github) ![CI](https://github.com/JasonLn0711/project_aura/actions/workflows/ci.yml/badge.svg) ![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) ![ASR Engine](https://img.shields.io/badge/ASR-faster--whisper-orange) ![UI](https://img.shields.io/badge/UI-PyQt6-9cf) ![VAD](https://img.shields.io/badge/VAD-WebRTC_VAD-success) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

Project AURA is a desktop audio assistant for real-time recording, Whisper-based transcription, batch file transcription, and smart audio splitting.

This repository is the maintained Python implementation extracted from the original `record_audio_ubuntu` prototype. Git history preserves the retired one-file baseline; the current tree contains the active application, validation scripts, tests, and release documentation.

![Project AURA v1.14.0 live transcription workspace with CUDA status, waveform, Traditional Chinese transcript, and review controls](./img/transcription-workspace-v1.14.0.png)

*AURA v1.14.0 during live transcription: the operator workspace keeps capture,
runtime status, waveform, Traditional Chinese transcript, and review together,
with direct access to settings, track splitting, and the local activity log.*

## Project Status

Project AURA provides a fast validation surface for Taiwan-focused ASR, audio preparation, correction, observability, and evidence-backed capability comparison. Generated recordings and private transcripts stay in their selected output folders while the repo remains a reviewable source and validation package.

Use this repo for:

- maintained desktop application source
- package structure
- tests and regression checks
- Python validation releases
- paired-corpus evidence before capability migration into Meetily

Keep historical recordings and generated transcripts in `record_audio_ubuntu` or another data folder.

### CUDA-only ASR validation (2026-07-14)

ASR is a GPU-only capability. AURA accepts `cuda` and fails closed when CUDA is not ready; it never substitutes CPU inference. The paired live benchmark in [`artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/`](artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/) ran 20 real transcriptions over five public Common Voice 24 zh-TW clips: 10 with AURA Breeze ASR 25 on CUDA/int8 and 10 with Meetily Breeze ASR 26 on a CUDA release build. Both paths are `valid_target_runtime`, the error log is empty, and GPU telemetry is retained with the audio, requests, event traces, latency report, failure analysis, and decision report.

This clean-speech minimum validates the runtime contract rather than choosing a product winner. The next validation layer expands the same artifact contract to long-form, far-field, overlapping, and noisy speech, then compares correction effort, VRAM, cancellation, recovery, and completion time.

Audit trail: [`docs/audit-events/2026-07-14-gpu-only-asr-live-benchmark/audit-event.md`](docs/audit-events/2026-07-14-gpu-only-asr-live-benchmark/audit-event.md).

## Executive Summary

Project AURA integrates two core workflows:

1. **Real-time / file-based transcription** with timestamped logs.
2. **Smart audio splitting** that finds natural pause points to avoid cutting speech mid-sentence.

The app is designed for professional meeting and lecture workflows. It includes prompt-guided ASR, Traditional Chinese punctuation restoration, optional background noise reduction, batch processing, and memory-management safeguards for heavier ASR workloads.

## Project Metadata

| Field | Value |
| --- | --- |
| Project Name | Project AURA / Ultimate Audio Assistant |
| Refactor Version | `1.14.0` |
| Current Release Tag | `v1.14.0` |
| ASR Model | `SoybeanMilk/faster-whisper-Breeze-ASR-25` |
| GitHub Repository | `JasonLn0711/project_aura` |
| Academic Affiliation | National Yang Ming Chiao Tung University (NYCU) |
| Project Lead | Jason Chia-Sheng Lin (PhD. Student) |
| License | MIT |

## Latest Update — v1.14.0 (2026-07-14)

Project AURA v1.14.0 adds an operator-focused desktop workspace and a local,
content-free audit event system. The release makes recording, import, summary,
diagnostics, output review, and track splitting easier to operate while giving
maintainers enough trustworthy evidence to improve UI flow and investigate
runtime anomalies.

This release adds six durable capabilities:

1. **Operator workspace**: the PyQt layout now separates capture actions, live
   transcript review, output controls, Settings, runtime diagnostics,
   and the activity log into clearer working regions.
2. **Local product audit trail**: app lifecycle, decision-relevant UI actions,
   model loading, recording, import, summary, diagnostics, splitter, and audit
   report events are written to daily local JSONL files.
3. **Privacy and integrity controls**: audit details redact transcripts,
   summaries, audio, file paths, credentials, prompts, and raw error messages.
   Session sequence numbers and a SHA-256 hash chain support integrity review;
   audit files and generated reports use owner-only permissions.
4. **UI and reliability analysis**: local reports summarize workflow completion,
   recoverable friction, latency percentiles, repeated actions, error bursts,
   incomplete workflows, unknown schemas, and uncontrolled termination
   candidates. Every anomaly remains a human-review signal.
5. **In-app and CLI reporting**: Settings can open the local audit
   folder or generate a Markdown report; `scripts/summarize_audit_events.py`
   provides the same analysis in Markdown or JSON.
6. **Automatic version synchronization**: `make bump-version BUMP=patch|minor|major`
   calculates the next semantic version and synchronizes package metadata,
   runtime metadata, release date, README version rows, the latest-update
   heading, window title, audit events, runtime reports, and the bottom status
   bar from the same runtime version.

Validation passed `289` tests. The PyQt control smoke produced `8` ordered
events with integrity `PASS`; the updated desktop process subsequently wrote
`23` content-free runtime, UI, navigation, import, and summary events in one
active session with `0` provisional review signals. The next validation layer
confirms normal session termination and calibrates UI-friction thresholds after
at least `20` valid sessions or two weeks of local evidence.

Canonical design: [`docs/audit-event-system-design.md`](docs/audit-event-system-design.md).

## Previous Update (2026-06-11)

Project AURA now records each live recording as a reviewable execution package, not only as transcript text. The contribution in this update is operational observability: every recording folder now preserves both a raw runtime log and a structured event log, while live ASR exposes enough telemetry to distinguish normal verbose logging from real latency buildup. The recording audio export path now defaults to clearer M4A/AAC output while retaining MP3 as a legacy compatibility option.

This update adds five durable capabilities:

1. **Per-recording runtime logs**: each recording folder now includes `{base}_runtime.log`, a Python logging capture for that recording session. This preserves third-party logger lines such as `faster_whisper` processing-duration messages alongside AURA's own runtime events.
2. **Structured recording event logs**: each recording folder now includes `{base}_event_log.json`. The event log records UI status updates, live transcript updates, live ASR telemetry, recording start/stop events, final ASR drain, optional summary activity, save stages, and recording audio export start/finish/failure events.
3. **Live ASR telemetry**: every live ASR chunk reports `chunk_duration`, `queue_size`, `asr_elapsed`, `realtime_factor`, and `queue_backlog`. This makes it possible to tell whether AURA is merely producing normal logs or whether ASR is falling behind the capture queue.
4. **Live capture tuning for noisy environments**: the live maximum segment length is now configurable through settings and defaults to `16.0` seconds. The live energy gate is also settings-owned and defaults to `1000.0` RMS, so background system audio and room noise are less likely to force premature ASR segmentation.
5. **M4A/AAC recording export**: recorded WAV normalization now defaults to `M4A / AAC-LC 96k`, which preserves clearer meeting speech at practical file sizes. Advanced Settings can still select `MP3 / LAME VBR q0` for legacy workflows, and both paths apply the limiter after gain adjustment.

The supported scope is practical debugging and daily use. AURA now leaves enough evidence in the recording folder to inspect what happened after the meeting: which runtime settings were used, whether ASR queued up, whether recording audio export completed, where every artifact was written, and which stage consumed time. This is especially important for diagnosing live recordings that sound degraded, transcribe slowly, or produce many `faster_whisper` processing lines.

The recording artifact set now includes:

```text
{base}_raw.txt
{base}_corrected.txt
{base}_final.txt
{base}_summary.txt
{base}_correction_log.json
{base}_processing_metrics.json
{base}_event_log.json
{base}_runtime.log
```

The implementation is covered by focused tests for transcript artifact naming, event-log writing, structured live ASR telemetry, live segment/gate defaults, M4A/AAC recording export, MP3 legacy export, normalization limiter behavior, and import smoke coverage.

## Previous Update (2026-06-09)

Project AURA now has a more grounded daily meeting-summary path that turns the corrected transcript into structured meeting notes through the approved local Gemma 4 E4B Ollama runner. The 2026-06-09 correction removes the earlier Layer 1 / Layer 2 grouped prompts and runs the nine final summary fields as one parallel batch. The contribution is operational: **Summarize Current Transcript** no longer depends on one-shot free-form summary generation, grouped prompt examples, or a manually pre-started LLM runtime. It now runs nine field-level extractors in one parallel batch, validates every structured field in Python, writes local artifacts only to an ignored output directory, renders Markdown deterministically from the final JSON, and performs a local Ollama runtime preflight before any LLM call.

This update adds five durable capabilities:

1. **Parallel field-batch summary extraction**: `src/summary/layered_summary_pipeline.py` runs nine single-field extractors in one parallel batch: `meeting_topic`, `participants`, `executive_summary`, `key_points`, `decisions`, `action_items`, `open_questions`, `risks`, and `next_steps`. This removes the earlier Layer 1 / Layer 2 split, avoids a single oversized all-fields prompt, and reduces cross-field example leakage.
2. **Fixed local Gemma 4 E4B contract**: summary generation uses only the local Ollama tag `gemma4:e4b-it-q4_K_M` for base model `google/gemma-4-E4B-it`, with `temperature=0`, `num_ctx=32768`, and `stream=false`. AURA checks `http://localhost:11434/api/tags` before generation and refuses fallback models or cloud calls.
3. **Corrected-transcript-only input boundary**: the model receives only the current corrected transcript. Raw ASR text, `correction_log`, private audit logs, and review notes stay outside the prompt. This preserves the fuzzy-correction audit trail while keeping summary generation focused on the user-facing transcript.
4. **Structured JSON source of truth**: every extractor has its own prompt, minimal valid output example, strict JSON shape, Python validation, and one repair attempt. Python merges the validated outputs into the final schema, validates the full summary, and renders Markdown without using the LLM for formatting.
5. **Ollama runtime preflight and model-install guardrail**: `src/aura/llm/ollama_runtime.py` checks whether the local Ollama server is reachable, starts `ollama serve` when the server is unavailable, waits for `http://localhost:11434/api/tags`, verifies `gemma4:e4b-it-q4_K_M`, and separates missing-command, server-timeout, missing-model, pull-failure, and summary-failure states. If the model tag is missing, the UI shows a **Local Gemma model not installed** dialog with **Pull Model**, **Copy Command**, and **Cancel**. AURA never silently downloads a large model.

The practical workflow is now:

```text
Audio
↓
Breeze-ASR
↓
Raw Transcript
↓
Fuzzy Glossary Correction
↓
Corrected Transcript
↓
Local Gemma 4 E4B parallel field extraction
↓
Validated JSON
↓
Markdown meeting report
```

The supported scope is a local, user-facing meeting-notes feature. It does not create a new research gate, benchmark, or claim about summary quality. The next validation layer is real daily use: lab meetings, advisor syncs, industry discussions, and course recordings should produce paste-ready notes that are easy to inspect and revise.

The new runtime safety path is:

```text
Summarize Current Transcript
↓
Transcript content check
↓
Ollama localhost /api/tags preflight
↓
Start local ollama serve if needed
↓
Verify gemma4:e4b-it-q4_K_M
↓
If missing: Pull Model / Copy Command / Cancel
↓
Run field-batch summary only after the local runner is ready
```

The implementation is covered by focused runtime and UI-adjacent tests: `tests/test_ollama_runtime.py` validates server detection, command lookup, startup timeout, model-tag checks, pull success/failure, and localhost-only host policy; `tests/test_summary_ui_runtime.py` verifies that UI summary starts only after runtime-ready, model-missing does not call summary, and empty transcript does not start runtime.

## Previous Update (2026-05-29)

Project AURA `v1.13.0` is the Windows User Onboarding Release. The contribution in this update is user-facing: Windows users can now start from a portable folder, run one check, launch one script, and get a copyable diagnostic report when the machine is not ready. The implementation keeps the same RTX/CUDA-only ASR policy while reducing the setup flow from a developer command sequence to `Start-AURA.bat` / `Start-AURA.ps1` and `Check-AURA.bat`.

This release adds three onboarding layers:

1. **One-click Windows launch**: `Start-AURA.ps1` and `Start-AURA.bat` check Python 3.11, create `.venv`, install dependencies, verify FFmpeg, verify `nvidia-smi`, run `windows_gpu_smoke.py`, write `diagnostic_report.txt`, and then start the PyQt UI.
2. **Portable Windows ZIP layout**: `scripts/build_windows_portable.ps1` now produces `dist/aura-windows-portable-v1.13.0.zip` with root-level `Start-AURA.bat`, `Check-AURA.bat`, `app/`, `scripts/`, `docs/`, `sample_audio/`, and a placeholder `diagnostic_report.txt`.
3. **First Launch Check in the UI**: Runtime Diagnostics now includes GPU Ready, CUDA Ready, FFmpeg Ready, Microphone Ready, Output Folder, and ASR Model Load checks. Each failed item exposes Fix Guide, Copy Diagnostic Report, Open Setup Folder, and Retry Check actions beside the failed gate.

The supported scope is practical: the portable ZIP is the preferred Windows onboarding artifact before a full installer. CUDA, cuDNN, Qt plugin, and audio-device behavior still need repeated validation on real Windows RTX machines before moving to PyInstaller, Nuitka, or an installer.

## Previous Update (2026-05-29, v1.12.0)

Project AURA has moved from an Ubuntu-focused refactor into a cross-platform RTX workstation foundation. The contribution in this update is practical: AURA now has a Windows native validation path, a shared runtime diagnostics layer, a workstation-oriented PyQt layout, Windows CI coverage, and a portable developer release path. The evidence is concrete: the local CUDA smoke check loaded the default `SoybeanMilk/faster-whisper-Breeze-ASR-25` model on `cuda/int8`, the ASR artifact smoke wrote raw/final/metrics transcript outputs, and both Ubuntu and Windows GitHub Actions completed successfully after the hosted Windows runner was given FFmpeg.

This release adds four durable capabilities:

1. **Windows native RTX validation**: `scripts/windows_gpu_smoke.py` checks `nvidia-smi`, Python imports, CUDA runtime visibility, cuBLAS/cuDNN, `ctranslate2`, and the required `WhisperModel(..., device="cuda", compute_type="int8")` load path.
2. **Copyable runtime diagnostics**: `scripts/runtime_report.py` and the new `src/aura/system/` diagnostics modules report OS, Python, GPU, CUDA, cuBLAS, cuDNN, `ctranslate2`, `faster-whisper`, FFmpeg, audio devices, and output-folder writability.
3. **Windows-friendly workstation UI**: the transcription workspace now exposes left-side workflow commands, top GPU/model/device status, a central transcript workspace, right-side artifact/export/summary/settings controls, and a bottom runtime log. Runtime Diagnostics can copy the diagnostic report, and error dialogs expose the same report.
4. **Windows CI and portable release path**: `.github/workflows/windows.yml` runs hosted Windows tests, PyQt import smoke, runtime-report smoke, and portable packaging smoke. A gated self-hosted Windows RTX job can run both the GPU model-load smoke and the ASR artifact smoke. `scripts/build_windows_portable.ps1` prepares `dist/aura-windows-portable/` with setup docs, runtime checkers, known issues, and a generated sample WAV.

The supported scope is clear: hosted Windows CI verifies source compatibility and non-GPU runtime reporting; self-hosted RTX validation is the gate for CUDA performance claims. Installer work remains a planned extension after the portable developer release has been exercised on real Windows RTX hardware.

## Previous Update (2026-05-25)

The real problem in meeting transcription is rarely that a person does not know how to press a button. The problem is that humans are busy, meetings start while we are still switching context, and recordings often keep running long after the real conversation has ended. A transcription tool should protect attention instead of demanding more of it.

Before today, AURA already had the essential professional workflow: live recording, real-time ASR, optional summary generation, automatic transcript artifact saving, and an output folder policy. But it still depended on one fragile human habit: remember exactly when to start, and remember exactly when to stop.

Today we added two safety rails:

1. **Scheduled live recording**: AURA can now arm a recording for a specific wall-clock `HH:mm` start time, with an optional `HH:mm` auto-stop time. If the selected time has already passed today, AURA rolls it to the next matching time. If the stop time is earlier than the start time, AURA treats it as a next-day stop.
2. **No-voice failsafe**: if live capture detects no human voice for 20 continuous minutes, AURA automatically stops the recording and trims the final no-voice audio before exporting the selected recording format. This prevents forgotten recordings from turning into long silent files.

We compared four implementation paths before choosing this design:

- OS-level scheduling such as cron/systemd timers: powerful, but too detached from the desktop recording state and transcript artifact workflow.
- A UI-only countdown timer: simple, but it cannot know whether the room is still active or only silent.
- A fixed maximum recording duration: safe, but it can interrupt long lectures or research meetings at the worst moment.
- Capture-layer voice-aware stopping: slightly more work, but it uses the same live audio stream that drives ASR and can trim the saved audio at the exact place where useful speech ends.

The final decision is intentionally hybrid: wall-clock scheduling belongs in the PyQt interaction layer, while the 20-minute no-voice guard belongs in the audio capture layer. That keeps the feature predictable for the user and keeps the saved transcript/audio artifacts consistent with the same recording pipeline AURA already trusts.

## v1.13.0 Windows Onboarding Changes

`v1.13.0` turned the Windows native validation foundation into a simpler Windows onboarding path. Its goals were to let Windows users run one check and one launch command, keep ASR on the required RTX/CUDA path, produce `diagnostic_report.txt` automatically, package a real portable ZIP layout, and expose first-launch readiness checks in the UI.

### User Workflow Changes

- The primary transcription tab now uses a workstation layout: left-side workflow actions, top GPU/model/device status, central waveform/transcript workspace, right-side artifact/export/summary/settings controls, and a bottom runtime log.
- Windows users can now launch with `Start-AURA.bat` / `Start-AURA.ps1`, which prepares `.venv`, installs dependencies, checks FFmpeg and NVIDIA driver visibility, runs the CUDA smoke test, writes `diagnostic_report.txt`, and starts the app.
- Windows users can run `Check-AURA.bat` first to execute the same setup and RTX/CUDA validation flow without launching the UI.
- Runtime Diagnostics can be refreshed from the UI and copied as a developer-ready report.
- Runtime Diagnostics now includes a First Launch Check for GPU, CUDA, FFmpeg, microphone, output-folder writability, and ASR model load status, with Fix Guide buttons for failed gates.
- Error dialogs for model loading, file transcription, and summary failures expose the same diagnostic report through details and a copy button.
- The main transcription controls are simplified around the actual user actions: **Start/Stop Recording**, **Import Media**, optional **Cancel Import**, optional **Open Output Folder**, and **Summarize Current Transcript**.
- Live recording can be armed from Advanced Settings to start at a selected wall-clock time. The same schedule can optionally auto-stop at a selected wall-clock time, including next-day stop times when the end time is earlier than the start time.
- Live recording now has a 20-minute no-voice failsafe: if AURA does not detect human voice for 20 continuous minutes, it auto-stops and trims the trailing no-voice audio before saving the recording.
- The previous standalone **Save Transcript** and **Clear Transcript** buttons are removed from the primary workflow.
- After **Stop Recording**, AURA now waits for the live ASR queue to finish, runs the optional LLM summary if enabled, saves transcript artifacts automatically, clears the visible transcript pane, and removes the temporary transcript backup.
- After an auto-save, **Open Output Folder** becomes available so the user can inspect the generated files without searching manually.
- Import wording is shortened to **Import Media** because the import action already starts transcription automatically.
- The transcript field is now treated as a working display, not the user's permanent storage layer. The permanent record is the artifact set saved under the selected output policy.

### Transcript Artifact Changes

Transcripts are now saved as a durable artifact set instead of one manually saved text file:

```text
{base}_raw.txt
{base}_corrected.txt
{base}_final.txt
{base}_summary.txt
{base}_correction_log.json
{base}_processing_metrics.json
{base}_event_log.json
{base}_runtime.log
```

- `raw.txt` contains the ASR transcript only.
- `corrected.txt` contains conservative glossary-corrected ASR output.
- `final.txt` contains the corrected transcript plus the LLM summary when a summary is available.
- `summary.txt` contains only the LLM summary and is written only when a summary is produced.
- `correction_log.json` records each accepted fuzzy glossary correction.
- `processing_metrics.json` records the workflow type, source path, output policy, output paths, total elapsed time, coarse stage durations, runtime configuration, and status-event summary.
- `event_log.json` records structured per-run events. For live recordings, it includes runtime configuration, UI status updates, live transcript updates, ASR telemetry, recording start/stop events, final ASR drain, optional summary activity, save stages, and recording audio export status.
- `runtime.log` records raw Python logging for the recording session, including third-party logger lines such as `faster_whisper` processing-duration messages.

This split makes it possible to compare the original ASR output with the final user-facing transcript and audit where the file was saved.

### ASR Post-Processing

After Breeze-ASR-25 emits a transcript, AURA now runs a conservative domain-glossary fuzzy correction layer before summary generation. The glossary lives in [`config/domain_glossary.yaml`](config/domain_glossary.yaml), and the implementation is in [`src/asr_postprocess/fuzzy_corrector.py`](src/asr_postprocess/fuzzy_corrector.py).

The first version uses `rapidfuzz`, does not use LLM verification, and only corrects high-confidence glossary terms. It preserves `{base}_raw.txt`, writes `{base}_corrected.txt`, writes `{base}_correction_log.json`, and uses the corrected transcript for `{base}_final.txt` and downstream summary. The detailed policy and next validation path are recorded in [`docs/asr_postprocess_fuzzy_glossary.md`](docs/asr_postprocess_fuzzy_glossary.md).

### Import And Batch Processing Changes

- Imported audio/video files are processed as a queue.
- When **Summarize transcript after ASR** is enabled, each imported file now completes ASR, summary, and artifact saving before the next queued file begins.
- This prevents later batch files from skipping summary when a previous summary is still running.
- **Cancel Import** now clears the remaining queue and requests cancellation of the active import worker.
- Supported import formats include common audio/video containers such as `mp3`, `mp4`, `m4a`, `wav`, `flac`, `mkv`, `mov`, `ogg`, `aac`, `wma`, `aiff`, `opus`, `webm`, `avi`, `m4v`, `3gp`, and `3g2`, with an **All Files** fallback for other FFmpeg-supported media.
- Each imported file records status events in metrics, including preparation, normalization, ASR, optional punctuation restoration, optional diarization, optional summary, and artifact save stages.

### Live Capture And Audio Quality Changes

- Live recording can now request **System audio + microphone**, **System audio only**, or **Microphone only** from Advanced Settings.
- On PulseAudio/PipeWire systems, AURA uses `pactl` to discover the default sink monitor and default microphone source, then uses `parec` readers for precise source capture.
- When PulseAudio/PipeWire source discovery is unavailable, the app reports the fallback and records from the default PyAudio/Pulse input instead of failing silently.
- System-audio plus microphone capture is mixed before VAD/ASR as 16 kHz mono `int16` frames.
- Mixed live capture now applies RMS-based active-source balancing. Silent/background-only chunks are ignored, active sources receive limited gain, and mix headroom is preserved so microphone speech and system audio do not clip or drown each other out.
- Live ASR segmentation now uses a settings-owned maximum segment length, default `16.0` seconds, so long speech runs are less fragmented while still bounded for live feedback.
- The live energy gate is settings-owned and defaults to `1000.0` RMS. This raises the background-noise threshold from the earlier hard-coded value and makes future tuning easier without editing recorder internals.
- If no voice-like live audio is detected for 20 continuous minutes, the capture layer stops the recording and removes the final no-voice tail before the WAV is normalized/exported.
- The selected live capture mode is stored in recording metrics as `capture_source`.
- Recording audio export now defaults to `M4A / AAC-LC 96k`, with `MP3 / LAME VBR q0` available from Advanced Settings for legacy compatibility. Both export paths use the FFmpeg-first normalization path and apply a limiter after gain adjustment.

### ASR, GPU, And Readability Changes

- ASR model loading is pinned to `cuda`. CPU fallback is intentionally disabled so transcription never silently leaves the RTX GPU path.
- CUDA runtime/cuBLAS/cuDNN availability is checked before loading the ASR model; missing runtime libraries produce a product-facing RTX/CUDA activation error with platform-specific guidance for Windows native, WSL, Linux native, and Docker.
- Windows native feasibility is covered by `scripts/windows_gpu_smoke.py`, which verifies `nvidia-smi`, Python imports, CUDA DLL/runtime visibility, cuBLAS/cuDNN, and the actual `WhisperModel(..., device="cuda", compute_type="int8")` model-load path.
- `scripts/runtime_report.py` produces a copyable report covering OS, Python, GPU, CUDA, cuBLAS, cuDNN, `ctranslate2`, `faster-whisper`, FFmpeg, audio I/O, and output-folder writability.
- File ASR keeps the Traditional Mandarin meeting-record prompt by default; live ASR keeps a separate live prompt default.
- Traditional Chinese transcript text now runs through post-ASR punctuation restoration with the available `p208p2002/zh-wiki-punctuation-restore` token-classification model.
- If punctuation dependencies or model weights are unavailable, AURA uses deterministic full-width punctuation cleanup instead of blocking ASR or transcript saving.
- Punctuation restoration is conservative: it adds/normalizes punctuation for readability but does not translate Simplified Chinese, rewrite vocabulary, or replace the ASR text.

### Advanced Settings Changes

Advanced Settings now includes a transcript output policy:

- **Same folder as source/recording**: default; keeps imported transcripts beside the source file and live-recording transcripts in the recording folder.
- **Project outputs/transcripts folder**: writes transcript artifacts under `outputs/transcripts/` in this repo.
- **Custom folder**: writes all transcript artifacts to a user-selected folder.

Existing advanced options remain available: live capture source, denoise mode, speaker diarization, LLM summary, recording audio format, target volume normalization, beam size, initial prompt, language, compute precision, output policy, and model reload.

Runtime Diagnostics now appears alongside these controls. It reports GPU detection, CUDA runtime status, ASR model load status, audio input/output status, output-folder writability, and includes a **Copy Diagnostic Report** action.

The First Launch Check inside Runtime Diagnostics shows:

- **GPU Ready**
- **CUDA Ready**
- **FFmpeg Ready**
- **Microphone Ready**
- **Output Folder**
- **ASR Model Load**

Failed checks expose **Fix Guide**, **Copy Diagnostic Report**, **Open Setup Folder**, and **Retry Check** actions beside the failed gate so users do not need to interpret raw PowerShell output first.

Advanced Settings also includes scheduled live recording:

- **Schedule recording start** turns the main recording button into **Schedule Recording** and starts live recording/transcription at the selected `HH:mm` wall-clock time.
- **Auto-stop at** is optional. When enabled, AURA automatically stops the scheduled recording at the selected `HH:mm` wall-clock time and then uses the normal transcript finalization and artifact save workflow.
- If the selected start time has already passed for the day, AURA schedules the next matching wall-clock time. If the selected stop time is not after the scheduled start, AURA treats it as a next-day stop.

### Progress And Performance Visibility Changes

- Import normalization progress is surfaced in the status line, including CPU thread budget, FFmpeg volume-analysis pass, detected mean volume, gain amount, export progress percentage, and completion.
- Imported-file status events are retained in `processing_metrics.json`, so users can inspect what happened after the run finishes.
- Live ASR telemetry is emitted for each live chunk: `chunk_duration`, `queue_size`, `asr_elapsed`, `realtime_factor`, and `queue_backlog`. These fields identify whether live ASR is keeping up with capture or accumulating delay.
- Live recording folders now retain `{base}_event_log.json` for structured events and `{base}_runtime.log` for raw Python logging. The raw log captures `faster_whisper` processing lines, while the structured log keeps per-recording settings, transcript updates, status events, ASR telemetry, summary stages, save stages, and recording audio export outcomes.
- FFmpeg normalization uses a multi-core CPU policy of `CPU count - 6` threads, with a minimum of `1`.
- CPU count detection tries multiple probes and reports clearly if CPU count cannot be detected.
- ASR remains RTX/CUDA-only. CPU fallback is disabled so transcription never silently leaves the GPU path.
- Traditional Chinese transcripts now run through post-ASR punctuation restoration. When the optional punctuation dependencies and model are available, AURA uses a local Chinese punctuation model; otherwise it falls back to safe full-width punctuation normalization and sentence-final punctuation.
- The app surfaces long-running import stages through the status line instead of leaving the user unsure whether normalization or ASR is still running.

### Dependency And Optional Model Changes

- Core ASR dependencies stay in the base install.
- Speaker diarization remains an optional `diarization` extra because it pulls in `pyannote.audio` and PyTorch.
- LLM summary remains an optional `summary` extra because it loads a local 9B model.
- Traditional Chinese punctuation model support is available through the optional `punctuation` extra. Without it, the built-in rule fallback still improves saved Traditional Chinese transcripts.

### Documentation And Test Changes

- `docs/windows_setup.md` documents the Windows native setup path, including Python 3.11 venv creation, optional extras, GPU smoke testing, and app launch.
- `docs/windows_known_issues.md` records the current Windows CUDA/audio/packaging boundaries.
- Root-level `Start-AURA.ps1`, `Start-AURA.bat`, `Check-AURA.ps1`, and `Check-AURA.bat` provide the Windows onboarding entrypoints.
- `scripts/build_windows_portable.ps1` creates both `dist/aura-windows-portable/` and a versioned `dist/aura-windows-portable-v<version>.zip`, reading the release version from `pyproject.toml`, with the onboarding scripts at the archive root.
- `.github/workflows/windows.yml` adds hosted Windows checks for unit tests, PyQt import smoke, runtime-report smoke, and portable packaging smoke; the gated self-hosted RTX lane runs CUDA model-load and ASR artifact smoke tests.
- `scripts/windows_asr_artifact_smoke.py` generates a tiny WAV, runs a CUDA/int8 ASR pass, and verifies raw/final/metrics transcript artifact output.
- README workflow documentation now matches the simplified UI and automatic transcript-saving behavior.
- `docs/architecture_decisions.md` records the first-principles ownership split for transcript artifacts, output policy, progress visibility, UI interaction policy, live capture ownership, and Traditional Chinese punctuation post-processing.
- [`docs/first-principles-aura-meetily-review.md`](docs/first-principles-aura-meetily-review.md) records the 2026-07-13 cross-repo architecture review, completed simplification work, measured verification evidence, and activation gates for capability migration into Meetily.
- Tests now cover transcript artifact naming, raw/final/summary splitting, metrics JSON writing, event-log writing, structured live ASR telemetry, FFmpeg progress parsing, M4A/AAC recording export, MP3 legacy export, normalization limiter behavior, CPU-count detection, live capture source selection, RMS-based source mixing, live segment/gate defaults, scheduled wall-clock calculation, no-voice auto-stop/trailing-trim helpers, Traditional Chinese punctuation post-processing, runtime diagnostics reporting, first-launch check gates, and propagation of normalization progress into the import pipeline.

### Current Architecture Health

The project is still within a maintainable size for a desktop transcription tool, but three areas are now clear refactor candidates:

- `src/aura/ui/transcription_tab.py` should be split further because it still coordinates UI widgets, import queue state, recording session state, summary scheduling, metrics, and transcript saving.
- `src/aura/audio/capture.py` should eventually be split into PulseAudio/PipeWire source discovery, audio readers, source mixing, and recorder-thread orchestration.
- Windows audio should get a dedicated system module once real Windows RTX hardware confirms which microphone, system-audio, and loopback paths are stable.

The guiding rule remains: if behavior can be tested without launching Qt, it should live outside `src/aura/ui/`.

The supported meeting-summary path is the local Gemma field-batch pipeline documented below. Comparative retrieval architectures begin from a licensed paired corpus and measured correction-time or evidence-grounding gap; this keeps evaluation driven by a real product decision instead of a dry-run architecture scaffold.

## Windows Native Runtime Path

AURA now has a Windows native RTX validation and onboarding path. The supported direction is to prove the CUDA runtime and `faster-whisper` model load first, give users one-click check/start scripts, keep platform differences in shared diagnostics modules, and use the portable ZIP path before installer work.

The implementation and remaining validation path are tracked in [`docs/windows_native_roadmap.md`](docs/windows_native_roadmap.md), [`docs/windows_setup.md`](docs/windows_setup.md), and [`docs/windows_known_issues.md`](docs/windows_known_issues.md).

## Feature Implementation Checklist

| Feature Category | Implementation Details |
| --- | --- |
| Real-time Transcription | Live system-audio, microphone, or system+microphone recording plus streaming ASR via `faster-whisper`; stopping a recording waits for final ASR, auto-saves transcript artifacts, and clears the transcript pane. |
| Scheduled Live Recording | Optional wall-clock scheduled start for live recording/transcription, with optional wall-clock auto-stop and normal transcript artifact finalization. |
| No-Voice Failsafe | Automatically stops live recording after 20 continuous minutes without detected human voice and trims the trailing no-voice audio before export. |
| Batch Transcription | Import multiple audio/video files with queue scheduling, cancellation, serialized optional summaries, and progress tracking. |
| Transcript Artifacts | Auto-saves raw transcript, corrected/final transcript, optional summary, correction log, processing metrics, structured event log, and recording runtime log to the selected output policy. |
| Traditional Chinese Punctuation | Detects Traditional Chinese ASR output and restores readable full-width punctuation after ASR, using a local model when available and rule fallback when not. |
| System + Mic Capture | Uses PulseAudio/PipeWire monitor and microphone sources when available, mixes them to mono, balances active source RMS levels, and reports fallback behavior in the UI. |
| Speaker Diarization | Optional imported-file speaker labeling through `pyannote.audio`, with configurable speaker-count bounds. |
| Real-time Denoising | Optional `noisereduce` processing before ASR for noisy environments. |
| Volume Normalization | Dynamically standardizes imported and recorded audio to a target dBFS, default `-20`, using a fast FFmpeg path when denoise is off. Recorded audio defaults to `M4A / AAC-LC 96k`, with `MP3 / LAME VBR q0` retained as a legacy option; both use a limiter after gain adjustment. The FFmpeg path uses `CPU count - 6` worker threads, with a minimum of `1`, and reports clearly if CPU count cannot be detected. |
| Progress Telemetry | Surfaces import normalization and processing stages in the status line, stores imported-file status events in processing metrics, and records live ASR chunk telemetry for recordings. |
| Recording Observability | Writes `{base}_event_log.json` and `{base}_runtime.log` beside each recording so ASR latency, queue backlog, runtime settings, recording audio export status, and third-party logger output can be inspected after the run. |
| Local Product Audit | Writes content-free app/UI/workflow events to a local daily JSONL chain with redaction, retention, owner-only permissions, integrity verification, KPI/friction summaries, provisional anomaly signals, and in-app or CLI report generation. |
| Runtime Diagnostics | Reports GPU detection, CUDA runtime status, ASR model load status, FFmpeg, audio input/output devices, and output-folder writability through CLI scripts and the PyQt UI. |
| Windows Onboarding | Provides `Start-AURA.bat`, `Check-AURA.bat`, automatic `.venv` preparation, dependency installation, diagnostic report writing, and a versioned portable ZIP layout. |
| Windows Native Validation | Provides Windows setup docs, GPU smoke checks, runtime reports, hosted Windows CI, gated self-hosted RTX smoke tests, and a portable release builder. |
| Asynchronous Architecture | `ModelLoaderThread` prevents UI freezing during initialization and compute-type switching. |
| RTX/CUDA-only ASR | ASR model loading is pinned to `cuda`; CPU fallback is disabled so transcription never silently leaves the RTX GPU path. |
| System Tray Integration | Minimizes to background with `QSystemTrayIcon`. |
| Auto-update Checker | Background GitHub release check preserved from the original app. |
| Track Splitter | Uses silence detection to cut near natural pauses and preserves original bitrate when possible. |
| Modern Desktop UI | PyQt6 workstation layout with workflow actions, top runtime status, transcript workspace, output/review panel, foldable settings, live waveform visualization, and activity log. |

## What Changed In This Refactor

The original project used a monolithic script. This repo keeps the behavior but splits the code by responsibility:

```text
project_aura/
├── Check-AURA.bat
├── Check-AURA.ps1
├── Start-AURA.bat
├── Start-AURA.ps1
├── pyproject.toml
├── README.md
├── docs/
│   ├── architecture_decisions.md
│   ├── denoise_upgrade_plan.md
│   ├── first-principles-aura-meetily-review.md
│   ├── refactor_plan.md
│   ├── windows_known_issues.md
│   ├── windows_native_roadmap.md
│   ├── windows_setup.md
│   └── versioning.md
├── img/
│   ├── advanced-settings-v1.14.0.png
│   ├── track-splitter-v1.14.0.png
│   └── transcription-workspace-v1.14.0.png
├── src/aura/
│   ├── app.py                    # QApplication entrypoint
│   ├── config.py                 # Runtime constants
│   ├── metadata.py               # Version and project metadata
│   ├── settings.py               # Testable runtime defaults
│   ├── asr/
│   │   ├── file_pipeline.py      # File prep, formatting, cancellation, and transcription services
│   │   ├── punctuation.py        # Traditional Chinese punctuation restoration and fallback cleanup
│   │   └── threads.py            # Thin Qt wrappers for model loading, live ASR, batch file ASR
│   ├── audio/
│   │   ├── capture.py            # PyAudio/PulseAudio recording thread
│   │   ├── denoise.py            # Safe noisereduce wrapper
│   │   ├── export.py             # Recording normalization/export helpers
│   │   ├── normalization.py      # FFmpeg normalization, CPU-count detection, and progress parsing
│   │   ├── splitter.py           # Thin Qt wrapper for smart audio splitting
│   │   └── splitter_pipeline.py  # Testable split-point detection and export service
│   ├── llm/
│   │   ├── summary.py            # Optional local LLM summary service
│   │   └── threads.py            # Qt wrapper for summary generation
│   ├── system/
│   │   ├── audio_diagnostics.py  # FFmpeg/PyAudio input/output runtime report helpers
│   │   ├── cuda.py               # CUDA runtime preload and required-library detection
│   │   ├── gpu_diagnostics.py    # nvidia-smi, CUDA library, faster-whisper, and ctranslate2 checks
│   │   ├── native_audio.py       # ALSA/JACK stderr suppression helpers
│   │   ├── platform.py           # Linux/WSL/Windows/Docker environment classification
│   │   ├── runtime_paths.py      # Runtime temp paths and transcript backup helpers
│   │   ├── runtime_report.py     # Copyable developer-facing diagnostic report
│   │   └── update_checker.py     # Background GitHub release check
│   └── ui/
│       ├── messages.py           # User-facing strings and dynamic UI message formatting
│       ├── main_window.py
│       ├── splitter_tab.py
│       ├── transcript_io.py      # Transcript artifact writing helpers
│       └── transcription_tab.py
├── scripts/
│   ├── build_windows_portable.ps1
│   ├── check_windows_runtime.ps1
│   ├── run_aura_windows.ps1
│   ├── runtime_report.py
│   ├── windows_asr_artifact_smoke.py
│   └── windows_gpu_smoke.py
└── tests/
    ├── test_audio_capture.py
    ├── test_audio_normalization.py
    ├── test_file_pipeline.py
    ├── test_punctuation.py
    ├── test_transcript_io.py
    └── ...
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
- Runtime diagnostics are centralized in `src/aura/system/` so scripts, ASR error handling, and the UI share the same platform facts.
- Windows onboarding is now root-level and portable-friendly through `Check-AURA.bat`, `Start-AURA.bat`, automatic dependency preparation, and `diagnostic_report.txt`.
- Imported-file volume normalization uses an FFmpeg fast path when denoise is off.
- CPU count detection uses multiple probes and reports clearly when no CPU count can be detected.
- ASR is now explicitly RTX/CUDA-only; CPU fallback is treated as a configuration error.
- Windows native RTX validation now has CLI smoke tests, a setup document, hosted Windows CI, and a gated self-hosted RTX lane.
- Live capture can record system audio, microphone audio, or both when PulseAudio/PipeWire exposes the sources.
- System+microphone mixing balances active source RMS levels before VAD/ASR.
- Traditional Chinese punctuation restoration is extracted into a testable ASR post-processing module.

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
python -m pip install -e ".[punctuation]"
```

`pyproject.toml` is the single dependency contract for pip, uv, CI, and release builds.
This standard app profile activates both deterministic punctuation cleanup and the local
model-backed punctuation path. For a complete uv development environment, use one command:

```bash
make setup-dev
```

Speaker diarization is optional because it adds heavyweight ML dependencies:

```bash
python -m pip install -e ".[diarization]"
export HUGGINGFACE_TOKEN=hf_your_token_here
```

For local development, AURA also reads `/home/jnclaw/.codex/secrets/project-aura-hf.env`
when `HF_TOKEN` / `HUGGINGFACE_TOKEN` is not already set. This keeps `uv run aura`
usable without storing tokens in the repository.

Before using the default `pyannote/speaker-diarization-community-1` model, accept its Hugging Face terms for your account.

The daily meeting-summary path uses the local Ollama API and needs no additional
Python dependency group. The `summary` extra supports explicitly activated
Transformers evaluation scripts under `scripts/`.

The approved summary backend is the local Ollama tag `gemma4:e4b-it-q4_K_M`, corresponding to base model `google/gemma-4-E4B-it`. Before generation, AURA runs a local runtime preflight: it checks `http://localhost:11434/api/tags`, starts `ollama serve` if the local server is not already running, waits for the localhost runner to become ready, and verifies the exact model tag. If the model is missing, AURA shows a local-model dialog with **Pull Model**, **Copy Command**, and **Cancel** actions. Model download is never silent, no fallback model is used, and no cloud API is called.

Traditional Chinese punctuation restoration can use an optional local Hugging Face token-classification model:

```bash
python -m pip install -e ".[punctuation]"
```

With `uv`, install the same optional dependency group with:

```bash
make setup-app
```

`make setup-app` adds the standard punctuation profile without removing optional packages already
present in the environment. `make setup-dev` selects every declared extra for the complete
development/test feature set. Without the punctuation extra, AURA still applies safe Traditional
Chinese punctuation cleanup and reports the exact activation command in runtime diagnostics.

### Windows 3-Step Quick Start

For the Windows portable onboarding path:

1. Install or update the NVIDIA driver.
2. Unzip `aura-windows-portable-v<version>.zip`.
3. Double-click `Check-AURA.bat`, then double-click `Start-AURA.bat`.

`Check-AURA.bat` and `Start-AURA.bat` create `.venv`, install dependencies, check FFmpeg, check the NVIDIA driver, run the RTX/CUDA smoke path, and write `diagnostic_report.txt`.

For developer-level Windows RTX validation, follow [`docs/windows_setup.md`](docs/windows_setup.md), then run:

```powershell
nvidia-smi
python scripts/runtime_report.py
python scripts/windows_gpu_smoke.py
```

The smoke script checks `nvidia-smi`, Python imports for `faster_whisper` and `ctranslate2`, CUDA runtime DLL visibility, cuBLAS/cuDNN visibility, and the required `WhisperModel(..., device="cuda", compute_type="int8")` load path.

## Run

From the repository root:

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

### Tab 1: Transcription

1. Wait for the background `ModelLoaderThread` to initialize the ASR model.
2. Open **Settings** to adjust live capture source, target dBFS, compute type, beam size, language, initial prompt, denoise, optional speaker diarization, optional LLM summary, and transcript output location.
3. Click **Start Recording** for live recording and live transcription. The default live capture source tries to mix system audio and microphone audio through PulseAudio/PipeWire; Settings can switch to system-only or microphone-only capture.
4. Click **Import Media** for batch transcription. Speaker diarization runs only on imported files when enabled.
   The import dialog lists common media containers including `mp3`, `mp4`, `m4a`, `wav`, `flac`, `mkv`, `mov`, `ogg`, `aac`, `wma`, `aiff`, `opus`, `webm`, `avi`, `m4v`, `3gp`, and `3g2`; the fallback **All Files** filter can still be used for other ffmpeg-supported media. Each imported transcript is auto-saved according to the selected transcript output policy.
   Use **Cancel Import** to stop the active import when possible and skip the remaining queue.
5. Enable **Summarize transcript after ASR** or click **Summarize Transcript** to append a local Gemma 4 E4B summary.
6. Click **Stop Recording** to finish live recording. The app waits for final ASR text, runs glossary correction and optional summary if enabled, saves the transcript, metrics, event log, runtime log, and recording audio together, then clears the transcript pane and temporary backup.
7. Use **Open Output Folder** after an auto-save to inspect the generated transcript artifacts.

### Settings and Runtime Diagnostics

The scrollable **Settings** panel keeps audio preparation, speaker labeling,
scheduling, local summary, output policy, model controls, runtime diagnostics,
first-launch checks, and local audit actions in one operator surface.

![Project AURA v1.14.0 Settings panel with meeting-distance, denoise, speaker, capture, scheduling, summary, output, and recording controls](./img/advanced-settings-v1.14.0.png)

*Settings keep optional capabilities and output choices available without
competing with the primary recording and import actions.*

Runtime Diagnostics appears lower in the same panel. It reports GPU, CUDA,
model, FFmpeg, audio-device, and output-folder readiness, then provides a
First Launch Check and a focused **Fix Guide** for each activation gate.

### Transcript Output Policy

Settings exposes three output modes:

- **Same folder as source/recording**: default; imported-file artifacts stay beside the source media, and live-recording artifacts stay in the recording folder.
- **Project outputs/transcripts folder**: stores artifacts under `outputs/transcripts/` in this repo.
- **Custom folder**: stores all transcript artifacts in the selected folder.

For each transcript base name, AURA writes:

```text
{base}_raw.txt
{base}_corrected.txt
{base}_correction_log.json
{base}_final.txt
{base}_summary.txt                  # only when a summary is produced
{base}_processing_metrics.json
{base}_event_log.json
{base}_runtime.log                  # live recordings only
```

`final.txt` uses the corrected transcript plus optional summary. The metrics JSON includes output policy, source path, saved artifact paths, glossary correction status, total elapsed time, coarse stage durations, and imported-file status events such as FFmpeg normalization progress.

### Tab 2: Track Splitter

1. Select source audio or video.
2. Select output folder.
3. Set target segment length and tolerance.
4. Start splitting to export chunks near natural pauses.

![Project AURA v1.14.0 Track Splitter with target length, tolerance, source, output, progress, and processing details](./img/track-splitter-v1.14.0.png)

*Track Splitter presents the complete source-to-output sequence and keeps
progress and processing details visible during long media jobs.*

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
| Live Capture Source | System audio + microphone when PulseAudio/PipeWire exposes both sources; otherwise default input fallback |
| Meeting Distance Mode | Off by default; Settings can choose `normal`, `far-speaker`, or `rescue-offline` |
| Traditional Chinese Punctuation | Enabled; the `p208p2002/zh-wiki-punctuation-restore` token-classification model activates when the punctuation extra is installed |
| Denoise | Off in UI by default |
| Speaker Diarization | Off by default; imported-file range defaults to `2-6` speakers |
| LLM Summary | Off by default; local Ollama `gemma4:e4b-it-q4_K_M` parallel field-batch meeting summary extraction when enabled |

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

It is loaded into the Settings prompt field at startup and is passed to both batch file transcription and live recording when recording starts.

The lower-level ASR threads also have explicit defaults:

- File transcription uses the Traditional Mandarin meeting-record prompt when no prompt is supplied.
- Live transcription uses `The following is a professional meeting record.` when no live prompt is supplied.
- If a caller explicitly passes an empty string, the app respects that as "no prompt".

## Traditional Chinese Punctuation Behavior

Traditional Chinese punctuation is a post-ASR readability layer. AURA first keeps ASR on the required RTX/CUDA path, then checks the detected or selected language plus the transcript text. When the output looks like Traditional Chinese, it restores readable full-width punctuation before imported-file artifacts are saved and while live-recording segments are emitted.

The model-backed path uses `p208p2002/zh-wiki-punctuation-restore`, a Hugging Face `transformers` token-classification model that supports `，`, `、`, `。`, `？`, `！`, and `；` and includes a Traditional Chinese usage example. If `torch`/`transformers` or the model weights need activation, AURA keeps deterministic cleanup available: ASCII punctuation beside Chinese text is converted to full-width punctuation, duplicate punctuation is collapsed, spacing around Chinese punctuation is normalized, and a final `。` is added when a Chinese line has no terminal punctuation.

This post-processing is intentionally conservative: it does not translate Simplified Chinese into Traditional Chinese, rewrite words, or block transcript saving when the model cannot load.

## Speaker Diarization Behavior

Speaker diarization is an optional imported-file workflow. Live recording still uses the low-latency ASR queue without speaker labels.

When enabled in Settings, the file pipeline:

1. Decodes the source media with `pydub`.
2. Optionally applies the selected denoise preset.
3. Normalizes the file to the target dBFS and writes a temporary WAV under `AURA_RUNTIME_DIR`. The normal no-denoise path uses FFmpeg `volumedetect` plus `volume` filtering to avoid slow Python/pydub processing; FFmpeg is configured with `CPU count - 6` threads, with a minimum of `1`. CPU count detection tries `os.cpu_count()`, Linux CPU affinity, `nproc`, and `/proc/cpuinfo`; if all probes fail, the UI reports that CPU count is unavailable and uses one FFmpeg normalization thread. During import, the status line reports CPU budget, volume-analysis pass, detected mean volume, gain, export progress, and completion. Denoise-enabled imports still use the Python audio path because denoise operates on an in-memory `AudioSegment`.
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

LLM summary is an optional post-ASR workflow. It is intentionally separate from ASR so the app can still run transcription without the local Gemma 4 E4B Ollama runner.

When enabled in Settings:

- imported-file transcription starts summary after each file's transcript is complete and waits for that summary/save step before starting the next queued file
- live recording schedules summary shortly after the user stops recording, giving the ASR queue a short drain window
- the **Summarize Transcript** button can run summary manually on the current transcript area

The summary model contract is fixed:

- base model id: `google/gemma-4-E4B-it`
- Ollama model tag: `gemma4:e4b-it-q4_K_M`
- runner: `ollama`
- context window: `32768`
- external calls: `false`
- cloud calls: `false`
- fallback model: disabled

When **Summarize Transcript** runs, AURA uses the current corrected transcript only. It does not send the raw transcript, correction log, audit logs, or review notes to the model.

Before starting the LLM call, AURA performs a local Ollama preflight. If the localhost server is unavailable, AURA attempts to start `ollama serve` and waits for `http://localhost:11434/api/tags`. If the required `gemma4:e4b-it-q4_K_M` tag is missing, AURA asks before running `ollama pull gemma4:e4b-it-q4_K_M` or lets the user copy the command. Missing server, missing command, missing model tag, and pull failure are surfaced as separate runtime states.

Summary generation uses nine parallel single-field extractors instead of one-shot full-summary generation, two-layer grouped extraction, or 9 sequential field calls. AURA runs all nine field prompts in one parallel batch against the same corrected transcript, then merges and validates the final JSON in Python:

- Parallel batch: `meeting_topic`, `participants`, `executive_summary`, `key_points`, `decisions`, `action_items`, `open_questions`, `risks`, and `next_steps`.

Each extractor has a dedicated prompt, minimal valid output example, strict expected JSON shape, Python validation for each field, and one optional extractor-level format-repair attempt. Field types remain explicit:

- `meeting_topic`: string
- `participants`: list of strings
- `executive_summary`: string
- `key_points`: list of strings
- `decisions`: list of explicit decision objects
- `action_items`: list of task objects
- `open_questions`: list of strings
- `risks`: list of strings
- `next_steps`: list of strings

The final JSON is the source of truth. Markdown is rendered deterministically from that JSON, which keeps the report stable for Notion, GitHub, Google Docs, or email paste-in.

### Practical Meeting Summary Pipeline

For daily meeting notes, generate a Markdown report from the corrected transcript artifact:

```bash
PYTHONPATH=. uv run python scripts/generate_meeting_summary.py \
  --transcript path/to/meeting_corrected.txt \
  --output-md reports/meeting_summary.md \
  --output-json reports/meeting_summary.json
```

This practical pipeline uses only the corrected transcript as model input. It does not pass the correction log to Gemma, does not create research claims or benchmark metrics, and writes a paste-ready Markdown report with topic, participants, executive summary, key points, decisions, action items, open questions, risks, and next steps. Generated private outputs are written under ignored `local_outputs/meeting_summary/`; the public dry-run sample is stored at [`reports/sample_meeting_summary.md`](reports/sample_meeting_summary.md).

Summary evaluation uses the same corrected transcript, structured JSON schema, deterministic Markdown renderer, and field-level validation as the product path. New retrieval or model variants enter only through a paired benchmark with real inference outputs, source-linked evidence, failure records, and human correction-time results.

## Denoise Behavior

Live denoise is intentionally conservative and policy-driven:

- Settings includes `Meeting Distance Mode`: `off`, `normal`, `far-speaker`, and `rescue-offline`.
- `normal` applies at least `light` denoise for normal meeting-room audio.
- `far-speaker` applies at least `medium` denoise, uses a longer live VAD energy bridge, lowers the live energy gate for weak speech, applies bounded segment gain before live ASR, and attempts DeepFilterNet3 on imported files when the optional backend is installed.
- `rescue-offline` attempts ClearVoice/ClearerVoice enhancement for difficult imported recordings when the optional backend is installed; live recording still uses the conservative fallback path until transcript evaluation promotes a model backend.
- Denoise is represented internally as explicit presets: `off`, `light`, and `medium`.
- The Settings UI exposes these presets as a `Denoise Mode` combo box; meeting-distance mode provides the minimum safe denoise floor.
- Silent and near-silent buffers are returned unchanged.
- Very tiny buffers are skipped because spectral reduction has too little context.
- Non-silent `light` buffers use `noisereduce` in non-stationary mode with gentle reduction, `prop_decrease=0.35`.
- `medium` uses `prop_decrease=0.55`; it may affect speech detail more.
- FFT and hop sizes are capped dynamically so short live buffers cannot trigger `noverlap must be less than nperseg`.

For the model-based denoise roadmap, see `docs/denoise_upgrade_plan.md`. The short version is: keep `noisereduce` as the lightweight fallback, evaluate DeepFilterNet3 first for near-real-time far-speaker preprocessing, evaluate ClearVoice/ClearerVoice for offline rescue imports, and add WPE/dereverberation only after far-field transcript metrics justify it. The local comparison harness is `scripts/evaluate_denoise_backends.py`; DeepFilterNet is called through an external `deep-filter` CLI, and ClearVoice can run through `AURA_CLEARVOICE_PYTHON` with `scripts/run_clearvoice_enhancement.py`. The harness adds a recommendation table only for categories with reference-backed ASR metrics, so process-only runs do not change defaults.

To prepare the private fixed clip set:

```bash
python scripts/init_denoise_eval_workspace.py --input-dir ~/record_jn/aura_eval_audio
python scripts/discover_denoise_eval_candidates.py \
  --root ~/record_jn/record_audio_ubuntu \
  --output local_outputs/denoise_eval_candidates/candidates.md
python scripts/prepare_denoise_eval_case.py \
  --source /path/to/source_recording.wav \
  --case-dir ~/record_jn/aura_eval_audio/far_speaker_reverb \
  --start 120 \
  --duration 60 \
  --reference-file /path/to/trusted_reference.txt \
  --rare-term DeepFilterNet \
  --rare-term MossFormer
python scripts/check_denoise_eval_workspace.py \
  --input-dir ~/record_jn/aura_eval_audio \
  --min-cases 10 \
  --max-reference-chars-per-second 45
```

The discovery manifest lists transcript files only as review sources. A `reference.txt` should be a clip-level trusted transcript for the selected 30-90 second window, not an unreviewed full-recording transcript. The workspace checker rejects references that are implausibly long for the clip duration.

After generating an evaluation report, gate any default-promotion decision against reference-backed ASR metrics:

```bash
python scripts/gate_denoise_default_promotion.py \
  --report-json reports/denoise_eval_YYYYMMDD.json \
  --baseline off \
  --candidate deepfilternet3 \
  --min-cases 10
```

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
- runtime diagnostic report formatting, CUDA activation guidance, and preload status reconciliation
- recording M4A/AAC default export and MP3 legacy export behavior
- smart splitter extension handling, split-point selection, export, and progress callbacks
- multi-chunk splitter workflow behavior using synthetic audio
- runtime settings and UI message formatting defaults
- speaker diarization timestamp assignment and speaker-count argument handling
- LLM summary prompts and the local Gemma 4 E4B `q4_K_M` runtime contract
- import smoke coverage for every `aura` package module
- transcript artifact naming, final/raw/summary splitting, and metrics JSON writing
- live capture PulseAudio/PipeWire source parsing, source selection, and system+microphone RMS mixing
- imported-media FFmpeg normalization progress parsing and CPU thread-budget policy
- Traditional Chinese punctuation detection, model-label decoding, line-prefix preservation, and rule fallback
- RTX/CUDA-only model-loading policy and CUDA runtime error handling
- short-buffer denoise stability
- denoise preset normalization and `off` bypass behavior
- silence denoise bypass
- synthetic signal preservation smoke check
- runtime temp path and backup cleanup behavior
- default prompt behavior for batch and live ASR
- transcribe keyword construction for language and prompt handling
- Windows-hosted CI compatibility, including FFmpeg setup, PyQt import smoke, runtime report smoke, and portable packaging layout smoke

GitHub Actions runs Ubuntu compile/unit tests and Windows hosted checks on pushes to `main`, `refactor/**`, and pull requests. The Windows workflow also defines a gated self-hosted RTX job for `scripts/windows_gpu_smoke.py` and `scripts/windows_asr_artifact_smoke.py` when `AURA_RUN_WINDOWS_RTX_SMOKE=true`.

## Release Build

Build a source distribution and wheel from a clean checkout:

```bash
python -m pip install --upgrade build
python -m build
```

or use the repository command:

```bash
make build UV=/path/to/uv
```

Before tagging or publishing a release, run:

```bash
make check PYTHON=/path/to/python
```

Version bumps follow [`docs/versioning.md`](docs/versioning.md). Use
`make bump-version BUMP=patch|minor|major RELEASE_DATE=YYYY-MM-DD` to calculate
the next semantic version automatically, or provide `VERSION=X.Y.Z` explicitly.
The helper synchronizes package/runtime metadata and README release surfaces;
`make check` enforces the contract before tagging with `vX.Y.Z`.

This update uses `v1.14.0` because it adds the operator workspace, local audit
event system, integrity/privacy controls, UI and anomaly summaries, live audit
activation evidence, and automatic semantic-version synchronization. Package
metadata, runtime metadata, README release surfaces, and the application bottom
bar are synchronized for `2026-07-14`.

## Troubleshooting

### GPU Out Of Memory

- Open Settings and keep Compute Type on `int8` for the default RTX GPU path.
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

### System Audio + Microphone Capture

Live recording can mix the active output monitor source and the default microphone source through `pactl`/`parec`. On PipeWire/PulseAudio systems this usually means:

- system audio source: the default sink's `.monitor` source
- microphone source: the default non-monitor source

When both sources are active, AURA balances each 30 ms audio chunk before it reaches VAD/ASR. It measures each source's RMS level, ignores silent/background-only chunks, applies limited gain to bring active sources closer together, and keeps mix headroom so system audio and microphone speech do not clip or drown each other out.

If either source is not exposed, AURA reports the fallback in the status line and records from the default PyAudio/Pulse input. To diagnose source visibility manually:

```bash
pactl info
pactl list short sources
```

### File Bloat In Track Splitter

The splitter attempts to detect and reuse the original bitrate for MP3 export. Ensure `ffmpeg` is installed and visible on PATH.

## Repository Data Boundary

- Keep `.record/`, generated recordings, transcripts, split media, and other large runtime outputs in `record_audio_ubuntu`, `outputs/`, or another data folder.
- Version small, stable fixtures under `tests/fixtures/` when they support regression checks.
- Use `docs/refactor_plan.md` for the next architecture phase.

## License

This project is licensed under the [MIT License](./LICENSE).

© 2026 Jason Chia-Sheng Lin (NYCU)
