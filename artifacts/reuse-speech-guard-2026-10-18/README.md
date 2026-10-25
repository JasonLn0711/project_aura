# RE-USE speech-guard availability packet

[validation.json](validation.json) is the sanitized functional receipt for
`STUDY-AURA-STREAMING-001` / `EXP-20261018-02-live-speech-guard`.
It records pinned model revisions, executable SHA-256 hashes, regression counts,
60-second and 1,200-second live GPU runs, native completion and local activation.

Validation mode: `availability_validation`. Execution:
`LIVE_MINIMUM_COMPLETED`. Runtime: `valid_target_runtime`. Production activation:
`active` at the recorded closeout. Accuracy, denoising quality and latency:
`not_evaluated`. This is a historical receipt, not a live service-status endpoint.

The 1,200-second run completed 255 ASR jobs and 26 live repair intervals. Fourteen
submitted parent intervals still require review; one enhancement candidate
remained unusable. The original audio is retained. Counts of jobs, parent
intervals and repair intervals describe different units and are not additive.

Private evidence is held under the account's
`~/.local/share/project-aura/diagnostics/reuse-speech-guard-2026-10-18/`:
`availability-short-r02/receipt.json`, `availability-long-r02/receipt.json`,
`signal-800-810-comparison.json`, `live-repair-before-eof.json`,
`activation-receipt.json`, `capture-state-reconciliation.json`,
`validated-source-final.json`, and the regression/native logs. Earlier incomplete
attempts remain in that directory and are excluded from the two completed-run
counts. Audio, transcripts, session databases and model weights stay local.

Use the [incident record](../../docs/audit-events/2026-10-18-reuse-speech-guard/audit-event.md)
for interpretation and next gates, the
[source decisions](../../docs/audit-events/2026-10-18-reuse-speech-guard/source-decisions.md)
for user scope, and the [C4 architecture](../../docs/architecture/reuse-c4.md)
for the implementation contract. Publication checks are recorded separately
from the live runtime receipt in [publication-checks.json](publication-checks.json).
The publication regression uses the existing isolated test environment and
extracted PortAudio library; it does not synchronize the product ASR environment.
An edit-preservation fixture now captures and submits its current revision under
the session lock, avoiding an unrelated stale-revision race while live jobs finish.
All 77 live executable hashes still match. Eleven touched Markdown files contain
490 relative links, with zero new failures and 65 inherited unavailable paths or
anchors; Planning checks pass with 44 existing policy warnings and zero new.
