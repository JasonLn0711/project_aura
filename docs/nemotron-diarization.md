# Nemotron diarization operating contract

AURA owns the implementation and local validation evidence. The constrained
resources are GPU memory shared with ASR and the full-duration replay window.
Private audio, timestamps, transcripts, and model output stay in the owner-local
`local_outputs/nemotron/` directory. [Public validation status](../artifacts/nemotron/README.md)
contains aggregate evidence only.

## Installation and defaults

Run `python3 scripts/setup_nemotron.py`, then `aura doctor`. The setup script uses
`dependencies/nemotron/requirements.txt` and caches the pinned model. It requires
Python 3.12, `uv`, FFmpeg, and an NVIDIA CUDA runtime. The default interpreter is
`.venv-nemotron/bin/python`; `AURA_NEMOTRON_PYTHON` overrides its location.
ASR and punctuation remain in AURA's main environment.

The model is `nvidia/Nemotron-3-Diarization`, revision
`f667ed73aee57d40cc39428eb768b4fd87a0a29e`. Transformers is pinned to commit
`50e35cc0ca18ec19b80653690de553e6decf74f5`. Inference uses CUDA FP32, batch size
one, and the official `low_latency` streaming processor. Its 1.04-second input
buffer is one component of end-to-end speaker-update latency.

New sessions enable diarization. The one-time `nemotron-default-on` database
migration replaces the old shared default and removes obsolete speaker-count
preferences. Explicit choices saved afterward persist. Use `--no-diarization`
for recording, import, or refinement to disable it. Historical session options
and saved text are preserved. Old count fields are accepted at the compatibility
boundary but do not constrain Nemotron's automatic, up-to-eight-channel output.

## Runtime and artifacts

The capture producer sends 30 ms frames. The service saves mixed PCM before
analysis. The diarization worker consumes complete published samples with the
processor's required lookahead, retains speaker cache, and emits new activity
intervals. It never waits for ASR to finish a phrase. Clients receive diarization
sequence and processed-sample cursors even when transcript revision is unchanged.

`diarization.jsonl` contains incremental live turns; file imports save
`diarization.json`. Refinements save `refined_diarization.json` separately.
Speaker labels join existing review segments by timestamp overlap. Multi-speaker
segments retain a review flag. The system does not perform audio-source
separation, biometric identification, or word-level speaker alignment.

Only bounded audio windows and model cache stay in the worker. Historical turns
are journaled and retained on the service CPU for transcript alignment. Already
assigned segments are skipped on subsequent updates. Thus model memory does not
grow with recording duration; the CPU interval index grows with speaker turns.

## Failure and recovery

A failed model preload prevents an enabled recording from starting. During
capture, diarization failure preserves audio and leaves ASR available. The
session exposes the error independently from ASR errors. There is no alternative
model fallback. An update more than three seconds behind is displayed as
catch-up rather than current speaker activity.

Pause/resume retains cache. Stop flushes remaining audio before finalization.
Unfinished diarization prevents working-audio cleanup. After restart or a failed
stream, recovery replays retained audio from the beginning to rebuild cache.
Prior live receipts are retained with unique names. Human edits are not replaced.
A successful full-file refinement can supersede unfinished live analysis while
retaining its provenance.

## Validation

`PYTHONPATH=src .venv/bin/python scripts/validate_nemotron.py INPUT OUTPUT --mode stream`
starts an isolated AURA service, sends the recording at original speed over the
production authenticated transport, and observes speaker events using the SDK.
`--mode file` exercises the full import path. Every run uses a new output folder
and records source and code hashes. Do not commit the private output directory.

Streaming acceptance requires all input frames to be analyzed, consecutive
speaker event sequences, nonempty persisted ASR output, successful export, and
p95 speaker-update latency no greater than three seconds after preload. The
latency includes the oldest sample scored by each update, buffering, inference,
and event delivery. Silence and continuing speakers remain in the measurements.
Failures and late events are retained. ASR accuracy and latency are not evaluated.
File replay does not establish physical microphone acceptance or diarization DER.

## Upstream references

- [NVIDIA model card](https://huggingface.co/nvidia/Nemotron-3-Diarization)
- [Pinned processor source](https://github.com/huggingface/transformers/blob/50e35cc0ca18ec19b80653690de553e6decf74f5/src/transformers/models/nemotron3_diarization/processing_nemotron3_diarization.py)
