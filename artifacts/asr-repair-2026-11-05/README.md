# GX10 system-audio availability — November 5, 2026

Validation mode: `availability_validation`. Status: `LIVE_MINIMUM_COMPLETED`.
Runtime validity: `valid_target_runtime`. Functional result:
`available_and_working`. Accuracy and latency: `not_evaluated`.

The fixed product runtime was Breeze ASR 25 on NVIDIA GB10, native CTranslate2
4.7.1 and faster-whisper 1.2.1, requested CUDA `int8` with effective
`int8_float16`. This is functional availability evidence, without model ranking
or performance selection.

## Exercised paths

| Receipt | Real execution and persisted result |
| --- | --- |
| `direct-import` | Public Common Voice 24 zh-TW input; non-empty text, one segment and TXT/JSON export; diarization explicitly disabled |
| `combined-01` | Import, virtual Pulse capture through Rust, RE-USE, default-on Nemotron, pause/resume, Stop/export and refinement; four successful ASR jobs (two file, two chunk), one exported recording |
| `hdmi-01` | Actual default HDMI monitor with controlled public-audio playback; non-empty live text, one segment, TXT/JSON and one M4A export |
| `hdmi-default-02` | Actual HDMI monitor through CLI `record` without `--source`; saved `system` preference applied; non-empty live text, one segment, TXT/JSON and one M4A export |

The combined receipt confirms preload reused the worker and unload terminated
it, valid segment bounds, retained edits and exports. Both HDMI M4A files were
independently probed as AAC, 16 kHz mono. These paths exercised seven successful
ASR jobs in total and produced three exported recording files; exports are
recorded input audio, not synthesized speech.

## Evidence custody and checks

[Machine-readable aggregates](checks.json) retain hashes of the four original
receipts. Detailed authorized-input manifests, session IDs, transcripts, event
logs, request/error records and audio remain host-local under
`runtime/asr-repair-2026-11-05/`. This public packet contains no connection
credentials, private recordings, model weights or machine-specific user paths.

The supported-path regression command passed 451 tests with ResourceWarnings
treated as errors. Unfiltered discovery ran 453 tests with 451 passes, one
failure and one error in the preserved untracked raw-ASR draft. The
[audit event](../../docs/audit-events/2026-11-05-system-audio-repair/audit-event.md#validation-and-repository-conditions)
explains the contract conflict. Full draft-inclusive discovery is not green.
Compilation and `git diff --check` passed.

The repair, source, evidence and history integration were published as
`22cbca7`, `066004c`, `dd6cf75` and `27beec3`; the
[audit receipt](../../docs/audit-events/2026-11-05-system-audio-repair/audit-event.md#publication-source-selection)
records the fetched remote comparison and source-selection boundary.

## Decision and next gate

Production runtime remains Breeze with RE-USE and default-on Nemotron. GX10's
service and GUI capture choice is now `system`; the service was left running
with Breeze loaded. No new operational fallback or research candidate was
activated. The next gate is Jason's normal system-audio use. Physical microphone,
second-host, long-session, ASR quality and timing acceptance remain separate.

[Preserved source and repair decision](../../docs/audit-events/2026-11-05-system-audio-repair/source.md)
→ [implementation and ownership](../../docs/audit-events/2026-11-05-system-audio-repair/audit-event.md)
→ [operator entry point](../../docs/shared-sessions-2026-09-08.md#saved-capture-source--november-5)
→ [Planning day receipt](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W45/days/2026-11-05.md#aura-system-audio-2026-11-05).
