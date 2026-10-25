# RE-USE redesign implementation audit

Continuation: [October 18 speech-suppression incident](../2026-10-18-reuse-speech-guard/audit-event.md)
records the later live guard, bounded recovery, native completion correction and
remaining review gates. The October 17 counts below remain historical evidence.

October 17 status: implementation and regression validation completed before
source publication. The October 18 handoff below records later Git integration. The availability packet records account-service
activation separately from isolated validation.

## Source and ownership

[Supplied decisions](source-decisions.md) preserve the post-stop ASR correction.
[C4 architecture](../../architecture/reuse-c4.md) owns the new design. Project AURA
owns code, runtime environments, public-input availability receipts and local
logs. The scarce runtime is the NVIDIA GB10 GPU. No cross-repository work or
Planning publication was requested.

## Implementation

- Removed the ClearVoice in-process adapter, external runner, environment switch,
  package resource expectation, capability declaration and evaluation entry.
- New sessions use fixed `reuse-v1`; old saved preferences migrate, while explicit
  removed CLI profiles fail with an actionable message. Historical evidence and
  existing sessions are not bulk rewritten or reprocessed.
- Isolated RE-USE worker uses pinned NVIDIA source and weights, checked hashes,
  FP32 CUDA execution, exit layer 8 and look-ahead 0. CPU control imports do not
  load PyTorch. Existing custom CTranslate2 remains in its own environment.
- Implemented streaming centered STFT, stateful frame prediction, inverse
  overlap-add, 30 ms transport reframing, short input padding and exact tail
  length. A continuous interval retains model state across ASR segments.
- Raw PCM ACKs remain independent of enhancement. A separate consumer reads the
  durable journal; excess work stays on disk. Replay reconstructs model state,
  deduplicates committed intervals and waits for regenerated enhanced samples
  before dispatching retained ASR jobs.
- Offline RE-USE reads the complete original WAV with five-second/50% overlap
  processing and bounded memory. It never consumes live-enhanced PCM. Encoding
  follows enhancement; validated M4A is atomically published before cleanup.
- Retention records enhancement receipts, phase and sample progress. Failed
  enhancement/encoding preserves original audio. Export recovery does not create
  a full-file ASR job. User edits remain authoritative.
- Rust capture waits for delivery commit before deleting its original spool.
  Reconnection can finish pending cleanup. An observed pause/resume race was
  corrected so missing an intermediate paused snapshot cannot stall uploads.
- Imported media uses offline RE-USE before its normal transcription workflow.
  The user-owned input is never removed. Previous noisereduce processing is
  absent from the current session and import paths; historical evaluation
  baselines remain available through the benchmark dependency group.

## Runtime diagnostics and corrections

1. CUDA 13 PyTorch 2.9.1 and torchaudio were installed under
   `runtime/reuse-venv`, without synchronizing the existing ASR environment.
2. Initial native builds failed because system Python development headers were
   absent. Existing extracted Ubuntu Python 3.12 headers were used for builds
   and retained under `runtime/reuse-headers` for Triton JIT compilation.
3. Mamba 2.3.2.post1 and causal-conv1d 1.7.0 compiled successfully. Both compile
   failures and the successful build log are preserved separately.
4. First actual live model execution failed during Triton JIT due to the missing
   runtime headers. The next attempt exposed bundled `ptxas` lacking `sm_121a`.
   The worker now uses the host CUDA 13 `ptxas`; both real models then produced
   the expected 118,960 output samples from the public input.
5. The first service test preserved incoming audio but stalled uploads after a
   rapid pause/resume. It was interrupted and retained as a failed attempt.
   The corrected helper passed the same full service workflow.
6. A regression process crash was traced to a test importing real PyTorch inside
   `patch.dict(sys.modules)`, then removing its loaded C extension at patch exit.
   The affected Parakeet unit fixture now supplies an explicit torch test double.
   The full suite subsequently passed; this was a fixture lifecycle correction.
7. The new replay-prefix gate correctly held a synthetic ASR job whose fixture
   had no enhanced samples. The worker-supervision fixture now declares its
   prepared 480-sample prefix; all 399 tests pass.
8. A temporary source-edit syntax error in replay deduplication was caught by
   checks, repaired, and the recovery tests rerun. It was not activated in the
   account service. Earlier failed test logs remain in the inventory.

## Evidence boundaries and next checks

`runtime/reuse-validation/` contains failed attempts, real model preflights and
isolated service runs. Public audio comes from NVIDIA's public sample
`2086-149220-0033.wav`; the five-minute input repeats that authorized sample.
No accuracy, CER/WER, preprocessing-effect comparison or ASR timing study was
activated. Identity worker tests establish control and failure behavior only.
Physical amd64/SSH and microphone acceptance remain separate from local ARM64
execution and the configured two-architecture CI matrix.

See the [availability packet](../../../artifacts/reuse-availability-2026-10-17/README.md)
for final measured counts and gates. Full logs and their hashes are inventoried
there, including failed attempts and the final 399-test regression pass.

## Final local outcome

The user-authorized Brave run completed 4,802,400 samples (300.15 seconds),
42 live text segments and 2,762 characters. Both live and offline enhancement
ran on GB10. Delivery committed, M4A validated, original working audio and
producer spool were removed, and zero full-file ASR jobs were created.
The idle account service was restarted and verified with `reuse-v1` and Breeze
loaded. The native capture binary was updated in `.venv/bin`. Physical amd64,
SSH second-host and microphone acceptance remain `not_evaluated`.

## October 18 publication and Planning handoff

FIRST PRINCIPLE: protect evidence fidelity, recording continuity and operator
attention. AURA owns code, C4 design and runtime receipts; Planning owns status,
capacity and the next gate. The [day note](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W42/days/2026-10-18.md#aura-reuse-closeout)
and [project locator](https://github.com/JasonLn0711/planning-everything-track/blob/main/data/projects/2026-05-project-aura-refactor.md#aura-reuse-closeout)
connect the final source publication to the existing W42 Red capacity boundary.
The local validation above occurred on October 17; October 18 records its
publication handoff. Human listening, physical amd64/SSH and microphone
acceptance remain separate, owner-activated gates. No new inference is run
for this documentation and Git closeout.

The separate [Yilan listening experiment](../../yilan-enhancement-2026-10-17.md)
retains its own source, human decision and full-length listening gate. Its
research commits are preserved during integration; they do not establish
ASR accuracy or replace this product availability evidence.

Publication preparation retained implementation commit `b75963a`, documentation
commit `12bea04`, and merge `a56ea1d`; all four upstream research commits through
`24becfe` remain ancestors. Two denoise-document conflicts were resolved by
retaining both the product update and separate listening study. The merged tree
passed 399 regression tests, nine focused versioning tests and 102 relative-link
checks. Planning validators passed with 44 grandfathered policy warnings and
zero new warnings. Upstream generated SVGs contain existing trailing whitespace;
those evidence files were preserved unchanged. The local delta against upstream
and both working-tree whitespace checks pass.

Detailed public-test traces remain owner-local and are explicitly ignored;
aggregate receipts and audit inventories are versioned. Git publication uses
the existing authenticated GitHub CLI helper per command and the latest
repository author identity, without changing global Git settings. Planning's
day/project notes retain the verified push receipt and exact published tips.
