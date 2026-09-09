# Shared GUI, terminal, and SSH sessions — v1.17.0

AURA now runs one session service per operating-system account. The desktop and
terminal use `aura.sdk.AuraClient` for the same sessions, settings, revision
checks, exports, and recording controls. Closing a client detaches it. An
explicit Stop finalizes the recording. This implementation belongs to the
Python `project_aura` repository.

The GUI banner, window title, footer, CLI welcome, and `aura --version` share
`aura.metadata.__version__`. The repository bump script synchronizes package,
metadata, lockfile, README version, and release-candidate markers.

## Install and operate

```bash
make setup-app
uv run --no-sync aura --version
uv run --no-sync aura                  # interactive terminal with slash commands
uv run --no-sync aura gui              # desktop; project-aura is also supported
uv run --no-sync aura sessions
uv run --no-sync aura record --source microphone --detach
uv run --no-sync aura attach SESSION_ID
uv run --no-sync aura pause SESSION_ID
uv run --no-sync aura unpause SESSION_ID
uv run --no-sync aura stop SESSION_ID
uv run --no-sync aura refine SESSION_ID
uv run --no-sync aura export SESSION_ID --format refined --output refined.txt
uv run --no-sync aura export SESSION_ID --format txt --output meeting.txt
uv run --no-sync aura transcribe meeting.wav --profile light
```

Use `/help`, `/model`, `/record`, `/sessions`, `/resume`, `/attach ID`, `/pause`, `/unpause`, `/stop`,
`/inspect`, `/doctor`, `/refine`, `/export`, `/transcribe`, `/schedule`, `/detach`, and `/quit` in the
interactive terminal. Arguments follow the corresponding command's `--help`.
The interface provides command completion and a transcript that updates above
the prompt. `/status` prints the current state; `/graphs on|off` controls the
compact audio and pending-work history. It owns transcription operations; an LLM agent is a separate
product work package.

`aura schedule --start-at 2026-10-01T09:00:00+08:00 --stop-at
2026-10-01T10:00:00+08:00 --source microphone` schedules capture on
the service host. The service must remain running. One active recording owns
the inference slot; imported media queues serially.

uv manages Python dependencies and the environment. FFmpeg, PortAudio system
libraries, NVIDIA drivers, and OpenSSH are installed through the operating
system. Install uv before setup. Startup uses `--no-sync` so the chosen profile
stays intact; update dependencies deliberately through `uv sync --locked` with
the same extras. Stop active sessions and the service before changing its environment.

## Resume history and diagnose sessions

```bash
uv run --no-sync aura resume --all       # searchable picker on this service
uv run --no-sync aura resume --last      # most recently updated session
uv run --no-sync aura resume SESSION_ID  # full UUID or unique UUID prefix
uv run --no-sync aura inspect SESSION_ID
uv run --no-sync aura doctor
uv run --no-sync aura --ssh gpu-host resume --all
uv run --no-sync aura --json resume --all
uv run --no-sync aura --json inspect SESSION_ID
```

`resume` with no arguments opens the same picker as `resume --all`. History
includes sessions created through the GUI, CLI, or SDK on the selected service.
Each operating-system account and `AURA_DATA_DIR` owns its history; an SSH host
selects that remote service. The current checkout folder does not filter history.
The picker searches titles and IDs. Arrow keys move through a bounded list,
Enter opens the selected workspace, and Escape cancels. Rows show session ID,
state, last update, and title. Duplicate titles remain distinguishable by ID.
UUID prefixes must resolve uniquely; ambiguous prefixes list matching full IDs.

Reopening restores the saved transcript and follows new updates while retaining
the session's recording state. Use `/unpause` to restart a paused recording.
Completed, failed, and recoverable sessions open for inspection and available
exports; fresh capture begins through `/record`. `/resume` and `/attach` switch
workspaces, and `/quit` or `/detach` leave capture under explicit `/stop` control.
`--last` selects the most recently updated session, with UUID as a stable tie
breaker. Choose either an explicit ID or `--last`.

**CLI migration from v1.16.0:** scripts that used `aura resume ID` to restart
capture now use `aura unpause ID`. The SDK/service `resume` operation and GUI
pause/resume button retain their recording behavior. `aura attach ID` retains
its transcript-following behavior. Existing `sessions` API responses remain
available; the new SDK requests summary rows for history navigation.

The interactive workspace prints a saved error when it changes. `/status`
includes that error; `/inspect [ID]` shows timestamps, capture source and location,
work counts, and artifact paths. `/doctor` reports client and running-service
versions, existing capabilities, and log locations. Older services report
`unknown` version, and a mismatch is visible at startup. Diagnostics use the
normal connection flow, including service startup when needed. Finish active
recordings and jobs before restarting an older service to load updated code.
The service's version is independent of the CLI's `aura --version` output.

Global `--ssh` and `--json` options precede the command. JSON output contains
session snapshots for explicit selections and summary arrays for picker modes.
Redirected/noninteractive resume follows the same selection rules using plain
output, so scripts receive data without an interactive picker. Diagnostics
report connection and dependency metadata; physical device capture and model
inference have their own validation paths. The lab PC's reported zero-audio
failure can be inspected by its saved ID before selecting a device-specific fix.

## Remote operation

Use the same published source checkout on each computer. Prepare the CUDA host:

```bash
uv sync --locked --extra server --extra cli --extra capture --extra punctuation
```

Prepare the connecting computer (omit capture for a terminal-only client):

```bash
uv sync --locked --extra cli --extra capture
```

For direct SSH terminal use with server-side devices:

```bash
ssh -t jnclaw@SERVER_IP 'cd /home/jnclaw/every_on_git_jnclaw/project_aura && uv run --no-sync aura'
```

For client-side audio forwarding, the SDK invokes the server command by name.
Make the host’s uv-installed `.venv/bin/aura` entry point available as `aura`
in its SSH command environment. Verify with `ssh HOST command -v aura`.
Configure a working
OpenSSH host alias with key authentication and a verified host key.

```bash
uv run --no-sync aura --ssh gpu-host sessions
uv run --no-sync aura --ssh gpu-host record --source microphone --capture-location server
uv run --no-sync aura --ssh gpu-host record --source microphone --capture-location client
uv run --no-sync aura --ssh gpu-host export SESSION_ID --format txt --output meeting.txt
```

The SDK starts an authenticated loopback WebSocket service through SSH and
forwards it with `ssh -L`. The service binds `127.0.0.1`, uses a random bearer
token stored with owner-only permissions, and rejects browser origins. SSH
keys and host verification remain owned by OpenSSH. The desktop's connection
field accepts the same host alias. “Service host capture” selects host devices;
“This computer capture” sends local audio through the tunnel. The detached
capture helper keeps its own connection when the presentation client closes.

Ubuntu is the exercised platform. Cross-computer SSH and physical microphone
acceptance remain installation checks on the target machines; Windows launch
scripts retain the desktop entry point and dependencies.

## Ownership and bounded work

- `session_core.py`: SQLite WAL sessions, persistent job queue, settings,
  ordered events, revision checks, scheduling, and lifecycle state.
- `session_runtime.py`: one spawned CUDA worker, reusing the existing ASR,
  punctuation, enhancement, diarization, and export functions.
- `service.py`: account lock, authenticated WebSocket transport, uploads,
  downloads, and capture-helper launch.
- `sdk.py`: shared request, event subscription, audio streaming, file transfer,
  and SSH connection methods. Importing the SDK loads neither Qt nor CUDA.
- `producer.py` and `audio/inputs.py`: detached device capture and disk-backed
  forwarding. Source tracks are journaled before VAD and transcription.
- `cli.py` and `ui/transcription_tab.py`: terminal and desktop presentation.

The queue stores audio offsets instead of accumulated NumPy chunks. One
inference job runs at a time; a slower worker leaves durable queued audio.
Pause closes the capture admission path, finishes the current inference, and
holds queued inference until Resume or Stop. Stop drains accepted audio and
exports it. Refinement is an explicit second pass saved to `refined.txt`;
manual editor text stays in `transcript.txt`.

Client capture retains a local recovery spool as well as the server's accepted
journal. This costs disk space and preserves audio across a broken connection.
A disconnected producer leaves an explicit paused/recoverable state; Resume
opens a fresh capture interval. Historical audio is available for explicit
refinement rather than being silently replayed into a new live stream.

## Data and recovery

`AURA_DATA_DIR` selects the service root; its default is
`~/.local/share/project-aura`. Keep it on a local writable filesystem.

```text
sessions.sqlite3                 # sessions, events, jobs, shared preferences
connection.json                  # private local token and process locator
service.log / capture.log
sessions/UUID/
  session.json
  .capture/*.pcm
  live.txt / transcript.txt / refined.txt
  prepared_transcript.json / segments.json
  refined_segments.json
  UUID.wav / UUID.m4a            # source and delivery audio
capture_sources/UUID/            # local source recovery spool
uploads/                        # explicitly uploaded media
audit/                          # content-free command audit
drafts/UUID.txt                  # unsent desktop text preserved at detach
```

The manifest and API artifact locators are authoritative. Export copies an
artifact to a chosen destination with overwrite protection. Service restart
marks interrupted work recoverable. Select it and request explicit refinement
from preserved audio. An unsent desktop draft remains in `drafts/UUID.txt` for
manual recovery. Keep source journals until exported audio and text have been
reviewed. Stopping the service is an operator action; closing the desktop
preserves ongoing sessions.

## Audio profiles and evidence

Light (`noisereduce`, normal room policy) is the requested product default.
Off preserves the direct input path; medium increases denoise strength;
far-speaker adds bounded gain and a longer VAD energy bridge. These controls
are implemented and exercised by regression tests. They represent different
capture conditions; quality improvement requires paired reference review.
Offline rescue uses the existing optional enhancement runner and its reported
fallback when the separate environment is unavailable. It applies to imports.

The product keeps bundled stateful Silero with a reported WebRTC fallback.
The comparison harness pins Breeze CUDA/int8 and separates the enhancement
arms (Off, Light, FastEnhancer-B, DPDFNet2) from the VAD arms (bundled Silero,
Silero 6.2.1, FireRed Stream-VAD). The 17-case corpus is present locally.
Acoustic review, reviewed numbers/terms, and 16 kHz speech-boundary annotations
activate its quality comparison. The generated review template is under the
local study's `review-20260908` directory. Its current status is `PREFLIGHT_ONLY`.
Candidate adapter availability is separate from a completed comparison.

Upstream references: [Silero 6.2.1](https://github.com/snakers4/silero-vad/releases/tag/v6.2.1),
[DPDFNet 0.6.0](https://github.com/ceva-ip/DPDFNet/releases/tag/v0.6.0),
[FastEnhancer ONNX DNS](https://github.com/aask1357/fastenhancer/releases/tag/onnx-dns-v1.0.0),
and [FireRedVAD](https://github.com/FireRedTeam/FireRedVAD).

## Validation receipt

The [availability packet](../artifacts/shared-session-availability-2026-09-08/)
contains two successful public-audio CUDA checks through the service: one WAV
and one M4A delivery path. Both exercised two SDK clients, ordered audio,
pause/resume, non-empty transcription, persistence, and export. Each used one
source clip and one session. These are `LIVE_MINIMUM_COMPLETED` with
`valid_target_runtime`; accuracy and latency are `not_evaluated`. The desktop
also rendered the resulting persisted public transcript through the actual
service. Regression tests use explicit test doubles for deterministic control
and failure cases.

The v1.16.0 full regression suite passes 295 tests. A clean CLI-only installation
imports the SDK without Qt, PyAudio, NumPy, or model dependencies. The detached
producer control loop passes with a synthetic device; this is a functional
test distinct from physical microphone acceptance.

Run `make check` through uv. The availability script requires
`--activate-availability`, an authorized input WAV, and a new output directory.
The paired driver `scripts/run_preprocessing_study.py` generates its review
packet before activation. Physical-device acceptance, second-host SSH, and the
reviewed preprocessing comparison remain separate validation layers.

## Planning connection

The [September 8 day receipt](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W37/days/2026-09-08.md#project-aura-shared-service-and-uv-receipt)
and [project locator](https://github.com/JasonLn0711/planning-everything-track/blob/main/data/projects/2026-05-project-aura-refactor.md)
track capacity, source publication, and the next acceptance gate. This repository
owns implementation and validation; Planning preserves the learning allocation
and records actual AURA work time as unreported. Source publication is distinct
from a release tag or completion of the quality comparison.

Source checkpoints: `4de00a4` owns the shared runtime and clients; `0cabed3`
owns functional and review-gated study checks; `5aa5b13` owns the uv setup,
CI and Windows launcher changes. Source publication uses remote `main`;
`v1.17.0` remains a separately governed release candidate.

## v1.16.0 validation and compatibility

Version display uses runtime metadata in the GUI banner, title and footer, and
in the CLI welcome and `--version`. The CLI version command exits before service
connection. The version bump includes package metadata, lockfile, README and date.
The [version receipt](../artifacts/shared-session-availability-2026-09-08/version-1.16.0.json)
records the v1.16.0 checks; the earlier WAV/M4A receipts retain their original
execution provenance. No new ASR inference is counted for this presentation update.

Windows CI on the preceding source exposed open SQLite connections during
atomic index replacement, locale-dependent test reads, and POSIX permission
assertions. Explicit connection closure and UTF-8 reads address the first two;
mode-bit assertions apply on POSIX, while Windows access remains governed by
its account directory and ACLs. Native Windows validation runs in hosted CI.

## Direct recording and terminal presentation

Record and Schedule use the selected source immediately. The GUI checkbox and
service confirmation gate have been removed. Old `--consent` flags and SDK
fields remain accepted as ignored compatibility inputs. Device availability,
source validation and explicit Stop retain their operating roles. Finish active
recordings before restarting an older service process to load updated code.

The scrolling terminal uses the existing prompt toolkit, AURA teal accents and
an original pixel owl. The prompt remains usable while commands and transcript
updates arrive. Audio level and pending-work graphs use actual session values,
with client history bounded to 60 observations and refresh capped at four times
per second. Captured-audio duration comes from source samples. Uploads show byte
progress; downloads report transferred bytes; stopped-recording queues show
completed versus total chunk jobs. Open-ended recording and unknown-duration
jobs display state/activity rather than a percentage. Disconnects stop graph
updates, narrow terminals collapse the display, and JSON stays decoration-free.

`uv run --no-sync python scripts/check_terminal_pty.py` exercises owl/version,
transcript arrival during partially typed input, graph toggling and clean exit
with synthetic audio/ASR. Linux CI runs it separately from the regression suite.
The command-line version remains available without starting the service.

## v1.17.0 validation

The [v1.17.0 receipt](../artifacts/shared-session-availability-2026-09-08/version-1.17.0.json)
records 302 passing regression tests, version/lock/link checks, and package
builds. The Linux PTY check exercises title search, arrow selection, Escape
cancellation, restored transcripts, saved failure reasons, typing during live
updates, and clean exit using synthetic audio and ASR. Session tests establish
read-only reopening across paused, active, completed, failed, and recoverable
states, while `unpause` exercises the existing service recording operation.
The earlier public-audio receipts retain their original live inference counts.

Hosted [Linux CI](https://github.com/JasonLn0711/project_aura/actions/runs/34222936459)
and [Windows CI](https://github.com/JasonLn0711/project_aura/actions/runs/34222936393)
passed for source `412bbc8`, including the Linux terminal interaction check.


## Optional Parakeet v2 integration (unreleased)

The session `options.asr_model` field accepts `breeze` (the default) and
`parakeet-tdt-0.6b-v2`. Legacy sessions and queued jobs without the field resolve
to Breeze. Preferences affect new sessions; recording, queued chunks, and
refinement retain the session snapshot. No database migration is required.

The existing single-worker process pool owns both runtimes. It closes the old
worker before a different ASR model starts, and retains the existing idle cleanup.
The service and GUI import only model metadata; NeMo and CUDA objects remain in
the inference process. `capabilities.asr_models` is additive to protocol version 1
and reports static capabilities, optional dependency presence, and local cache
presence. Its `runtime_probe` is `not_performed`; actual runtime receipts belong
to the sessions that exercised inference.

CLI record, transcribe, and schedule commands accept `--model`. The server-local
`models download parakeet-tdt-0.6b-v2` command retrieves a pinned official checkpoint;
normal inference loads it offline. English-only settings are resolved centrally,
with inherited Breeze prompts/hotwords excluded from the effective Parakeet
snapshot and explicit incompatible options rejected. GUI controls preserve
Breeze values while disabled for Parakeet.

Imported speech scratch audio is decoded to 16 kHz mono PCM through either the
FFmpeg or Python preparation path. NeMo segment timestamps enter the existing
review artifact contract with `asr_logprob=null`. Live review segments retain
AURA's durable capture-interval coordinates. Runtime receipts identify the
checkpoint revision, NeMo/PyTorch versions, precision, and attention configuration.

See the [availability packet](../artifacts/asr-parakeet-availability/README.md#initial-availability)
for the exercised paths and remaining validation boundaries.


### Interactive model lifecycle controls

`aura model` and `/model` show `model.status`. A model name or `load` submits
`model.load`; `unload` submits `model.unload`. The existing inference worker
handles controls asynchronously while status queries remain available. Controls
are rejected during active work or another load/unload. `model_control=true`
advertises support; old services receive explicit restart guidance in the CLI.

A successful explicit load persists the shared model default and retains its
worker until explicit unload, a different-model job, or service shutdown.
Failed loading releases the worker and preserves the prior default. Ordinary
recording/import loads retain the existing idle release policy. Session model
snapshots and stored transcripts are unchanged by model selection. Entering the
CLI does not allocate GPU memory; the banner, toolbar, and `/model` show that state.


### Tab completion and inference decisions

The workspace uses `WorkspaceCompleter` with the existing argparse definitions
and prompt_toolkit Tab behavior. Commands, model choices, options and local paths
complete in context; Enter executes. Tests apply completions to real input buffers
and the PTY check sends actual Tab keys. Reopen the CLI after updating the client.

[ASR inference decision](asr-inference-decision-2026-09-09.md) preserves the source
questions, `uv run --no-sync aura` explanation, memory accounting, framework
options and deferred precision gate. The [public validation summary](../artifacts/asr-parakeet-availability/README.md)
separates 317 software tests from the two earlier real availability attempts.
