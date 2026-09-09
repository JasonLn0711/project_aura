# Parakeet v2 availability receipts — 2026-09-09

This publication preserves aggregate functional evidence and hashes of owner-local
receipts in [public-summary.json](public-summary.json). Raw audio, transcripts,
request/event logs, session identifiers, local paths, databases and connection
credentials stay in their original local attempt directories, excluded from Git.

## Initial availability

`2026-09-09-attempt-01`: `availability_validation`, `LIVE_MINIMUM_COMPLETED`,
`valid_target_runtime`, `available_and_working`. Three real inference jobs
exercised file import, one VAD-delimited audio interval and explicit refinement;
one recorded WAV was exported. Input was the
[public NVIDIA example](https://dldata-public.s3.us-east-2.amazonaws.com/2086-149220-0033.wav).
The audio-ingest path used controlled playback; physical microphone and
second-host SSH acceptance remain separate gates.

## CLI model controls

`2026-09-09-cli-controls`: the same functional status, three real inference jobs,
and one recorded WAV export. Explicit preload reused one worker across import,
VAD processing and refinement; explicit unload was followed by worker exit.
The two attempts establish six inference jobs in total, not six independent
quality trials. No ground truth was read. Accuracy, latency, throughput and
model/precision ranking remain `not_evaluated`.

Both attempts used `nvidia/parakeet-tdt-0.6b-v2`, revision
`ae9ad07059c7c739ffaf932226a8fe64ae2620b0`, NeMo 3.0.0,
PyTorch 2.11.0+cu128, CUDA FP32, batch size 1, local attention `[128,128]`
and automatic subsampling chunking. Attribution: NVIDIA,
[model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## Software and local-state validation

The subsequent Tab-completion regression passed 317 tests; nine focused
versioning tests and the Linux PTY check passed. The PTY uses synthetic ASR
and verifies actual Tab key input, completion without execution, model selection
and unload. These checks are separate from the real inference receipts above.
Reproduce software checks with `QT_QPA_PLATFORM=offscreen make check`,
`uv run --no-sync python -m unittest tests.test_versioning tests.test_bump_version`
and `uv run --no-sync python scripts/check_terminal_pty.py`.

Local service restarts preserved exact session/preference rows. An initial GUI
test changed a local QSettings vocabulary value; tests now isolate QSettings.
Recovery used the latest saved session's empty vocabulary because the prior
GUI-only value had not been snapshotted. This limitation remains in the local
receipt; it does not establish exact restoration of that earlier GUI-only value.

Source publication does not create a release tag or establish Windows-native
NeMo, long-recording or physical-device acceptance. Breeze remains the application
default; Parakeet is an explicitly selected English runtime.

See the [operator guide](../../docs/shared-sessions-2026-09-08.md) and
[FIRST PRINCIPLE inference decision](../../docs/asr-inference-decision-2026-09-09.md)
for commands, evidence boundaries and the deferred optimization gate.
