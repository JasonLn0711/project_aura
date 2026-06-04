# Refactor Plan

## Decision

Use this sibling repository as the new maintainable Python codebase. Keep `record_audio_ubuntu` as the legacy working/data folder.

## Boundaries

- Do not import recordings, transcripts, `.record/`, or generated split files into this repo.
- Keep the one-file legacy implementation only as an audit baseline.
- Prefer package modules under `src/aura/` for all new work.

## Refactor Phases

1. Package split
   - Move system helpers, ASR threads, audio workers, and UI tabs into separate modules.
   - Keep behavior equivalent to `audio_assistant_v1.5.0.py`.

2. Regression tests
   - Cover denoise short-buffer handling.
   - Add splitter tests using tiny synthetic audio fixtures. Done; tests cover extension fallback, export format mapping, silence cut selection, final short-segment export, progress callbacks, and invalid target rejection.
   - Add import smoke tests for all modules. Done; `tests/test_imports.py` walks the `aura` package and imports each module.
   - File transcription pipeline tests now cover segment formatting, temp cleanup, cancellation, error guidance, and model kwargs.

3. Runtime hardening
   - Replace `terminate()` on file worker shutdown with cooperative cancellation. Done in `src/aura/asr/threads.py` and `src/aura/ui/transcription_tab.py`.
   - Move temp files into a configurable runtime directory. Done with `AURA_RUNTIME_DIR` support in `src/aura/system/runtime_paths.py`.
   - Add structured logging instead of `print()`. Done for current runtime diagnostics in `src/aura/app.py`, `src/aura/audio/capture.py`, `src/aura/asr/threads.py`, and `src/aura/ui/transcription_tab.py`.
   - Make denoise behavior policy-driven. Done with explicit `off`, `light`, and `medium` presets in `src/aura/audio/denoise.py`; Advanced Settings now exposes the presets through a `Denoise Mode` combo box.

4. Pipeline extraction
   - Extract file import/transcription logic from `FileTranscriberThread` into `src/aura/asr/file_pipeline.py`. Done; the Qt class now wraps the service and emits UI signals.
   - Extract recorded WAV normalization/export from the transcription UI into `src/aura/audio/export.py`. Done; tests cover output path, MP3 creation, and source WAV cleanup.
   - Extract smart audio splitting from `SmartSplitterThread` into `src/aura/audio/splitter_pipeline.py`. Done; the Qt class now delegates to the service and only emits UI signals.
   - Move GitHub release-check repository identity into config. Done with `GITHUB_REPOSITORY` and `latest_release_api_url()`.

5. UI cleanup
   - Move display strings into a localization layer. Started with `src/aura/ui/messages.py`; main window, transcription tab, and splitter tab now read user-facing labels/dialog text from `UIStrings`.
   - Keep English and Traditional Mandarin variants in one codebase instead of duplicate scripts.
   - Centralize runtime defaults. Done with `src/aura/settings.py`; ASR threads, file transcription defaults, and UI controls now use `AppSettings`.
   - Record first-principles ownership boundaries. Done in `docs/architecture_decisions.md`.

6. Packaging
   - Add release commands. Done with `Makefile` targets for `check`, `test`, `compile`, `build`, and `clean`, plus README release-build instructions.
   - Add CI checks for compile, tests, and formatting. Compile and unit-test CI is now in `.github/workflows/ci.yml`; formatting/linting can be added after adopting a formatter.
   - Add strict version-bump rules. Done in `docs/versioning.md`; tests now verify that `pyproject.toml`, `src/aura/metadata.py`, and the README refactor version stay synchronized.

7. Windows native RTX validation
   - Treat Windows native support as a first-class validation lane after the Ubuntu refactor baseline. Done; the durable record is tracked in `docs/windows_native_roadmap.md`, `docs/windows_setup.md`, and `docs/windows_known_issues.md`.
   - Start with `scripts/windows_gpu_smoke.py` and `scripts/runtime_report.py` so Windows CUDA activation can be proven before packaging work begins. Done; `scripts/windows_asr_artifact_smoke.py` also verifies CUDA/int8 ASR artifact output.
   - Move platform-specific CUDA, GPU, audio, FFmpeg, and dependency checks under `src/aura/system/` so UI and ASR code consume shared diagnostic results. Done with `platform.py`, `gpu_diagnostics.py`, `audio_diagnostics.py`, and `runtime_report.py`.
   - Keep CPU fallback disabled, but make runtime failures product-facing: the machine has not completed RTX/CUDA activation for AURA, and the diagnostic report should identify the missing layer. Done for ASR model loading and file transcription errors.
   - Add Windows hosted CI for non-GPU compatibility and a self-hosted Windows RTX runner for CUDA model-load and small-audio ASR smoke tests. Done; hosted Windows CI passed after adding FFmpeg setup, and the RTX lane is gated by `AURA_RUN_WINDOWS_RTX_SMOKE`.
   - Build the first Windows release as a portable developer artifact before evaluating PyInstaller, Nuitka, or a full installer. Done as `scripts/build_windows_portable.ps1`; `v1.13.0` strengthens this into a versioned portable ZIP layout.

8. Windows user onboarding
   - Reduce the Windows flow from developer commands to `Check-AURA.bat` and `Start-AURA.bat`. Done in `v1.13.0`; the PowerShell entrypoint creates `.venv`, installs dependencies, checks FFmpeg/NVIDIA, runs the GPU smoke test, writes `diagnostic_report.txt`, and launches the UI.
   - Keep check-only and launch flows on the same code path. Done with `Start-AURA.ps1 -CheckOnly`, used by `Check-AURA.ps1`.
   - Add UI-level First Launch Check gates while keeping readiness logic testable outside Qt. Done with `first_launch_checks()` in `src/aura/system/runtime_report.py` and display/actions in `src/aura/ui/transcription_tab.py`.
   - Package the onboarding flow as `dist/aura-windows-portable-vX.Y.Z.zip`. Done in `v1.13.0`; installer work remains a later validation layer.

9. Evidence-grounded meeting summary target
   - Treat `docs/meeting_summary_mvp_sdd.md` as the durable SDD for the current MVP: Graph Knowledge + RAG + INT8 SLM summary over ASR transcripts.
   - Keep `docs/meeting_summary_target_architecture.md` as the long-term architecture for the broader ASR Gate, evidence graph, graph-aware RAG, SLM, verifier, and evaluation path.
   - MVP-v0.1 input is ASR transcript; output is structured meeting summary. It excludes speaker diarization, ASR correction, full action-item ownership, multi-speaker role attribution, fine-tuning, medical/legal conclusion generation, and autonomous decision-making.
   - MVP-v0.1 compares six settings: Qwen 3.5 9B INT8 direct, vector RAG, graph RAG; and Gemma 4 E4B FP8 direct, vector RAG, graph RAG.
   - Start with time-based chunking plus sliding window chunking; leave semantic chunking for v0.2.
   - Use unsupported claim rate, evidence support rate, topic coverage, schema validity, decision capture accuracy, risk/constraint capture accuracy, open-question capture accuracy, human preference ranking, and human correction time as the first evaluation gates before PyQt UI integration.
