# Live streaming reliability, DGX runtime, and Linux capture audit

## Identity and scope

- Audit ID: `AUDIT-2026-10-17-LIVE-STREAMING-001`.
- Date: October 17, 2026; conversation timezone: Asia/Taipei. Machine receipts preserve their own UTC timestamps.
- Canonical owner: Project AURA, `/home/jnlngx10/phd-research/repos/project_aura`.
- Status: `source preserved`, `adopted decision`, implementation locally applied, scoped runtime validation completed, publication not performed.
- Live mode: `availability_validation`; final Brave result: `LIVE_MINIMUM_COMPLETED`, `valid_target_runtime`. Accuracy and ASR latency: `not_evaluated`.
- Scarce resources: reliable captured speech, operator attention, GPU ownership, and reproducible evidence.
- Planning role: locator/status only if separately requested. This task changes no Planning repository and copies no voice material there.
- Scope: Linux capture/control on ARM64 and amd64 CPU hosts; NVIDIA GPU inference on the service; Rust capture with a small Python supervisor. This was not a complete application rewrite or CPU-ASR implementation.

Read [source reports](source-reports.md) before treating the narrative below as primary source. The machine evidence inventory is [log-inventory.json](log-inventory.json); the current implementation snapshot is [code-inventory.json](code-inventory.json). Raw private logs and recorded speech remain in the owner-local archive identified in those inventories.

## Outcome and qualification

The final verification captured the user's active Brave playback through the actual default HDMI monitor. English text appeared before Stop. Session `fb358355-5c8b-4da2-9e86-cc59308914ff` finished with four saved segments, 178 segment-text characters, and no failed jobs. Its session snapshot reports `silero-v6+webrtc-guard`, 606 accepted speech frames, and Breeze running on CUDA.

This validates live delivery for that exercised stream. It does not establish transcription accuracy, general language quality, arbitrary websites, long-duration reliability, physical microphones, second-host SSH, or physical amd64 compatibility. The earlier 49-second session remains incompletely transcribed even after recovery. All statements that the implementation or public-audio test was complete must be read within these boundaries.

The final regression suite passed 390 tests. Rust's three unit tests, formatting and Clippy checks passed during the initial implementation; the later incident fixes touched Python and documentation, not Rust. No commits, tags, pushes, releases, or remote CI runs were performed.

## Chronology and corrected conclusions

| Stage | Evidence and action | What it established |
| --- | --- | --- |
| Initial reliability audit | Closed SDK sockets, Stop/disconnect state loss, and unqueued-tail recovery were reproduced with failing regression checks. | Concrete transport/recovery defects, not a claim that every live failure was known. |
| Native implementation | Rust capture, local frame journal, replay protocol, bounded upload, supervised GPU worker, source/backend preflight, and architecture CI were added. | Implemented paths with unit/integration coverage. |
| Public GPU checks | `gpu-availability-r01` and `r02` used public audio through a virtual PulseAudio monitor and real Breeze CUDA inference. | Four GPU chunk jobs and 270 retained frames in each run; public-input availability only. |
| Synthetic transport checks | `capture-transport-r01` and `r02` used a test-double inference service and emulated 100 ms RTT. | Capture-process/backlog measurements, not ASR performance. |
| User stale-service report | Both client and daemon displayed 1.18.0, but the running daemon had no `audio_stream_v2` capability. | Version equality did not prove that the process loaded the updated source. |
| Service activation | Idle sessions were verified before shutdown. The old worker exited, but old daemon PID 1314353 hung; it was killed after graceful shutdown failed. Updated service capability was verified and Breeze reloaded. | New service code activated without terminating an active recording. |
| Missing dependencies | `pactl` and `parec` were absent; `sudo -n` required a password. The user installed `pulseaudio-utils`. | An environment prerequisite was supplied by the user; the agent did not install it with sudo. |
| Missing microphone | PipeWire exposed an HDMI monitor and no microphone. Combined capture failed after session creation. | A device-selection/preflight gap, not a GPU error. |
| Empty live transcript | Session `8be61abc-840e-4877-ace3-57fce22e312c` saved 49 seconds of audio and reached ready with zero chunk jobs. | Capture/export succeeded while speech selection failed. |
| Detector diagnosis | Silero accepted zero frames on decoded retained audio; WebRTC mode 3 accepted 792. The user confirmed spoken dialogue. | Evidence for testing an independent sustained-speech guard. |
| Recovery repair | Empty ready sessions had been returned unchanged by `/recover`; compressed M4A was skipped by tail re-segmentation. Both paths were repaired. | Three recovery chunk jobs completed; two produced saved text segments. This did not establish complete recovery. |
| Paced replay | Guarded short-chunk replay completed 14 inference jobs and produced live text, but only one two-character segment. | Technical pipeline availability with inadequate content; not a successful user transcription. |
| Language diagnosis | Session options forced `zh`; user clarified American English in Brave. Auto-language and forced-English diagnostics on the old audio still yielded sparse output. | Chinese selection was a mismatch, but not a sufficient explanation for all old-recording failures. |
| Actual browser acceptance | Brave was unmuted, uncorked, and routed to sink 47, the default HDMI output. A 25-second verification with English and an 8-second chunk cap produced live text and four saved segments. | Scoped live success on the actual playback route. |
| Defaults | Account preferences were set to English and `live_max_segment_len_sec=8`. | Operator settings changed for future sessions; repository-wide language defaults were not changed. |

The earlier claim that live transcription was implemented was too broad as a statement about this user's normal workflow. The subsequent field failures supplied the missing acceptance cases. This audit preserves those failures and the sparse intermediate outputs rather than replacing them with the final successful run.

## Implementation inventory

### Durable capture and transport

| Files | Change and purpose | Validation |
| --- | --- | --- |
| `native/aura-capture/Cargo.toml`, `Cargo.lock`, `src/main.rs`, `.gitignore` | Added Linux Rust helper; PulseAudio `parec` sources; PCM16 mono 16 kHz, 480-sample frames; paced PCM fixture path; source mixing; local frame journal; spool ownership lock; 1 GiB free-space gate; measured progress events; bounded network writes; reconnect backoff; private stdin credential renewal; local deadline and SIGINT drain. | Rust unit tests, Clippy, formatting, release build; compiled-helper integration and real virtual/HDMI capture. |
| `src/aura/native_capture.py` | Small Python supervisor locates helper and utilities, resolves sources, owns SSH/client renewal, initializes the helper over stdin, and retains the spool on failure. It imports no NumPy, Torch, faster-whisper, or Qt. | Clean base-client import and helper protocol check; real helper execution. |
| `src/aura/streaming.py` | Negotiated v2 protocol: producer identity, connection generations, 1–4 frame packets, 32-frame window, cumulative durable acknowledgment, exact duplicate replay checking, sequence validation, reconnect journal reconciliation, idempotent pause/stop boundaries. | Protocol tests for replay, conflict, stale connection, offline control and limits; actual native service-restart integration. |
| `src/aura/session_core.py` | Added persistent stream cursor table; clears stale producer ownership at startup; retains interrupted state; re-segments unqueued PCM/WAV tails; preserves Stop and Pause intent across disconnects. Separate scheduler handles recording deadlines without waiting for inference. | Transport/recovery and blocked-inference deadline regressions. |
| `src/aura/service.py` | Negotiates v2 while retaining v1; handles status/finish and frame packets; validates captured/sent counters; closes peers before core shutdown; passes selected capture backend to server capture. | Service/protocol integration and runtime validation. |
| `src/aura/sdk.py` | Discards closed/failed control socket before cleanup, tolerates cleanup errors, and preserves the original exception. | Closed-socket regression. No claim of automatic mutation retry is made. |
| `src/aura/audio/inputs.py` | Lazy PyAudio import so Pulse-based lightweight clients do not load the legacy capture dependency. | Base-client dependency checks. |

### GPU runtime, installation, and portability

| Files | Change and purpose | Validation and boundary |
| --- | --- | --- |
| `src/aura/worker.py` | One spawned GPU worker with pipe-based commands, crash detection, configurable watchdog, and bounded terminate/kill shutdown. | Watchdog and blocked-worker tests. Default safety timeout 300 seconds; not an ASR latency target. |
| `src/aura/asr/models.py`, `src/aura/system/cuda.py`, `src/aura/system/gpu_diagnostics.py`, `src/aura/asr/threads.py` | Probe the installed CTranslate2 CUDA backend rather than requiring legacy CUDA 12 library names; report architecture/backend/effective compute type; keep GPU-only ASR. | CUDA 13 GB10 probe and real inference. Earlier related changes already existed at task start; attribution boundary below applies. |
| `src/aura/session_runtime.py` | Cache model runtime receipt at load and provide actionable missing-dependency errors. | Runtime diagnostics and actual model use. |
| `scripts/setup_gpu_runtime.py` | Read-only default check of local GX10 build receipt, wheel checksum, interpreter prefix/RPATH, shared library, and CUDA int8 support. Optional restore/sync protects the reviewed custom backend and refuses mutation while a service is running. | Read-only preflight passed. Restore/sync was not exercised against the active production environment. |
| `Makefile` | Added native build/check/install and base-client setup; detects the checkout-local GX10 receipt for application setup. | Native build/install passed. Base-client setup must be used in a client environment because dependency sync can remove server extras. |
| `.github/workflows/ci.yml` | ARM64/amd64 Linux runner matrix; Rust build/check; checksum-bearing binary artifacts; base-client dependency check before full extras/tests. | Configuration only. No remote CI result or physical amd64 result was generated in this task. |
| `pyproject.toml`, `uv.lock`, completion-related files | Preserved existing base CLI dependency/completion work and checked it with the modified application. | Lock validation, package build, base tests. These changes were already present in part at task start. |

Host runtime: ARM64 NVIDIA GB10, driver 580.178.04 / CUDA 13, Python 3.12, faster-whisper 1.2.1, custom CTranslate2 4.7.1, Breeze `SoybeanMilk/faster-whisper-Breeze-ASR-25`. Requested compute type `int8`; effective type `int8_float16`. The native wheel's recorded SHA-256 is `7ee4035c168ba5b34af019f084f8e29c3fcad2ff6ca81340a03a625149ee9cff`. Its interpreter-specific RPATH makes it a checkout-local build, not a portable ARM64 wheel.

Rust 1.99.1 and its formatting/lint tools were installed under `~/.cargo`; shell startup files were not changed. Native helper was installed at `.venv/bin/aura-capture`. Test-only Python environment and extracted Debian development/runtime libraries were placed under `/tmp/aura-stream-tests` and `/tmp/aura-system-deps`; these were separate from the GPU environment. The user later installed the actual system PulseAudio utilities.

### Operator and field fixes

| Files | Change and purpose | Evidence |
| --- | --- | --- |
| `src/aura/cli.py`, `src/aura/ui/transcription_tab.py` | Linux Rust default with explicit legacy Python option; capability/source preflight; capture/upload status. Stale capability error now explains that the service must restart from the updated installation. | Terminal/UI tests; user failure reproduced against old process. |
| `src/aura/native_capture.py`, CLI, core, UI | Preflight validates the selected source before creating a recording. System-only selection does not require a microphone; microphone-only selection does not query the default output; a monitor default can fall back to an actual microphone. Missing-source errors give usable commands. | Five focused source tests and actual HDMI-only preflight. |
| `src/aura/audio/vad.py` | Retains Silero state and adds aggressive WebRTC secondary detection. A frame is admitted by the guard only after 300 ms of continuous secondary speech evidence with RMS at least 80 on PCM16 scale. Silence or insufficient evidence resets the secondary counter. Existing 320 ms pre-roll retains the onset. | Sustained-onset/reset test; old recording changed from zero to 767 accepted frames under the guard; actual Brave stream delivered text. Guard can admit additional non-speech and needs accuracy evaluation. |
| `src/aura/session_core.py` | Records peak RMS and accepted speech frames; reports guard use; distinguishes ten seconds of silent input from received audio with no accepted speech. Successful text clears the capture warning. | Capture-signal and terminal tests. Running service had the guard/diagnostics during field validation; the final warning-clear-on-recovery edit was made afterward and tested on disk. |
| `src/aura/terminal.py`, `src/aura/ui/transcription_tab.py` | Makes no-speech/input warnings visible during capture and after stop, rather than allowing a ready state and empty transcript to look unexplained. | Warning rendering regression. |
| `src/aura/session_core.py` | Allows `/recover` on an empty completed session; decodes retained M4A for re-segmentation; retains successful jobs and edited text. | New empty-M4A recovery test; real recovery of the reported session. Scratch decoded WAV remains owner-local. |
| `scripts/check_shared_session_availability.py` | Rust/virtual capture path, preload reuse/unload, live-before-end observation, pause/resume, captured-frame equality, segment bounds, and valid M4A export. | Public runs and private paced replay. Its nonempty-transcript success gate alone is insufficient for content acceptance, as the sparse private replay demonstrated. |
| `scripts/measure_capture_transport.py` | Separate synthetic comparison of Python/Rust capture process CPU, RSS and pending frames through delayed transport. | Two reports; neither measures ASR. |
| `scripts/check_terminal_pty.py` | Updated stale help-text expectation from `selects and preloads` to the current `Preload the selected model`. | PTY interaction smoke passed after correction. |
| README, shared-session documentation, `.gitignore` | Documented deployment roles, native transport, GPU build stewardship, diagnostics, recovery, evidence boundaries, and private service/spool exclusions. | Initial 83 relative links/images and versioning tests passed. This audit's documentation checks are separate from those historical results. |

## Incident diagnostics and evidence corrections

### Old saved session: capture was not silent

Session `8be61abc-840e-4877-ace3-57fce22e312c` originally recorded 791,520 samples / 1,649 frames. It had no transcript, no segments and no inference chunk jobs. Its final `audio_level=0.0` represented the last frame, not the whole recording.

Decoded M4A analysis found 791,552 samples, 390,179 nonzero samples, peak amplitude 31,577 and RMS about 3,351.13. The extra decoded samples are consistent with delivery encoding/padding and are not additional original capture frames. Native spool inspection found 791,520 samples, 388,895 nonzero samples and peak 14,393. The exported audio was normalized, so the two amplitude measurements are not interchangeable.

On the retained decoded audio, Silero's maximum reported probability was about 0.176, with zero accepted speech frames. WebRTC modes 1/2/3 accepted 814/802/792 frames. The new sustained guard accepted 767. These are diagnostic detector counts on one recording, not accuracy measurements or a model ranking.

Recovery completed three chunk jobs plus export, produced two segments and 45 transcript-file characters including formatting; segment content lengths were 3 and 18 characters. It remains incomplete. The conversation initially described this as two transcription chunks. The database corrects that count: three chunk jobs completed and two segments contained saved text. The update that recovery “produced text” should not be interpreted as complete restoration of the original dialogue.

### Sparse replay and language probes

The private paced replay used the guard with 2-second chunks and Chinese recognition. It completed 14 chunk jobs, retained 1,650 padded fixture frames, had valid segment bounds, and produced text before capture ended. Only one two-character segment was saved. Its receipt says `LIVE_MINIMUM_COMPLETED` under the existing functional gate, but the accepted interpretation is **technical delivery only, inadequate transcript content**.

The auto-language diagnostic guessed Chinese and produced seven short numeric segments. A forced-English diagnostic on the same old recording produced three characters. Those outputs do not establish the original spoken language or successful recovery. The user's clarification is the source for American English. Forcing Chinese was an operator-setting mismatch; it did not fully explain the failure on the old audio.

### Actual Brave playback

PulseAudio showed Brave routed to default HDMI sink 47, unmuted and uncorked. The verification session used system capture, English, punctuation disabled, and an 8-second maximum segment length. It generated live text before Stop, ended ready, and saved four segments containing 178 characters. The receipt's `work.done=4` counts chunk jobs only. The SQLite snapshot confirms four completed chunk jobs, one load job and one export job for this session. Segment count and inference-job count happen to match in this run; they are separate measures.

Raw output is private. Read the local receipt at:

```text
~/.local/share/project-aura/diagnostics/speech-guard-2026-10-17-r01/brave-live.json
```

## Validation ledger

| Check | Observed result | Scope |
| --- | --- | --- |
| Initial red probes | Three regressions reproduced before fixes | Socket disposal, Stop/disconnect, unqueued-tail recovery |
| Initial full suite | 378, then final initial pass of 381 tests | Successive implementation states; not additive counts |
| Device-fix suite | 385 tests; five focused source checks | The fifth source test was also checked separately after that full run |
| Speech/recovery suite | 389, then final 390 tests passed | Latest tested Python implementation |
| Focused final recovery/signal | Eight tests passed | Sustained guard and empty completed M4A recovery |
| Rust | Three unit tests, formatting, Clippy warnings denied, release build | Native implementation snapshot |
| Versioning | Five focused tests passed | Initial material README work |
| Base client | 19 terminal/completion tests; imports excluded heavy ASR/UI modules | Clean installation profile |
| Build/lock | `uv build`, `uv lock --check` passed | Packaging and locked dependencies |
| PTY | Passed after stale assertion correction | Synthetic device and ASR; not real GPU inference |
| Documentation | Initial 83 relative links/images passed; `git diff --check` passed | Historical initial packet; current audit validation recorded separately |
| Public GPU r01/r02 | Each four chunk jobs, 270 captured frames, validated M4A, live text before capture end | Virtual monitor, fixed public input, Breeze CUDA |
| Native service restart | All 100 fixture frames preserved across restart; unique spans | Real helper/transport, synthetic inference |
| Actual Brave | Four saved segments / 178 characters, live before Stop, no failed jobs | Physical output monitor + real GPU; ASR accuracy/latency not evaluated |

Synthetic transport r02, 100 frames per backend and 100 ms emulated RTT:

| Process | User CPU seconds | System CPU seconds | Peak RSS KiB | Peak pending frames | Accepted frames |
| --- | ---: | ---: | ---: | ---: | ---: |
| Python | 0.80 | 0.06 | 41,240 | 82 | 100 |
| Rust | 0.01 | 0.02 | 2,820 | 8 | 100 |

These are capture-process observations from one controlled workload per backend. They exclude inference, service-process cost and physical audio devices. Earlier r01 values remain in the original packet; no reports were overwritten.

## Log custody, provenance, and publication

The private archive is:

```text
~/.local/share/project-aura/audit-archives/2026-10-17-live-streaming-reliability/
```

It preserves 16 available `/tmp/aura*.log` command logs, account service/capture logs, private diagnostic logs/receipts, and the selected incident-session database rows. The inventory also hashes public evidence and owner-local session outputs/native spools retained in place. At capture, the selected database export contained three sessions, 13 jobs, 32 events and three preferences. Live files can change after a hash snapshot; copied archive files preserve the captured version.

The standard `~/.local/state/project_aura/audit/` directory was absent at this audit. No daily product-audit JSONL or hash-chain validation is claimed. SQLite service events, capture JSONL, validation receipts and human closeout notes are separate evidence layers. Credentials, connection JSON, environment variables and private initialization messages were excluded. The inventories identify content by path/hash; they do not publish recognized speech.

This task began with unrelated or earlier changes already present in `.github/workflows/ci.yml`, README, `pyproject.toml`, ASR models, CLI, completion, session runtime, completion tests and `uv.lock`, plus untracked Breeze activation/session-runtime tests. They were preserved. The current source snapshot records the combined working tree; it does not claim that every diff line was authored by this task. No original clean-tree patch is available to reconstruct finer attribution.

The initial artifact packet remains historical. Its `validation.json` hashes and 381-test count identify that earlier implementation, not the later guard/device fixes. This audit and its code inventory supplement it. The old statement that the account service was left untouched was true at initial closeout and was superseded by the explicitly documented troubleshooting restarts.

## Current operation and next gates

For this host's available system-audio source:

```text
/record --source system
```

For an explicit English invocation independent of saved preferences:

```text
/record --source system --language en --max-segment-seconds 8
```

Reopen the verified session:

```text
/resume fb358355-5c8b-4da2-9e86-cc59308914ff
```

The active account service was left running with the speech guard, and English/8-second defaults were saved. No physical microphone was present. Plain `/record` still requests system plus microphone, so operators on this host must select system-only capture or attach a microphone. The final warning-clear-on-success edit is tested source on disk and takes effect on the next service restart; a documentation-only audit does not restart it.

Remaining gates and limitations:

1. Human review of transcript completeness and correctness, especially the old incomplete recording and guard false positives. Accuracy and latency evaluations require separate activation and suitable ground truth.
2. Physical amd64 capture client to DGX over SSH, including a network outage, reconnect and source/device handling. CI is configured but unexecuted remotely.
3. Real GPU inference through a service restart; current restart coverage uses synthetic inference.
4. Physical microphone and mixed system/microphone acceptance, longer runs, disk-pressure/source-loss acceptance, and multiple playback routes.
5. More representative capture-performance repetitions before generalizing the synthetic comparison.
6. Stronger functional acceptance than “nonempty text,” because sparse output can pass the current availability script. No automated accuracy or completeness gate was implemented here.
7. Service build identity beyond a shared version string; capability checks and actionable restart messages are implemented, but no automatic safe service upgrade/restart command was added.
8. Source selection remains a snapshot at capture start. Automatic following of later default-output changes and every custom monitor naming scheme are not established by this audit.
9. Public release remains a separate request. Preserve existing work and private evidence; do not infer commit/push authorization from this documentation task.

## Documentation closeout validation

This documentation-only pass checked four Markdown files, 18 relative links,
and SHA-256 hashes for all 126 indexed evidence/source files; all passed.
`git diff --check` also passed. It did not rerun inference, restart the service,
change settings, or repeat the regression suite. The 390-test result is the
preserved implementation-run result.

Early red-probe and exploratory command outputs that were not saved as files
remain conversation evidence; this archive does not reconstruct missing raw
logs or exact execution timestamps. Available command logs are copied verbatim
into the private archive. User report excerpts are labeled as excerpts, and
the complete fix/decision narrative is maintained here.
