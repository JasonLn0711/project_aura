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
   - Treat Windows native support as a first-class validation lane after the Ubuntu refactor baseline. The detailed plan is tracked in `docs/windows_native_roadmap.md`.
   - Start with `scripts/windows_gpu_smoke.py` and `scripts/runtime_report.py` so Windows CUDA activation can be proven before packaging work begins.
   - Move platform-specific CUDA, GPU, audio, FFmpeg, and dependency checks under `src/aura/system/` so UI and ASR code consume shared diagnostic results.
   - Keep CPU fallback disabled, but make runtime failures product-facing: the machine has not completed RTX/CUDA activation for AURA, and the diagnostic report should identify the missing layer.
   - Add Windows hosted CI for non-GPU compatibility and a self-hosted Windows RTX runner for CUDA model-load and small-audio ASR smoke tests.
   - Build the first Windows release as a portable developer artifact before evaluating PyInstaller, Nuitka, or a full installer.
