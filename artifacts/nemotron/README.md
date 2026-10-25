# Nemotron integration validation

Validated on 2026-10-25 in the project-owned Linux CUDA environment. Streaming
and complete-file runs are `LIVE_FULL_COMPLETED` with `valid_target_runtime`.
Both functional gates passed. The user service is active with
`nvidia/Nemotron-3-Diarization` enabled by default; explicit opt-out remains
available. The runtime receipt predates Git publication; publication integration is recorded
below. No release tag was created.

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

## Publication integration

The preserved pre-merge implementation is `116266c`; its evidence and operating
contract are `7c496d6`. Remote main through `afd8bb2` adds RE-USE capture, speech
protection, recovery and C4 documentation. Both histories are retained in the
publication merge. The 362-test and live latency results above describe the
pre-merge runtime. Combined-code regression and documentation checks are recorded
in the publication closeout; combined live RE-USE/Nemotron acceptance is pending.
The local activated service remains on the measured pre-merge snapshot.

[Source, ownership and next gate](../../docs/nemotron-diarization.md#source-and-adopted-scope--october-25)
connect this packet to the Planning day note and project locator.

### Combined-code checks

Publication merge `f49631f` passed 439 Python regression tests (including
native capture restart and original/enhanced PCM routing), nine versioning tests,
four Rust tests, compilation, and diff checks. The README's 67 relative links and
images resolve. Thirty C4 views cover 77 source files; Chromium navigation checks
passed. These checks establish integration behavior and documentation integrity;
they do not add a new GPU inference or microphone result.
