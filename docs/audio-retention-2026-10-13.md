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
splitter M4As remain retained. No service database cleanup was applied: the running
service held its lock. Private filenames, session identifiers, transcripts and raw
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

After the current recording and other active jobs finish, stop the service normally,
run the guide's offline preview and apply commands from the published source, then
restart the service and reopen clients. Check a short recording, M4A playback/export,
current audio locators and absence of eligible WAV/MP3 duplicates. A missing-source
legacy package requires locator inspection before any deletion. This is the next
operational gate; deployment and that acceptance check remain pending.

Jason supplied the retention and continuity decisions. Codex implemented, verified,
cleaned eligible legacy packages and prepared the publication. Human time was not
reported. This maintenance creates no new learning quota or recurring schedule.

[Planning day](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W42/days/2026-10-13.md#aura-m4a-retention)
links the [project locator](https://github.com/JasonLn0711/planning-everything-track/blob/main/data/projects/2026-05-project-aura-refactor.md#aura-m4a-retention)
and [W42 capacity](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W42/weekly-plan.md#aura-m4a-retention).
The [integration index](https://github.com/JasonLn0711/planning-everything-track/blob/main/docs/14-local-integrations.md#project-aura-shared-asr-service)
returns operators to this canonical contract.
