# RE-USE availability evidence — 2026-10-17

Project AURA owns this packet. Validation mode: `availability_validation`.
The target is the ARM64 NVIDIA GB10 host, with the existing Breeze / custom
CTranslate2 4.7.1 CUDA 13 environment. RE-USE runs separately under PyTorch
2.9.1+cu130, FP32, with host CUDA `ptxas` and pinned NVIDIA snapshots.

## Runtime evidence

| Run | Result | Evidence |
| --- | --- | --- |
| Both-model public preflight | Real live and offline models each returned 118,960 samples; streaming emitted before flush | [Receipt](preflight-r03.json) |
| Public capture service | Live text before Stop; pause/resume, M4A delivery and native spool cleanup | [Receipt](service-r02.json) |
| Five-minute public capture | 162 successful live chunk jobs, zero full-file jobs; validated 300.3-second M4A and committed spool cleanup | [Receipt](service-five-min-r01.json) |
| User-authorized Brave English dialogue | 300.15 seconds; 42 live segments, 2,762 text characters, zero full-file jobs; M4A validated and spool removed | [Receipt](brave-r01.json) |

The public source is NVIDIA's [speech sample](https://dldata-public.s3.us-east-2.amazonaws.com/2086-149220-0033.wav),
SHA-256 `5fceacff0315d49cb59fcc505bcecf1ed5f2f35c2897b1e65a59f30e5d922150`.
The five-minute public input repeats that sample. Brave voice and transcript
remain in the private diagnostics directory; this packet contains counts and
runtime receipts only.

The public five-minute engineering gate observed a maximum of 1,920 samples
waiting for enhancement input consumption after warm-up, below its 16,000-sample
limit. Brave measures original samples minus completed enhanced samples instead.
Brave observed a maximum of 2,400 pending samples and passed the same
16,000-sample gate. These are queue health checks, not ASR latency or throughput
measurements.

## Implementation checks

- Full regression: 399 tests passed, including explicit identity-worker tests of
  failure retention, replay, recovery, delivery and preservation of user edits.
- Focused versioning checks: nine passed.
- Native Rust tests: three passed; formatting and Clippy with warnings denied passed.
- Lockfile check and preservation of the custom ASR CUDA runtime passed.
- CPU import coverage verifies control imports do not load Torch. CI covers the
  configured architecture matrix; physical amd64 and SSH second-host operation
  remain `not_evaluated`.

No CER/WER, accuracy, ASR timing, preprocessing-effect comparison, microphone
acceptance or human listening evaluation was performed. Unit fixtures establish
their own control layer; the real-model receipts establish runtime availability.

## Provenance and custody

[Audit event](../../docs/audit-events/2026-10-17-reuse-redesign/audit-event.md)
records decisions, failures and repairs. [Source decisions](../../docs/audit-events/2026-10-17-reuse-redesign/source-decisions.md)
preserve the latest instruction: Stop processes audio only, with no second full ASR.
[Architecture](../../docs/architecture/reuse-c4.md) owns the C1–C4 design.

[Log inventory](log-inventory.json) records complete owner-local log locations,
sizes and SHA-256 checksums, including failed attempts. Logs were archived under
`~/.local/share/project-aura/audit-archives/2026-10-17-reuse-redesign/`.
[Working-tree inventory](working-tree-inventory.json) hashes the final dirty
working tree, including preserved earlier work. It is not an exact source
snapshot for earlier runs. No commit, release or publication was performed.

Account-service activation is recorded separately in [activation.json](activation.json).

The idle account service was restarted successfully with `reuse-v1`, the updated
Rust helper installed, and Breeze loaded. Existing CLI connections should be
reopened to pick up the new service connection. Local activation does not
establish physical amd64 or microphone acceptance.
