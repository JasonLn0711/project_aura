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

LLM summary is also optional post-processing. It runs after ASR output exists, uses the fixed local Ollama tag `gemma4:e4b-it-qat`, and enables reasoning on every `/api/chat` generation request (`reasoning=true`, Ollama `think=true`). The client requires a completed response and non-empty final `message.content`; `message.thinking` is optional model output and remains ephemeral whenever present. The canonical session stores only the validated final structured response and deterministic Markdown. Summary prompts target Taiwanese Traditional Chinese so summarization behavior is independent from the ASR language setting. The fixed `1536`-token generation budget preserves room for both reasoning and final structured output.

The supported summary path receives the corrected transcript, extracts nine fields through the approved local Gemma runner, validates the JSON contract, and renders Markdown deterministically. AURA parses the Ollama URL and accepts only HTTP on an exact loopback hostname with an explicit port and no credentials, path, query, or fragment. It starts Ollama with local-only, single-user GPU defaults: loopback binding, cloud access disabled, one server-side parallel sequence, Flash Attention enabled, and q8 KV cache. Comparative architectures activate after a measured gap and run real model inference on the same paired corpus. vLLM is an activation-gated candidate: implementation begins only when repeated same-corpus measurements show sustained concurrent demand or the Ollama runtime misses an agreed latency, queue-time, or throughput target. The retired deterministic Graph-RAG dry harness remains available in Git history as design provenance; it no longer occupies the active runtime or test surface.

## Evidence-first Session Contract

每場錄音或匯入工作由 `{base}_session/session.json` 提供唯一 `meeting_id` 與
artifact locator。錄音層先建立 session，轉錄、摘要與覆核層重用同一 identity；
選定的 Session Output 同時承載音訊、逐字稿與 evidence，避免同一場會議形成
彼此無法對應的資料島。

錄音 durability 由 `src/aura/audio/recording_session.py` 擁有。Capture loop
將 mixed 與本次 capture 實際可用的 system／microphone track 寫入 append-only PCM journal，依固定週期
flush 與 fsync，並以原子 `session.json` 更新形成 crash recovery 邊界。最終 WAV
只從 durable journal 重建；M4A／MP3 是交付格式，mixed WAV 保留為 evidence
source。啟動時的 discovery 是唯讀操作，恢復動作由使用者明確啟動；成功取回
原音後寫入 acknowledgement 與下一步，避免同一 session 重複出現在 recovery
清單。中斷狀態重建出的 WAV 維持 `recording_outcome=partial`，並保存原始
status／failure provenance；`ready` 表示音訊可供覆核，不代表錄音內容完整。
Custom output 可由使用者直接選取 `session.json`。

逐字稿有三個清楚狀態：`provisional`、`final`、`confirmed`。Live ASR 提供
provisional feedback，durable audio 的第二次 ASR 形成 final timestamps，
人員修字、改講者與確認形成 append-only review events。ASR log probability、
unknown speaker 與多講者時間重疊形成 review flags；它們是覆核排序訊號，
不是自動品質結論。

摘要層只接收同一份 prepared corrected transcript。Decision 與 action item
形成帶有 stable claim identity、source segment IDs、support status 與 review
status 的 evidence claims。人員確認、校訂與退回保存於 `review_events.jsonl`；
model output 保持不變。缺少來源或標記為 `unsupported` 的主張不能進入
confirmed action。逐字稿一旦修正，manifest 會先原子標記既有摘要為
invalidated，再保存 canonical segments 與 review events；任何後段寫入失敗都
維持 fail-closed evidence state。下一次摘要
會把 transcript hash 與來源 segment revision 納入 claim identity，使舊的人工
確認不會自動套用到新 evidence。

跨會議 retrieval 由 `src/aura/evidence_search.py` 擁有。Canonical files
仍是 source of truth；SQLite FTS5 index 可隨時原子重建，查詢連線使用
read-only mode。對外工具面目前只有 `search_meetings`、`search_segments`、
`open_audio_span` 與 `get_confirmed_actions` 等唯讀能力。Proposal connector、
MCP 與通用 Agent 由真實 consumer、反覆搬運 confirmed action 的 audit evidence
及逐項核准需求啟動。

SQLite rebuild 只接受明確的資料庫副檔名；既有 target 必須通過 AURA schema 與
`user_version` 驗證後才能原子替換。只有 meeting identity／transcript hash
一致且仍有效的摘要可進入 meeting search 與 actions；confirmed action 的每個
source segment ID 也必須存在於該 meeting 的 canonical `segments.json`。摘要、
逐字稿與覆核 event history 採用 temp file、flush、fsync 與 `os.replace`，讓
中斷或磁碟錯誤保留上一個完整版本。

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
