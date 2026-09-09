# Parakeet short-tail recovery — 2026-09-09

Validation mode: `availability_validation`

Status: `LIVE_MINIMUM_COMPLETED`

Runtime validity: `valid_target_runtime`

Functional result: `available_and_working`

The operator authorized recovery of an existing failed recording and continuation
of capture after recoverable single-chunk output errors. Original audio, text,
session state and SQLite were backed up before mutation. Full evidence remains
owner-local under the application's `recovery-backups/2026-09-09-parakeet-short-tail/`.
This public summary contains aggregate results only.
[Verification JSON](verification.json) records counts and hashes of local receipts.

## Incident and repair

A 0.12-second live interval failed the adapter's segment-timestamp validation.
A subsequent capture rejection overwrote the visible cause. The stored event
history retained the original error, but not the actual invalid timestamp values.
There is no established OOM diagnosis.

Live recognition now requests text and uses durable capture sample coordinates.
File import/refinement retain model timestamps and strict validation. NeMo's
retained decoder setting is explicitly switched when changing paths. Known model
output errors create pending interval records; capture and subsequent chunks
continue. Unknown/runtime/storage failures still stop the session. Follow-on
capture errors preserve the first cause.

The first recovery attempt exposed an additional failure: WAV finalization removed
PCM journals still referenced by queued jobs. No successful chunk inference was
established by that attempt. Its failed receipt and database snapshot are retained.
The original PCM was restored from the pre-recovery backup and verified by hash.
The corrected finalization retains PCM for gaps/recovery; older finalized sessions
can read exact sample intervals from their mono 16-bit 16 kHz WAV instead.

## Verified outcome

- Two real Parakeet chunk inferences completed on the corrected recovery attempt.
- Original 54 segment records remained identical; final segment count is 56.
- Session returned to `ready`: 0 queued, 0 running, 0 failed jobs. The prior
  timestamp issue is retained with `status=resolved`.
- Recorded system, microphone and mixed PCM hashes match the original backup.
- One recovered mixed WAV and both current/recovered TXT exports were verified;
  WAV frame count matches preserved mixed PCM length.
- Other session rows and shared preference rows match the pre-recovery database.
- Runtime remains the pinned Parakeet v2 revision
  `ae9ad07059c7c739ffaf932226a8fe64ae2620b0`, NeMo 3.0.0,
  PyTorch 2.11.0+cu128, CUDA FP32, batch size 1.

The original source-end capture spool remains under local custody. Acceptance
covers audio saved into the session; it does not claim recovery of uncaptured
sound or establish transcript accuracy. No ground truth was read. Accuracy,
latency, throughput, VRAM ranking and precision/framework comparisons are
`not_evaluated`. No new model default or release tag was selected.

## Software acceptance

321 regression tests and the Linux PTY check passed. New checks cover the
120-ms text-only path, retained decoding-mode changes, strict file timestamps,
continued capture after a gap, fatal-error cause preservation, ordered and
idempotent recovery, manual-edit preservation, PCM retention and exact WAV reads.
The PTY uses synthetic ASR and exercises the recovery command with Tab completion;
it is separate from the two real inferences above.

See [operator recovery](../../docs/shared-sessions-2026-09-08.md#recover-transcription-gaps)
and [inference decision](../../docs/asr-inference-decision-2026-09-09.md).
