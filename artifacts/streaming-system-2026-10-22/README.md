# Streaming system optimization — 2026-10-22

> Historical evidence from the October 22 checkout. The code-linked receipts describe that run. The current branch is a source archive; it does not reproduce or activate the earlier runtime.

Study `STUDY-AURA-STREAMING-001`; experiment
`EXP-20261022-01-streaming-system`. Project AURA owns implementation and
evidence. The scarce resource is the GB10 CUDA host shared by live enhancement,
Breeze and bounded repair. Production activation is separate from successful
runtime execution.

## Runtime and measurement contract

The authorized private source is a 930.18-second recording, mono PCM16 at
16 kHz. The system runner uses the native capture producer with fixed
wall-clock frame deadlines; enhancement cannot pace the source. Breeze remains
fixed to zh, beam size 5, punctuation enabled, adaptive segments up to eight
seconds and 800 ms silence. Live ASR receives enhanced audio only. The adopted
live enhancer remains FP32, exit layer 8 and look-ahead 0.

Validation modes are `enhancement_streaming_validation` and
`streaming_system_validation`. The latter explicitly evaluates source-clock
delivery through the whole system, with a fixed ASR runtime; it is not an ASR
model benchmark. Source endpoints come from independent Silero VAD with an
RMS threshold of 80 and 800 ms silence. Each endpoint must fall inside a
displayed nonempty segment (30 ms boundary tolerance). Missing endpoints count
as infinite delay when computing P95; JSON represents a nonfinite P95 as null.
This tests segment coverage and delivery, not whether every spoken word is
correct. Accuracy and denoising quality remain `not_evaluated`.

Acceptance requires both CLI stdout and the actual offscreen Qt widget to
display 95% of endpoints within five seconds, enhancement lag P95 ≤1 second
and maximum ≤3 seconds. The Qt test exercises production polling and rendering;
it does not establish physical display or human UX acceptance. The 30-minute
soak is gated on the preceding full-recording acceptance.

## Implemented changes

The opt-in `stream-v2` implementation preloads and warms the live worker,
groups up to four available capture frames, retains chronological model state,
and eliminates per-spectrum diagnostic synchronization. Capture packets keep
their durable-ACK barrier. Enhanced output uses bounded group checkpoints
with forced durability before ASR reads. The consumer retains its source file
handle, reuses the warmed worker across pause, and computes enhanced VAD
outside the session lock. Primary jobs precede repair jobs; repair checks
backlog before model allocation. CLI and GUI distinguish audio delivery from
pending transcript intervals and expose lag and repair waiting reasons.

The [implementation contract](../../docs/architecture/reuse-c4.md#opt-in-streaming-implementation)
describes ownership, persistence and rollback. The new environment variable is
read when the service starts and frozen into each new session. The service
default remains `legacy-v1`; no account-service restart, release, commit or
publication is part of this validation.

## Initial live evidence

The 60-second paired enhancement run produced 960,000 samples per variant with
identical PCM16 SHA-256 and diagnostic counters. Both produced output before
input EOF. Processing took 70.899 seconds for legacy and 43.836 seconds for
stream-v2. These are single-run processing intervals: stream-v2 warms before
the interval, while legacy incurs first-call initialization inside it. They
are not a steady-state speedup estimate. This pair exercises continuous
enhancement without the service's health-triggered resets; it does not prove
whole-pipeline waveform equivalence when reset timing differs by packet size.

The initial 60-second system run completed live execution and M4A delivery but
failed acceptance: enhancement lag P95 2.25 seconds, maximum 2.49 seconds, and
11 of 12 source endpoints missing from both displays. The first displayed
endpoint arrived after 6.994 seconds in CLI and 7.182 seconds in Qt. A CPU
regression suite overlapped this exploratory run; it is not the isolated final
acceptance measurement. Startup and raw-checkpoint improvements followed it.

A separate 1.2-second CPU/CUDA profile completed. Matrix multiplication,
convolution and recurrent model operations dominate the captured device work;
the trace also contains substantial CPU dispatch activity. Profiling overhead
precludes using this run for acceptance timing. No missing upstream input
normalization was found in the pinned streaming adapter.

## Full-recording acceptance

The 930.18-second system run is `LIVE_FULL_COMPLETED`, classified
`valid_target_runtime`, with `gate_outcome=fail`. It delivered M4A and retained
audio for unresolved transcript intervals. Capture and live ASR drain completed
before regression and architecture workloads began during offline export.

| Measure | Observed result | Acceptance |
| --- | --- | --- |
| Enhancement lag P95 | 19.86 seconds | ≤1 second |
| Enhancement lag maximum | 20.91 seconds | ≤3 seconds |
| CLI endpoints displayed within five seconds | 2 / 78 | At least 95% |
| Qt endpoints displayed within five seconds | 2 / 78 | At least 95% |
| Missing endpoints in each display | 38 / 78 | Included as failures |
| M4A delivery | Successful | Functional export |
| Pending intervals after delivery | 34 | Preserve source and review status |

The final health state was `healthy`, after 33 resets, while historical gaps
remained pending. A healthy current frame does not resolve earlier missing
speech. Endpoint P95 is nonfinite because missing endpoints remain in the
denominator. These results establish a delivery and signal-availability
failure, not a measured word-error rate.

The worker round-trip stage took 851.21 seconds across 7,753 calls; enhanced
fsync took 2.33 seconds and session-lock wait took 1.83 seconds. These cumulative
stages are not mutually exclusive and should not be summed as wall time.
The worker round-trip stage dominated live consumer time. The sampled profile
and stage totals support further work on recurrent inference and dispatch;
they do not establish an omitted normalization step or a storage bottleneck.
The 30-minute soak was not started because full-recording acceptance failed.
The service default remains `legacy-v1`, and stream-v2 remains opt-in.

## Research candidates and next gate

The layer-6 FP32 probe completed 60 seconds of source audio in 39.140 seconds
of processing and preserved all 960,000 samples. Nonfinal enhanced output
arrived before source EOF.
Its signal check flagged 961 of 1,251 source-voiced 30 ms frames as suppressed
(output RMS below 8 and below 1% of source RMS). It remains a research candidate;
processing speed alone does not qualify it for adoption. Accuracy and denoising
quality were not evaluated.

The layer-8 BF16 attempt is `BLOCKED_UNRESOLVED` / `blocked_runtime`: warmup
failed on a convolution state/input dtype mismatch before a streaming output
file was produced. The [blocked-candidate report](blocked_unresolved_report.md)
preserves the exact error and the validation needed to revisit it. This does
not establish that GB10 hardware lacks BF16 support.

The [sanitized results](results.json) seal private receipt hashes, runtime/code
identity, output hashes, stage totals, gates and live counts. Legacy contributes
one `valid_baseline` run and one primary generated audio file. Adopted-setting
stream-v2 contributes four `valid_target_runtime` runs and six primary output
files; layer-6 FP32 contributes one run and one output file. BF16 contributes
zero completed runs and one blocked attempt. Counts include primary enhanced
PCM and delivered M4A, excluding input copies and repair/intermediate audio.

Further activation requires fixing signal availability and obtaining enough
inference/dispatch headroom, then repeating full-system acceptance before the
soak. Candidate precision or exit-layer changes also require a separately
activated quality review. The existing enhanced-only ASR path, source retention,
Stop behavior and human-edit preservation remain the operating contract.

## Repository verification

The [check receipt](checks.json) records 449 passing Python tests, nine focused
versioning tests, four native tests, clean Clippy/format checks, and successful
architecture generation and browser validation across 30 views and 77 source
files. Relative README/documentation links and image paths were checked.
Behavioral coverage includes grouped-frame alignment, exact sample count,
startup failure, pause reuse, regeneration barriers, failed-fsync ACK handling,
and missing endpoints failing acceptance.

## Evidence custody and reproduction

Raw audio, private transcripts, service databases, connection credentials and
full traces stay under the account-private diagnostics directory
`~/.local/share/project-aura/diagnostics/streaming-system-2026-10-22/`.
The sanitized receipt records source and code hashes without transcript text
or credentials. Existing run directories are immutable; use a new output path
for each run.

From the repository root, with the existing provisioned runtimes:

```bash
PYTHONPATH=src .venv/bin/python scripts/check_reuse_streaming.py \
  --pcm /path/to/authorized.pcm --output /private/new-paired-run \
  --seconds 60 --activate
PYTHONPATH=src .venv/bin/python scripts/check_streaming_system.py \
  --pcm /path/to/authorized.pcm --output /private/new-system-run \
  --seconds 930.18 --activate
```

The system runner requires the built native capture binary and a Qt-capable
Python environment, configurable through `--capture-binary` and `--gui-python`.
Longer requested durations repeat the source and record that fact. Candidate
enhancement probes accept `--candidate layer6-fp32` or `--candidate layer8-bf16`;
they do not change service settings. Profile probes use `--profile` and should
remain short. Run GPU probes sequentially and keep regression suites outside
system acceptance intervals.
