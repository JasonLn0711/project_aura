# Linux native streaming validation — 2026-10-17

The final public-audio run completed on the ARM64 NVIDIA GB10 with Rust capture and Breeze GPU inference. The owning implementation is Project AURA; this packet records availability and a separate synthetic transport comparison. Changes are local and unpublished.

## Target runtime result

- Mode: `availability_validation`.
- Status: `LIVE_MINIMUM_COMPLETED`; runtime: `valid_target_runtime`.
- Canonical receipt: [GPU run 02](gpu-availability-r02/receipt.json). [Run 01](gpu-availability-r01/receipt.json) retains the earlier validation before final telemetry and recovery changes.
- One public audio file, one session, four completed GPU chunk jobs, zero failed jobs in the canonical run. These are single-session streaming results; no parallel or batch inference claim is made.
- Breeze used faster-whisper 1.2.1 and CTranslate2 4.7.1 on CUDA. Requested compute type was `int8`; the backend reported `int8_float16`.
- Public audio played into a dedicated virtual PulseAudio sink; Rust captured its monitor. Text appeared before capture ended. Pause/resume, preload reuse, explicit model unload, nonempty transcript, segment bounds, and M4A export passed.
- All 270 captured frames (129,600 samples at 16 kHz) reached the saved session. Monitor capture includes surrounding silence; it is not a byte-for-byte copy of the original file.
- Accuracy and ASR latency: `not_evaluated`. Ground truth was not read. Physical microphone, physical amd64 client, and second-host SSH acceptance remain `not_evaluated`.

The public input is [NVIDIA's example audio](https://dldata-public.s3.us-east-2.amazonaws.com/2086-149220-0033.wav). The receipt records original and decoded SHA-256 hashes. Detailed session output, transcript, audio, job requests and ordered events remain
owner-local under `gpu-availability-r02/`; the published receipt contains
aggregate evidence. Local connection credentials, SQLite state and native
spools are excluded from Git.

## Capture and transport comparison

[Transport run 02](capture-transport-r02/report.json) used 100 synthetic frames per backend and 100 ms emulated round-trip transport delay. Inference was a test double. [Run 01](capture-transport-r01/report.json) preserves the preceding measurement.

| Capture process | User CPU seconds | System CPU seconds | Peak RSS (KiB) | Peak pending frames | Accepted frames |
| --- | ---: | ---: | ---: | ---: | ---: |
| Python | 0.80 | 0.06 | 41,240 | 82 | 100 |
| Rust | 0.01 | 0.02 | 2,820 | 8 | 100 |

These process measurements cover one controlled workload per backend. They exclude model inference, the service process, and physical audio devices. They support the bounded upload and lightweight capture design for this workload; broader performance acceptance needs repeated representative runs.

## Regression evidence and next validation

The final suite passed 381 Python tests, including replay conflicts, offline stop/pause, native capture across service restart, retained-tail recovery, worker watchdog termination, and capture deadlines during blocked inference. Rust passed three unit tests, formatting, and Clippy with warnings denied. Five focused versioning tests and 19 base-client tests passed; package build and locked dependency checks passed. The terminal PTY smoke check passed after its stale help-text assertion was corrected. All 83 relative documentation links and image paths passed, as did `git diff --check`. The clean base-client import loaded none of Torch, NumPy, Qt, or faster-whisper.

See [validation metadata and source hashes](validation.json). Linux ARM64 and amd64 build/test jobs are configured in CI; they have not been executed by this local task. The native helper is installed in the local checkout's environment. The existing account service was preserved. Restart that service after its active work finishes to activate the updated server code.

The next acceptance gate is an actual amd64 Linux capture client connected to the DGX over SSH, including physical microphone selection and a network interruption. Real GPU inference during a service restart also remains a separate acceptance check; the current restart test uses synthetic inference. ASR quality and timing require separately activated evaluations.

## Subsequent field incidents and audit

This packet records the initial implementation and public/synthetic runs. Later
operator reports exposed additional service activation, device preflight, speech
detection, and empty-session recovery issues. The [complete October 17 audit](../../docs/audit-events/2026-10-17-live-streaming-reliability/audit-event.md)
preserves those failures, the fixes, the final 390-test result, and real Brave
playback verification. Its private evidence inventory also records intermediate
runs that completed technically but produced inadequate text. The source hashes
and 381-test count above remain the historical initial snapshot. The account
service was subsequently restarted during troubleshooting.
