# Recording reliability and adaptive segmentation — September 10, 2026

## Intent and ownership

FIRST PRINCIPLE: preserve recorded audio, reject unusable input before disturbing
the inference worker, and make the wait for completed text an explicit operating
choice. Jason selected completed results only and phrase completeness over faster
updates. AURA owns code, operator guidance and validation; Planning owns the dated
status, capacity impact and next acceptance gate.

The reported failure combined a 12-token live prompt with 557 vocabulary tokens,
exceeding the shared 200-token budget at 569 tokens. The recording remained at
`Audio 00:00`. CPU-only verification using the locally cached Breeze tokenizer
reproduced that count. A separately saved, manually prioritized 25-term copy
uses 133 tokens including the live prompt. Both vocabulary files stay local;
the original was preserved and no terms were silently removed by the service.

## Implemented changes

- `abfaf3e`: cached-tokenizer preflight in shared session creation rejects overflow
  for recording, scheduling and import before persisting a session or changing
  model state. A cache miss retains worker validation without downloading assets.
- `08b550b`: adaptive endpointing retains an 800 ms pause for the first half of the configured
  maximum, then reduces it linearly to half. New sessions default to 20 seconds;
  fixed mode and old sessions preserve the previous behavior. Pause and stop
  preserve tail audio, and durable chunk jobs retain split reasons.
- Source recording continues independently of recognition. Completed ASR results
  are displayed; no provisional-caption stream or semantic boundary model was added.

See the [operator contract and rollback command](../../docs/shared-sessions-2026-09-08.md#adaptive-live-segmentation),
[hotword context](../../docs/transcription-front-end-2026-09-07.md), and
[product entry point](../../README.md). The earlier
[CLI presentation packet](../cli-garden-preview/README.md) owns screenshot and palette evidence.

## Validation

- `make check`: 332 tests passed, including compilation, invalid option rejection,
  CLI forwarding, saved schedules, legacy sessions, pause/stop tails and source
  sample continuity across forced splits.
- `uv build`: version 1.18.0 source distribution and wheel built successfully.
- `git diff --check` and touched operator-document relative links passed.
- README closeout repeated the 332-test suite and passed 9 focused versioning
  tests. All 76 local links, images and anchors across the README, operator
  guide, front-end note and this receipt resolved.
- Real microphone/system capture and ASR inference were not activated for these
  changes. Synthetic tests establish software behavior; they do not establish
  transcription accuracy or lower end-to-end latency.

## Next gate and publication boundary

Finish active work before restarting the service to activate the updated code.
Jason can then explicitly activate a bounded classroom-audio acceptance check,
with original audio retained and completed transcript persistence verified.
Accuracy and latency remain `not_evaluated`. This work does not select another
model, add cloud transcription, or allocate a new experiment block.

Source publication remains separate from runtime deployment and a release tag.
The package version remains 1.18.0; no new tag is part of this closeout.
