# Streaming speech suppression and recovery — October 18

Status: implemented, availability-validated and activated locally. Git
publication is recorded separately in the Planning day receipt. This event
continues the [October 17 redesign](../2026-10-17-reuse-redesign/audit-event.md);
the [selected source decisions](source-decisions.md) preserve the requested
behavior and later recording-preservation correction.

## FIRST PRINCIPLE and ownership

The required result is continuous usable ASR input while retaining the model's
noise suppression and recoverable original audio. Scarce resources are recording
continuity, evidence fidelity, operator attention and GB10 execution bandwidth.
AURA owns code, architecture and validation; private audio, transcripts, runtime
logs and reconciliation receipts remain in local custody. Planning owns status,
capacity, publication and the next decision. This record supports future
operations, incident diagnosis and weekly review.

Jason reported the live interruption, required both diagnosis and implementation,
set the enhanced-only and Stop/export boundaries, and supplied the authorized
recording. Codex implemented and verified the repair. Engineering output does
not establish attendance, learner completion or human quality acceptance.

## Diagnosis and implemented changes

Capture continued while the ASR queue was empty because enhanced audio could
become unusable before enhanced VAD and segmentation. A loaded ASR model and
advancing sample counters therefore did not prove that speech reached ASR.

The pinned live adapter had a concrete erasure mechanism: if more than half of
the predicted magnitude bins were zero, it cleared the entire time frame,
including surviving nonzero bins. `speech-guard-v1` bypasses that extra gate
only where source VAD and audibility evidence protect the corresponding
window. It preserves predicted magnitudes and phase, without a raw mix, gain
floor, model replacement or retraining. Nonvoice windows keep the reference
gate. Native all-zero predictions remain possible; their full internal model
cause is not established by this repair.

| Behavior | Original incident version | Current contract |
| --- | --- | --- |
| Live frame gate | Whole-frame mute above 50% zero bins | Preserve surviving predicted bins in protected speech windows |
| Sustained suppression | Capture could continue without usable ASR input | Source-aligned health check, one state reset per episode, explicit gaps |
| Missing live text | No bounded in-recording repair | One service repair worker; at most two fresh-state attempts per missing interval |
| Normal stream | Work counters did not distinguish suppressed speech | Main stream takes priority; late repair text sorts by source time |
| Existing text | Retained transcript | Submitted ranges require review; human edits remain authoritative |
| Offline export | Complete original through offline RE-USE | Same model and denoising algorithm; progress-based inactivity watchdog and validated delivery |
| Native completion | Pending retention could make a ready export appear failed | All captured frames durable plus ready export completes capture; spool deletion still requires authenticated delivery commit |

The first repair added health monitoring, explicit stopped recovery and export
supervision. The subsequent optimization added speech protection and bounded
live repair. The final native correction separated completion from cleanup.
These are distinct changes within this incident thread.

## Current two-path contract

During recording: original PCM is durably saved, then Real-time RE-USE output
passes through enhanced VAD/segmentation to Breeze. Source VAD is a protection
signal only. Streaming state spans ASR segment boundaries. The model remains
FP32, 16 kHz mono, exit layer 8, look-ahead 0.

After Stop: the complete original goes through offline RE-USE in five-second
windows with 50% overlap, then normalization and AAC encoding. Full decode,
format and duration validation precede delivery. Offline RE-USE does not take
live-enhanced audio as input and does not automatically start another ASR pass.
Its reference whole-frame mute rule is unchanged; the live speech guard has
not been extended to the offline model.

The [C4 architecture](../../architecture/reuse-c4.md#speech-suppression-and-recovery)
specifies thresholds, alignment, scheduling, pause/Stop cancellation and recovery.
The [operator guide](../../shared-sessions-2026-09-08.md) covers inspection and
explicit stopped recovery. New sessions use the guard; historical sessions and
the original recording's saved options retain their policy and interpretation.

## Evidence and limits

Canonical identities: `STUDY-AURA-STREAMING-001` and
`EXP-20261018-02-live-speech-guard`. The
[validation packet](../../../artifacts/reuse-speech-guard-2026-10-18/README.md)
owns measured counts and executable hashes. Execution is
`LIVE_MINIMUM_COMPLETED`, runtime is `valid_target_runtime`, and validation mode
is `availability_validation`.

- Fixed GPU runs covered 60 and 1,200 source seconds, with 10 and 255 successful
  ASR jobs. Both produced live text before source EOF and validated final M4A.
- The long run completed 26 live repair intervals; a dedicated receipt confirms
  two repairs before source EOF. Fourteen already-submitted parent intervals
  require review and one enhancement candidate remained unusable after two
  attempts. Original audio remains retained for unresolved work.
- At source 800–810 seconds, historical enhanced RMS was 0; current primary
  enhanced RMS was 1051.645996 PCM16, with two successful overlapping ASR jobs.
  This establishes signal availability, not transcription accuracy.
- Regression evidence records 428 Python tests, four Rust unit tests, Rust
  format/clippy checks and two compiled native/WebSocket control fixtures.
  Control fixtures use inference doubles and are separate from real GPU counts.
- A recent ready recording had been incorrectly marked failed after delivery
  because review retention prevented cleanup. Its full durable frame count and
  complete M4A were checked before a scoped state reconciliation. Existing text,
  options and revisions were preserved; ASR was not rerun.

Raw recordings, transcripts, model weights and private diagnostic logs are not
part of the Git packet. Prior attempts and the historical 390 pending recovery
candidates remain preserved; service restart does not activate their recovery.
Accuracy, denoising quality and latency remain `not_evaluated`. Deployment of the
guard is a functional availability decision, not quality certification.

## Connections and next gate

- [Audit index](../README.md) is the incident discovery entry.
- [Previous redesign](../2026-10-17-reuse-redesign/audit-event.md) explains the
  unchanged model/runtime and original transport ownership.
- [Planning day receipt](../../../../planning-everything-track/weeks/2026-W42/days/2026-10-18.md#aura-speech-guard-2026-10-18)
  records contribution, capacity and publication.
- [Project locator](../../../../planning-everything-track/data/projects/2026-05-project-aura-refactor.md#aura-speech-guard-2026-10-18)
  and [W42](../../../../planning-everything-track/weeks/2026-W42/weekly-plan.md#aura-speech-guard-2026-10-18)
  retain the current next gate.

Jason can review the flagged intervals when capacity permits and record
timecoded acceptance or defects here. A separately activated quality protocol
with reviewed ground truth is required for denoising/accuracy conclusions.
Physical amd64/SSH and microphone acceptance remain separate device gates.
No new review deadline, historical bulk scan or GPU run is scheduled.
