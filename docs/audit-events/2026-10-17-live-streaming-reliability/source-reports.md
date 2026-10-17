# Source reports — live streaming reliability

Source: user messages in the implementation and troubleshooting conversation on October 17, 2026. The following are verbatim request, error, command, and response excerpts. They preserve the incident-bearing text; this is not a full conversation export. Terminal artwork and routine package-manager output are not reproduced. Interpretation belongs in [the audit event](audit-event.md).

## Original request and implementation authorization

> Please try fix all the issues when transcribing live streaming, and optimizing for dgx and must be workable for other amd64-cpu devices.

> Implement the plan.

The earlier agreed scope, retained in the conversation summary, was Linux Rust capture, NVIDIA-only ASR, ARM64/amd64 CPU clients for remote capture/control, phrase-by-phrase output, local recording through outages, reconnect/replay, public-audio GPU validation, and amd64 CI with physical acceptance pending. This scope paragraph is a summary, not a verbatim quotation of the earlier planning exchange.

## Report 1: architecture and stale service

```text
jnlngx10@gx10-5f94:~/phd-research/repos/project_aura$ sudo snap install spotify
[sudo] password for jnlngx10:
error: snap "spotify" is not available on stable for this architecture (arm64) but exists on other
       architectures (amd64).
jnlngx10@gx10-5f94:~/phd-research/repos/project_aura$ uv run aura
AURA v1.18.0 · shared transcription workspace
```

```text
Connected: local service
Service version: 1.18.0 · matched
ASR: Breeze · loaded
```

```text
❯ /record
AURA: Upgrade the service before using Rust capture
```

The Spotify failure was supplied alongside the AURA failure. It was not an AURA defect, and no Spotify installation or architecture workaround was performed.

## Report 2: utility installation and missing microphone

```text
jnlngx10@gx10-5f94:~/phd-research/repos/project_aura$ sudo apt update && sudo apt install -y pulseaudio-utils
```

```text
The following NEW packages will be installed:
  pulseaudio-utils
0 upgraded, 1 newly installed, 0 to remove and 4 not upgraded.
Need to get 72.0 kB of archives.
After this operation, 545 kB of additional disk space will be used.
```

```text
Setting up pulseaudio-utils (1:16.1+dfsg1-2ubuntu10.1) ...
```

```text
jnlngx10@gx10-5f94:~/phd-research/repos/project_aura$ uv run --no-sync aura
```

```text
❯ /record
be0aaf45-d179-43b0-917b-7f7426ca7604  starting  Meeting
[recording] Meeting · be0aaf45-d179-43b0-917b-7f7426ca7604
[failed] Meeting · be0aaf45-d179-43b0-917b-7f7426ca7604
AURA: Requested system_microphone capture sources are unavailable
```

## Report 3: audio saved without live text

> No live streaming actually work out there:

```text
❯ /record
AURA: No microphone is available. Connect or enable a microphone, or use /record --source system to capture desktop audio only.
```

```text
❯ /record --source system
8be61abc-840e-4877-ace3-57fce22e312c  starting  Meeting
[recording] Meeting · 8be61abc-840e-4877-ace3-57fce22e312c
```

```text
❯ /stop
8be61abc-840e-4877-ace3-57fce22e312c  stopping  Meeting
[exporting] Meeting · 8be61abc-840e-4877-ace3-57fce22e312c
[ready] Meeting · 8be61abc-840e-4877-ace3-57fce22e312c
```

```text
❯ /files
Meeting · ready · 8be61abc-840e-4877-ace3-57fce22e312c
Folder (local service): /home/jnlngx10/.local/share/project-aura/sessions/8be61abc-840e-4877-ace3-57fce22e312c
transcript.txt: /home/jnlngx10/.local/share/project-aura/sessions/8be61abc-840e-4877-ace3-57fce22e312c/transcript.txt
live.txt: /home/jnlngx10/.local/share/project-aura/sessions/8be61abc-840e-4877-ace3-57fce22e312c/live.txt
m4a: /home/jnlngx10/.local/share/project-aura/sessions/8be61abc-840e-4877-ace3-57fce22e312c/8be61abc-840e-4877-ace3-57fce22e312c.m4a
Export from the CLI workspace: /export 8be61abc-840e-4877-ace3-57fce22e312c --format txt --output "./transcript.txt"
```

## User clarification, preserved in order

Question: “What was playing during that 49-second recording? The saved audio contains a signal, but speech detection accepted zero frames.”

> Spoken dialogue or a livestream

Question: “What language was the dialogue, and which app or website was playing it? Your session used Chinese recognition; the repaired detector passes audio to ASR, but the short-chunk replay produced very little text.”

> A brave browser website was playing it.

Question: “Please play the Brave video again and leave it playing while I check its audio routing. What language is it speaking?”

> American Enggggggggggggggggggggggggggggggggggggggggggggggggggggggglish

## Documentation authorization

> Please take full notes on all the audit logs and all the fix you have done.

## Source custody

User audio, recognized speech, native spools, SQLite event bodies, and full runtime logs remain owner-local. The audit includes their inventory and hashes without copying their content into versioned documentation. Public-audio receipts remain in the existing repository evidence packet. No passwords, tokens, or connection JSON files are included in the archive.
