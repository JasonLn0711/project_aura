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

## CLI operations closeout

### First-principles decision

The follow-up requests concern locating output, understanding commands, ending
capture at an intended time, and removing an explicitly selected saved session.
The scarce resources are operator attention, recording custody and validation
time. Reuse the existing session protocol and command metadata; keep capture
control explicit and make the next action visible where the user encounters it.

### Implemented scope and connections

- `record --stop-at` validates a future timezone-aware deadline, persists UTC,
  and reuses scheduled stop handling. An active-work error identifies the session
  and provides attach/stop guidance. Deadline checks occur between inference jobs;
  this is not a hard real-time cutoff.
- `delete` previews the owned directory and requires the full UUID to confirm.
  Active capture and running jobs block deletion. File or database failures leave
  a retryable `deleting` state; external source media and exports remain intact.
  Tests use temporary sessions, including restart, failure and symlink cases.
- `files` resolves the selected session or the most recently updated session,
  prints registered output paths and optionally opens a local folder. SSH paths
  remain server-owned; export downloads to the client and reports an absolute
  destination. This is metadata discovery, not transcript-content search.
- `/help` lists each supported workspace command once with a short English
  description reused from the parser and completer. Display toggles include
  `on|off`; recording/session options remain available through `--help`.

The [operator guide](../../docs/shared-sessions-2026-09-08.md) connects
[timed capture](../../docs/shared-sessions-2026-09-08.md#install-and-operate),
[confirmed deletion](../../docs/shared-sessions-2026-09-08.md#delete-saved-sessions),
[output discovery](../../docs/shared-sessions-2026-09-08.md#find-and-open-output-files),
and the [README entry point](../../README.md#session-artifacts-and-data-layout).
Implementation is in [cli.py](../../src/aura/cli.py) and
[session_core.py](../../src/aura/session_core.py); regression coverage lives in
[test_shared_sessions.py](../../tests/test_shared_sessions.py),
[test_session_delete.py](../../tests/test_session_delete.py),
[test_cli_files.py](../../tests/test_cli_files.py), and
[test_terminal.py](../../tests/test_terminal.py).

Code commits are split by purpose: `9400fec` for recording/session lifecycle,
`9b04258` for output discovery, and `a0dce89` for readable workspace help.

### Validation and operating scope

- Final `make check`: 345 tests passed, including compile checks. The earlier
  332-test checkpoint above remains its dated evidence.
- Source and wheel builds and lock consistency passed for version 1.18.0.
- Nine focused versioning tests, relative documentation/image links, anchors
  and whitespace checks passed for this publication.
- The preceding output-discovery check read an existing ready session through
  the running service and verified saved transcript/live-file presence. Session
  identity, title, vocabulary, audio and transcript contents stay outside this
  public receipt. The local file-manager launch is mock-tested.
- This closeout starts no recording or inference, deletes no real session and
  restarts no service. ASR accuracy and latency remain `not_evaluated`.

Client-only help and file discovery need a new CLI process to load the updated
code. Timed stops and deletion require a service advertising their respective
capabilities; finish active work before restarting an older service. Source
publication does not certify current deployment, physical-device acceptance,
second-host SSH operation or a new release. The package remains 1.18.0.

The [Planning project locator](https://github.com/JasonLn0711/planning-everything-track/blob/main/data/projects/2026-05-project-aura-refactor.md#2026-09-10-cli-operations-closeout)
and [day note](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W37/days/2026-09-10.md#aura-cli-operations--first-principle-closeout)
retain status, publication, capacity and the next operator-acceptance gate.
Further model-budget changes, runtime comparisons and new experiment blocks
remain deferred until an explicit scope and capacity decision.
