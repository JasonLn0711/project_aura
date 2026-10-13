# Mixed M4A retention — October 13, 2026

Project AURA owns the recording format, cleanup implementation and verification.
Disk capacity, recording continuity and operator attention are the scarce resources.
Planning holds the day receipt, capacity, publication references and next gate.

## Source and adopted decision

Jason requested:

> audio file output 的時候，只留下 m4a file 就好，mp3、 wav 就請刪除。

> Implement the plan.

The adopted scope includes completed service recordings and legacy project recording
packages, retaining only the mixed M4A. Imported sources, splitter outputs,
independent capture spools/backups and unfinished or recoverable work remain outside
cleanup. Jason selected the activation boundary:

> 保留目前錄音，結束後再切換

Jason subsequently requested day notes, related documentation, separate commits and
publication to remote main while preserving local and remote commit history. These
instructions authorize source publication; the active recording remains protected.

## Implementation and evidence

The [operator guide](shared-sessions-2026-09-08.md#mixed-m4a-retention-and-existing-recordings)
defines the supported output and offline migration commands. The
[retention module](../src/aura/audio/retention.py) validates AAC, full decoding,
duration and track layout before publishing references and deleting registered
working audio. Failed encoding, unresolved ASR and failed persistence retain inputs;
partial deletion has a durable retry list. [Cleanup tooling](../scripts/cleanup_recording_audio.py)
uses the service lock and rejects active work. Evidence search resolves the current
manifest locator without rewriting historical text indexes.

The [aggregate receipt](../artifacts/audio-retention-2026-10-13/summary.json)
records 27 cleaned legacy recording packages, 80 deleted WAV files and
5,383,793,920 bytes released (5.38 GB decimal). One recording with an unavailable
registered mixed source was skipped; an import manifest was excluded. Independent
splitter M4As remain retained. The initial service cleanup attempt was deferred because the running
service held its lock; the later activation below records the completed switch. Private filenames, session identifiers, transcripts and raw
cleanup logs remain in ignored local `outputs/audio-retention-2026-10-13/`.

The initial implementation passed 359 regression tests and 9 focused versioning
tests; 55 README relative links/images were valid. Integration with remote commits
preserves bounded progress events, owner-discarded audio guards and retained-M4A
recovery. The merged validator uses the remote 100 ms duration tolerance and checks
channel count/sample rate; the initial legacy cleanup used a 250 ms tolerance.
The aggregate receipt identifies final integration checks separately. Synthetic
audio and fake ASR tests establish software behavior; they do not establish
physical-device acceptance or recognition accuracy.

The October 1 temporary-WAV download behavior is superseded by M4A-only recording
exports. Independent producer capture spools remain outside this cleanup scope.
Remote vocabulary, punctuation and CLI documentation changes remain in history.

## Activation and connections

The protected recording subsequently reached `ready`, and the service had no active
session or queued/running database jobs. The primary AURA checkout was fast-forwarded
to published `f269ec4`; a named scoped stash preserves the pre-integration implementation.
Unrelated files remained in place. The idle service received normal SIGTERM, offline
preview/apply completed, and the service restarted from the published primary source.
No recording was interrupted and no dependency synchronization was performed.

Service cleanup processed 20 sessions, deleted 48 working audio files and released
4,217,938,752 bytes. Together with legacy cleanup, the total is 9,601,732,672 bytes
(9.60 GB decimal). Thirteen service sessions were skipped: six were imported,
unfinished or recoverable; seven lacked the registered mixed source. Existing
artifacts remain preserved for locator review. All 20 cleaned manifests point to
retained M4A, their journals/pending cleanup lists are empty and deleted paths are absent.

Authenticated readback after restart returned 28 ready, four failed and one
recoverable session; the protected recording remained ready. All 27 ready-session
M4A artifact paths existed. This confirms service activation and artifact persistence.
Reopen existing clients to load the current controls. A new short physical recording,
playback/export acceptance and review of skipped source locators remain the next
operator checks; no new recording or ASR accuracy experiment was performed.

Jason supplied the retention and continuity decisions. Codex implemented, verified,
cleaned eligible legacy packages and prepared the publication. Human time was not
reported. This maintenance creates no new learning quota or recurring schedule.

[Planning day](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W42/days/2026-10-13.md#aura-m4a-retention)
links the [project locator](https://github.com/JasonLn0711/planning-everything-track/blob/main/data/projects/2026-05-project-aura-refactor.md#aura-m4a-retention)
and [W42 capacity](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W42/weekly-plan.md#aura-m4a-retention).
The [integration index](https://github.com/JasonLn0711/planning-everything-track/blob/main/docs/14-local-integrations.md#project-aura-shared-asr-service)
returns operators to this canonical contract.
