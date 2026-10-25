# Source ownership map

Generated from `source-map.json`; one canonical owner per source file.

| Source | C3 owner | Classification | Notes |
| --- | --- | --- | --- |
| [native/aura-capture/src/main.rs](../../../native/aura-capture/src/main.rs) | `captureTransport` | current | Capture, transport and completion share one Rust source file; transport is its canonical map owner. |
| [src/asr_postprocess/__init__.py](../../../src/asr_postprocess/__init__.py) | `postprocess` | current |  |
| [src/asr_postprocess/domain_glossary.yaml](../../../src/asr_postprocess/domain_glossary.yaml) | `postprocess` | current |  |
| [src/asr_postprocess/fuzzy_corrector.py](../../../src/asr_postprocess/fuzzy_corrector.py) | `postprocess` | current |  |
| [src/aura/__init__.py](../../../src/aura/__init__.py) | `commands` | current |  |
| [src/aura/__main__.py](../../../src/aura/__main__.py) | `commands` | current |  |
| [src/aura/app.py](../../../src/aura/app.py) | `guiControl` | current |  |
| [src/aura/asr/__init__.py](../../../src/aura/asr/__init__.py) | `asr` | current |  |
| [src/aura/asr/file_pipeline.py](../../../src/aura/asr/file_pipeline.py) | `filePipeline` | current |  |
| [src/aura/asr/hotwords.py](../../../src/aura/asr/hotwords.py) | `postprocess` | current |  |
| [src/aura/asr/models.py](../../../src/aura/asr/models.py) | `asr` | current |  |
| [src/aura/asr/punctuation.py](../../../src/aura/asr/punctuation.py) | `postprocess` | current |  |
| [src/aura/asr/threads.py](../../../src/aura/asr/threads.py) | `qtAdapters` | retained | Retained Qt ASR adapters; current service inference uses session_runtime.py. |
| [src/aura/audio/__init__.py](../../../src/aura/audio/__init__.py) | `media` | current |  |
| [src/aura/audio/capture.py](../../../src/aura/audio/capture.py) | `qtAdapters` | retained | Retained Qt recorder interface; current detached producer reads audio/inputs.py. |
| [src/aura/audio/cleanup.py](../../../src/aura/audio/cleanup.py) | `retention` | current |  |
| [src/aura/audio/denoise.py](../../../src/aura/audio/denoise.py) | `media` | evaluation | Historical noisereduce baseline; current RE-USE path does not select it. |
| [src/aura/audio/enhancement_backends.py](../../../src/aura/audio/enhancement_backends.py) | `media` | current |  |
| [src/aura/audio/enhancement_health.py](../../../src/aura/audio/enhancement_health.py) | `health` | current |  |
| [src/aura/audio/export.py](../../../src/aura/audio/export.py) | `retention` | current |  |
| [src/aura/audio/fastenhancer.py](../../../src/aura/audio/fastenhancer.py) | `media` | current |  |
| [src/aura/audio/inputs.py](../../../src/aura/audio/inputs.py) | `pythonIO` | current |  |
| [src/aura/audio/meeting_distance.py](../../../src/aura/audio/meeting_distance.py) | `media` | compatibility | Compatibility policy for saved/import settings; current enhancement stays fixed RE-USE. |
| [src/aura/audio/normalization.py](../../../src/aura/audio/normalization.py) | `media` | current |  |
| [src/aura/audio/recording_session.py](../../../src/aura/audio/recording_session.py) | `sessions` | current |  |
| [src/aura/audio/retention.py](../../../src/aura/audio/retention.py) | `retention` | current |  |
| [src/aura/audio/reuse.py](../../../src/aura/audio/reuse.py) | `reuseProtocol` | current |  |
| [src/aura/audio/reuse_model.py](../../../src/aura/audio/reuse_model.py) | `reuseModel` | current |  |
| [src/aura/audio/reuse_offline.py](../../../src/aura/audio/reuse_offline.py) | `offline` | current |  |
| [src/aura/audio/reuse_policy.py](../../../src/aura/audio/reuse_policy.py) | `guard` | current |  |
| [src/aura/audio/reuse_stream.py](../../../src/aura/audio/reuse_stream.py) | `stream` | current |  |
| [src/aura/audio/reuse_worker.py](../../../src/aura/audio/reuse_worker.py) | `reuseProtocol` | current |  |
| [src/aura/audio/splitter.py](../../../src/aura/audio/splitter.py) | `splitter` | current |  |
| [src/aura/audio/splitter_pipeline.py](../../../src/aura/audio/splitter_pipeline.py) | `splitter` | current |  |
| [src/aura/audio/vad.py](../../../src/aura/audio/vad.py) | `live` | current |  |
| [src/aura/audio/vad_candidates.py](../../../src/aura/audio/vad_candidates.py) | `live` | evaluation | Explicit evaluation adapters; not a default product VAD. |
| [src/aura/audit.py](../../../src/aura/audit.py) | `audit` | current |  |
| [src/aura/cli.py](../../../src/aura/cli.py) | `commands` | current |  |
| [src/aura/completion.py](../../../src/aura/completion.py) | `terminal` | current |  |
| [src/aura/config.py](../../../src/aura/config.py) | `scheduling` | current |  |
| [src/aura/diarization/__init__.py](../../../src/aura/diarization/__init__.py) | `diarization` | current |  |
| [src/aura/diarization/live.py](../../../src/aura/diarization/live.py) | `diarization` | current | Isolated Nemotron streaming and complete-file runtime. |
| [src/aura/diarization/nemotron.py](../../../src/aura/diarization/nemotron.py) | `diarization` | current | Isolated Nemotron streaming and complete-file runtime. |
| [src/aura/diarization/speaker_assignment.py](../../../src/aura/diarization/speaker_assignment.py) | `postprocess` | current |  |
| [src/aura/diarization/worker.py](../../../src/aura/diarization/worker.py) | `diarization` | current | Isolated Nemotron streaming and complete-file runtime. |
| [src/aura/evidence_search.py](../../../src/aura/evidence_search.py) | `evidenceIndex` | current |  |
| [src/aura/metadata.py](../../../src/aura/metadata.py) | `commands` | current |  |
| [src/aura/native_capture.py](../../../src/aura/native_capture.py) | `nativeLauncher` | current |  |
| [src/aura/producer.py](../../../src/aura/producer.py) | `pythonIO` | current |  |
| [src/aura/reuse_capture.py](../../../src/aura/reuse_capture.py) | `live` | current |  |
| [src/aura/reuse_live_repair.py](../../../src/aura/reuse_live_repair.py) | `repair` | current |  |
| [src/aura/reuse_recovery.py](../../../src/aura/reuse_recovery.py) | `repair` | current |  |
| [src/aura/review.py](../../../src/aura/review.py) | `review` | current |  |
| [src/aura/scheduling.py](../../../src/aura/scheduling.py) | `scheduling` | current |  |
| [src/aura/sdk.py](../../../src/aura/sdk.py) | `sdk` | current |  |
| [src/aura/service.py](../../../src/aura/service.py) | `transport` | current |  |
| [src/aura/session_core.py](../../../src/aura/session_core.py) | `sessions` | current |  |
| [src/aura/session_runtime.py](../../../src/aura/session_runtime.py) | `executor` | current |  |
| [src/aura/settings.py](../../../src/aura/settings.py) | `scheduling` | current |  |
| [src/aura/streaming.py](../../../src/aura/streaming.py) | `sessions` | current |  |
| [src/aura/system/__init__.py](../../../src/aura/system/__init__.py) | `diagnostics` | current |  |
| [src/aura/system/audio_diagnostics.py](../../../src/aura/system/audio_diagnostics.py) | `diagnostics` | current |  |
| [src/aura/system/cuda.py](../../../src/aura/system/cuda.py) | `diagnostics` | current |  |
| [src/aura/system/gpu_diagnostics.py](../../../src/aura/system/gpu_diagnostics.py) | `diagnostics` | current |  |
| [src/aura/system/native_audio.py](../../../src/aura/system/native_audio.py) | `diagnostics` | current |  |
| [src/aura/system/platform.py](../../../src/aura/system/platform.py) | `diagnostics` | current |  |
| [src/aura/system/runtime_paths.py](../../../src/aura/system/runtime_paths.py) | `diagnostics` | current |  |
| [src/aura/system/runtime_report.py](../../../src/aura/system/runtime_report.py) | `diagnostics` | current |  |
| [src/aura/system/update_checker.py](../../../src/aura/system/update_checker.py) | `diagnostics` | current |  |
| [src/aura/terminal.py](../../../src/aura/terminal.py) | `terminal` | current |  |
| [src/aura/ui/__init__.py](../../../src/aura/ui/__init__.py) | `guiControl` | current |  |
| [src/aura/ui/main_window.py](../../../src/aura/ui/main_window.py) | `guiControl` | current |  |
| [src/aura/ui/messages.py](../../../src/aura/ui/messages.py) | `guiControl` | current |  |
| [src/aura/ui/splitter_tab.py](../../../src/aura/ui/splitter_tab.py) | `splitter` | current |  |
| [src/aura/ui/transcript_io.py](../../../src/aura/ui/transcript_io.py) | `review` | current |  |
| [src/aura/ui/transcription_tab.py](../../../src/aura/ui/transcription_tab.py) | `guiControl` | current |  |
| [src/aura/worker.py](../../../src/aura/worker.py) | `scheduler` | current |  |
