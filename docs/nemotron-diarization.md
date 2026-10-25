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

## Source and adopted scope — October 25

Jason requested the model replacement and default activation:

> 請刪除程式碼當中舊有的 pyannote ，並以 nemotron-3-diarization 為預設開啟。請詳加優化。

The execution instruction was: “Implement the plan.” Jason then requested:

> Using FIRST PRINCIPLE, and please take notes on my day note in the `planning-everything-track` repo, and update the relevant docs, files, and contents for it.
> Please update all the commits separately on git, and push this branch to the remote main branch of the github repo. (If there were conflict among commits, i would like to keep both local commits and remote commits.)
> And build strong connection with all other relevant files, docs, and contents.

**Adopted decision:** AURA owns code, pinned runtimes and private execution
receipts. Planning owns the locator, aggregate status, capacity and publication
receipt. The scarce resources are GPU time, uninterrupted recording, evidence
fidelity and operator attention. Jason selected the scope and acceptance target;
Codex implemented and tested the changes. Human effort was not measured.

**Publication integration:** Remote RE-USE capture, speech protection, recovery
and architecture commits are preserved by a merge. The measured 82.94-minute
Nemotron runs precede that merge. Regression checks of the combined code do not
extend those latency measurements to concurrent RE-USE execution. The activated
local service retains the measured pre-merge snapshot until combined-runtime
acceptance is explicitly scheduled. No new experiment or quality comparison is
activated by this publication.

**Next gate / Jason:** Reopen an existing GUI for the new controls. Allocate
capacity before combined RE-USE/Nemotron host and physical-device acceptance;
record results in the validation packet. DER and ASR quality remain deferred.

Connections: [runtime evidence](../artifacts/nemotron/README.md) ↔
[C4 source ownership](architecture/c4/source-map.md) ↔
[Planning project](https://github.com/JasonLn0711/planning-everything-track/blob/main/data/projects/2026-05-project-aura-refactor.md#aura-nemotron-2026-10-25) ↔
[October 25 day note](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W43/days/2026-10-25.md#aura-nemotron-2026-10-25).
