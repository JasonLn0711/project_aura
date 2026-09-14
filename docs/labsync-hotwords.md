# Local labSync vocabulary

AURA uses faster-whisper to run Breeze-ASR-25. The two vocabulary files below
serve different entry points into that recognizer; they are not different models.

| Owner-local root file | Scope |
| --- | --- |
| `hotwords-labsync-aura.txt` | 61 selected terms for the AURA GUI, CLI, and SDK |
| `hotwords-labsync-all-candidates.txt` | 347 candidates for agenda-specific selection; too long to import together |
| `hotwords-labsync-faster-whisper-223.txt` | 81 terms / 223 actual tokens for direct faster-whisper calls |

These files were prepared locally on September 14, 2026 and are ignored by Git.
They are not shipped with a clone. The owner-local source packet is
`local_outputs/frontend-eval/labsync-hotwords-2026-09-14/`; it contains the original
TXT copies, `candidates.tsv`, tokenizer receipt, and previous preferences.

Five meeting transcripts and the existing domain glossary supplied candidates.
The full candidate list includes 78 name/title entries, including short forms,
full names, and collaborators; this is not a count of lab members. Seven name
entries were selected for the AURA list. Spelling, person identity, and inferred
ASR variants need roster/audio review. Training frequency is unknown; selection
uses domain relevance and suspected recognition ambiguity, not a claim that a
model never learned a term. Full token usage is a requested operating choice,
not evidence of optimal accuracy.

AURA's cached-tokenizer validator counts 188 hotword tokens plus 12 prompt
tokens: exactly 200. The faster-whisper wrapper excludes special tokens and
counts the same text as 184 plus 8. The default prompt is
`The following is a professional meeting record.`. Both checks pass.
Direct faster-whisper retains at most 223 hotword tokens with its current
448-token maximum; prefix disables hotwords. That longer list exceeds AURA's
preflight contract. See the [upstream implementation](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py).

Use the local AURA list from the repository root:

```sh
uv run --no-sync aura record --model breeze --profile light --title labSync --hotwords-file hotwords-labsync-aura.txt
```

The local service and GUI saved the selected vocabulary. New sessions inherit
service preferences; existing or scheduled sessions retain their saved options.
Editing a TXT file does not update saved preferences: import it again or supply
`--hotwords-file`. Changing the prompt requires recounting the combined budget.
Keep raw vocabulary and meeting evidence in owner-local storage.

## Evidence and next gate

[September 14 validation](../artifacts/asr-front-end/2026-09-14/validation.json)
records aggregate checks without names or source transcript contents.
[Punctuation runtime repair](punctuation-runtime.md) owns the dependency fix.
Jason's next gate is roster confirmation and a bounded original-audio comparison
of omitted/incorrect terms and punctuation; no accuracy improvement is claimed.
[Planning day record](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W38/days/2026-09-14.md#aura-hotwords-and-punctuation--first-principle)
owns capacity and acceptance status.
