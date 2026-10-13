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

## Computer vision vocabulary — September 15

The [Traditional Chinese vocabulary](../hotwords-computer_vision_anomaly_detection-260915.txt)
contains 27 complete terms and exactly 223 hotword tokens for direct
faster-whisper calls with the cached Breeze-ASR-25 tokenizer. This generic
technical list is tracked; the labSync lists above retain their owner-local custody.

Jason supplied the candidate terms, their priority order, and the requirement to
fill the token budget with Traditional Chinese first. Selection tested each
complete term in order with `，` separators, accepting it only when the resulting
string fit 223 tokens. The first 27 terms, from `影像處理` through `運動向量`,
filled the budget; later application terms and English abbreviations did not fit.
The supplied conversation is the source for this vocabulary; the referenced
slides were not inspected. Filling the budget verifies format and capacity;
recognition quality still requires an original-audio comparison.

The file is UTF-8, one comma-separated line with a trailing newline. Preserve
its separators when passing it to `model.transcribe`:

```python
from pathlib import Path

hotwords = Path("hotwords-computer_vision_anomaly_detection-260915.txt").read_text(encoding="utf-8").strip()
segments, info = model.transcribe(audio, language="zh", hotwords=hotwords)
```

Use an already initialized Breeze model and an authorized audio input. Leave
`prefix` unset for hotwords to participate. No model/provider, saved vocabulary,
recording worker, or release version was changed during preparation.

[Validation receipt](../artifacts/asr-front-end/2026-09-15/validation.json)
records the file/tokenizer hashes, faster-whisper version, and actual `get_prompt`
check. Reproduce it without loading model weights or running audio inference:

```sh
.venv/bin/python artifacts/asr-front-end/2026-09-15/verify_hotwords.py
```

AURA's cached-tokenizer validator counts this text as 227 tokens before any
prompt, so the 200-token combined preflight rejects it. For AURA import, prepare
a shorter copy against the actual prompt and validator, then re-import it or
pass its path explicitly. Keep this direct-call file at its requested 223-token
budget. The [shared validator](../src/aura/asr/hotwords.py) owns AURA's contract;
the [upstream v1.2.1 implementation](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py)
owns direct-call truncation and prefix behavior.

FIRST PRINCIPLE: the scarce resources are decoder context, operator attention,
and trustworthy recognition evidence. AURA owns the vocabulary, reproducible
check and runtime contract; Planning owns status, capacity and the next gate.
Jason's next actual use determines whether to use direct faster-whisper or
prepare an AURA-sized copy, followed by a bounded original-audio comparison of
missed or incorrect terms. This creates no new scheduled block or accuracy claim.
The [Planning day decision](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W38/days/2026-09-15.md#aura-computer-vision-hotwords--first-principle)
and [project locator](https://github.com/JasonLn0711/planning-everything-track/blob/main/data/projects/2026-05-project-aura-refactor.md#2026-09-15-computer-vision-hotwords)
provide the return route for weekly review and operator handoff.
