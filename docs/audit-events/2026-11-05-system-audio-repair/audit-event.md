# GX10 system-audio ASR repair — November 5

## Source, contribution and adopted scope

The [preserved source](source.md) records Jason's failure report, confirmation
that he installed PortAudio, and correction to system audio only on GX10.
Jason selected the operating scope and requested recording and publication.
Codex repaired dependency readiness, source selection and diagnostics, then
validated the product path with public audio. This packet supports operator
handoff, project status and future incident diagnosis.

## FIRST PRINCIPLE routing

- Scarce resource: reliable recording, trustworthy evidence and maintenance attention.
- Canonical home: AURA owns implementation, dependency/runtime custody and detailed receipts.
- Planning role: day/project locator, status, capacity, publication and next gate.
- Evidence path: [public aggregate packet](../../../artifacts/asr-repair-2026-11-05/README.md);
  detailed host-local receipts remain under `runtime/asr-repair-2026-11-05/`.
- Scope control: fixed Breeze CUDA runtime with RE-USE and default-on Nemotron;
  system audio on GX10. Accuracy and latency remain `not_evaluated`.
- Next gate: Jason's next normal system-audio recording; capture any new failure
  by session ID. Physical microphone and second-host acceptance remain separate.

## Confirmed findings and implementation

The service responded, but its Nemotron environment was missing. GUI, capture
and punctuation dependencies were incomplete; Python capture also lacked the
system PortAudio library. Dependency synchronization restored the application
extras, then restored the reviewed native CTranslate2 CUDA 13 wheel. Nemotron's
isolated environment and pinned model cache were provisioned. PortAudio import
was independently verified after Jason's installation.

Linux exposed the HDMI output monitor and no microphone capture hardware.
The default combined source therefore required a device outside Jason's chosen
scope. The service now validates and persists `capture_source`; CLI recording
and scheduling use that preference when `--source` is omitted. Explicit source
selection wins. The GUI restores and saves its source choice. This host's
service and GUI choices are `system`; other installations keep the existing
combined-source fallback until configured.

PyAudio imports at device-open time, so missing PortAudio does not prevent the
capture module or Pulse capture path from loading. Device-open failures provide
an actionable dependency message. `/doctor` now retains server diarization
metadata and reports interpreter availability, explicitly distinguishing that
preflight check from real inference.

An idle `unloaded` state is supported: recording/import loads the model as
needed. Live checks verified explicit preload, worker reuse and unload with
worker exit. The repaired user service was left running with Breeze loaded.

## Validation and repository conditions

The [aggregate packet](../../../artifacts/asr-repair-2026-11-05/README.md)
separates direct import, controlled virtual capture and actual HDMI capture.
The final HDMI run used CLI `record` without `--source`, proving the saved
default through the real recording and export path. This is
`availability_validation` / `LIVE_MINIMUM_COMPLETED` / `valid_target_runtime`.

The supported-path suite passed 451 tests with ResourceWarnings treated as
errors. Full discovery ran 453 tests: 451 passed, one failed and one errored.
Both remaining outcomes are in the pre-existing untracked
`tests/test_raw_live_sessions.py`: it expects `enhancement.live_enabled` and
raw-ASR recovery without the live enhancement model. That draft conflicts with
the [adopted enhanced-audio contract](../../../README.md#nvidia-re-use-audio-processing)
and `tests/test_reuse_sessions.py`. It was preserved without publishing or
silently activating a different preprocessing architecture. Full discovery is
therefore **not green** in this host's draft-inclusive worktree.

Compilation and `git diff --check` passed. No ASR accuracy, timing, model ranking,
long-session acceptance or microphone result is claimed.

## Publication source selection

Fetched remote `9a912ca` selects the exact tracked tree of `7c496d6`; tree
comparison confirmed equality. Today's validated working branch instead starts
at `4e4772f`, with RE-USE, native capture and the supervised worker. Publishing
the current branch is an explicit new source selection: preserve the October 30
commit as a merge ancestor while retaining today's tested implementation.
The earlier snapshot remains recoverable by commit ID. No force push, release
tag, model weights, private recordings or runtime credentials are included.

Publication verified on November 5: repair `22cbca7`, preserved source
`066004c`, evidence/operator docs `dd6cf75`, and history-preserving merge
`27beec3` were pushed to `origin/main`. Fetch confirmed `HEAD...origin/main`
divergence `0 0`. The merge tree matches its first parent and retains remote
`9a912ca` as an ancestor, so it adds history without changing the tested tree.
This receipt is a subsequent documentation-only commit; the
[Planning day receipt](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W45/days/2026-11-05.md#aura-system-audio-publication-2026-11-05)
records the cross-repository publication result. No release tag was created.

## Connections and next action

- [Operator guide](../../shared-sessions-2026-09-08.md#saved-capture-source--november-5): source defaults, overrides and model lifecycle.
- [Nemotron contract](../../nemotron-diarization.md): isolated runtime and diarization boundaries.
- [Planning project](https://github.com/JasonLn0711/planning-everything-track/blob/main/data/projects/2026-05-project-aura-refactor.md#aura-system-audio-2026-11-05): current status and capacity.
- [November 5 day note](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W45/days/2026-11-05.md#aura-system-audio-2026-11-05): contribution and publication receipt.

Jason owns normal-use acceptance. Any raw-ASR research proposal requires its own
adoption and validation gate; the preserved draft does not change this repair's
operating contract or add a capacity commitment.
