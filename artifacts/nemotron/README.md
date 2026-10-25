# Nemotron integration validation

Validated on 2026-10-25 in the project-owned Linux CUDA environment. Streaming
and complete-file runs are `LIVE_FULL_COMPLETED` with `valid_target_runtime`.
Both functional gates passed. The user service is active with
`nvidia/Nemotron-3-Diarization` enabled by default; explicit opt-out remains
available. No release, commit, or publication was performed.

## Runtime evidence

The same authorized 82.94-minute recording was used for both paths, with fixed
Breeze ASR. The source was decoded successfully before execution. Input and code
hashes are retained with each private receipt.

| Check | Measured result |
| --- | --- |
| Original-speed streaming | 165,888 submitted 30 ms frames; all 79,626,240 samples processed |
| Speaker-event continuity | 6,912 consecutive updates; no missing sequence |
| Speaker-update latency | p95 1.252 seconds; maximum 1.663 seconds; p95 <= 3 seconds gate passed |
| Streaming persistence | 581 transcript segments, 577 with speaker labels and four explicitly unknown; JSON export succeeded |
| Complete-file persistence | 1,295 labeled transcript segments, 1,593 saved speaker intervals; JSON export succeeded |
| Failure and recovery | Intentional worker termination preserved audio; restart recovery processed all 2,434,080 retained samples and preserved output (`LIVE_MINIMUM_COMPLETED`) |
| Regression checks | 362 tests passed with ResourceWarnings treated as errors |
| User service activation | Nemotron capability, enabled shared preference, isolated runtime, model cache, and CUDA readiness verified |

Latency is measured from the oldest submitted sample scored in each update to
receipt through the production SDK subscription. It includes buffering,
inference, and event delivery after preload. Silence and continuing speakers
remain in the measurements. The final transport frame is padded by less than
30 ms. Streaming ASR and diarization ran concurrently; the complete-file run
started after streaming finished.

The final streaming code snapshot differs only in the GUI status-label placement:
live speaker activity was moved outside the collapsed advanced settings panel.
That display change passed a separate offscreen GUI check. The complete-file
run used the final application snapshot. The source and inference implementation
were unchanged during the streaming run.

## Scope and reproducibility

Accuracy, diarization DER, ASR latency, and physical microphone acceptance are
`not_evaluated`. Label counts establish persisted output, not identity accuracy.
The measured latency applies to this source and host, not every deployment.

The [operating contract](../../docs/nemotron-diarization.md) defines installation,
pinned dependencies, migration, recovery, and the validation commands. Detailed
private receipts stay under `local_outputs/nemotron/2026-10-25/`, including
`experiment.json`, `stream-02/report.json`, `file-01/report.json`,
`stream-01/recovery-report.json`, and `activation.json`. Audio, transcript content,
exact source inventory, credentials, and per-frame logs are excluded from this
public packet. The deliberate failed attempt is retained separately from the
successful full-duration run.
