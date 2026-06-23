#!/usr/bin/env python3
import argparse
from pathlib import Path


DEFAULT_CATEGORIES = (
    "quiet_room",
    "fan_or_ac_noise",
    "cafe_or_background_speech",
    "lecture_or_meeting",
    "far_speaker_reverb",
    "far_speaker_low_volume",
    "far_speaker_table_end",
    "far_speaker_overlap",
    "rare_terms",
    "rescue_offline",
    "rescue_offline_reverb",
    "rescue_offline_noise",
)

README_TEMPLATE = """# AURA Denoise Evaluation Workspace

This folder is intentionally outside git because it may contain private meeting audio.

Each case folder should contain:

- `input.wav`: 30-90 seconds of representative audio, preferably 16 kHz or 48 kHz mono WAV.
- `reference.txt`: trusted transcript for CER/WER.
- `rare_terms.txt`: one expected domain term per line.
- `notes.md`: room, microphone, distance, language, and why this clip matters.

Run:

```bash
python scripts/check_denoise_eval_workspace.py \\
  --input-dir {workspace} \\
  --min-cases 10 \\
  --max-reference-chars-per-second 45
python scripts/discover_denoise_eval_candidates.py \\
  --root ~/record_jn/record_audio_ubuntu \\
  --output local_outputs/denoise_eval_candidates/candidates.md
python scripts/prepare_denoise_eval_case.py \\
  --source /path/to/source_recording.wav \\
  --case-dir {workspace}/far_speaker_reverb \\
  --start 120 \\
  --duration 60 \\
  --reference-file /path/to/trusted_reference.txt \\
  --rare-term DeepFilterNet \\
  --rare-term MossFormer
python scripts/evaluate_denoise_backends.py \\
  --input-dir {workspace} \\
  --backends off,noisereduce-light,noisereduce-medium,deepfilternet3,clearvoice,wpe \\
  --model SoybeanMilk/faster-whisper-Breeze-ASR-25 \\
  --output reports/denoise_eval_YYYYMMDD.md

python scripts/gate_denoise_default_promotion.py \\
  --report-json reports/denoise_eval_YYYYMMDD.json \\
  --baseline off \\
  --candidate deepfilternet3 \\
  --min-cases 10
```

The discovery manifest lists transcript files only as review sources. A `reference.txt` should be a clip-level trusted transcript for the selected 30-90 second window, not an unreviewed full-recording transcript. The workspace checker rejects references that are implausibly long for the clip duration.
"""

NOTES_TEMPLATE = """# Evaluation Case Notes

- Room:
- Microphone:
- Approximate speaker distance:
- Language:
- Expected hard terms:
- Capture issue:
- Listening notes:
- Promotion relevance:
"""


def create_case_template(case_dir: Path):
    case_dir.mkdir(parents=True, exist_ok=True)
    for path, content in (
        (case_dir / "notes.md", NOTES_TEMPLATE),
        (case_dir / "reference.txt", ""),
        (case_dir / "rare_terms.txt", ""),
    ):
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def init_workspace(workspace: Path, categories: tuple[str, ...] = DEFAULT_CATEGORIES) -> list[Path]:
    workspace.mkdir(parents=True, exist_ok=True)
    readme = workspace / "README.md"
    if not readme.exists():
        readme.write_text(README_TEMPLATE.format(workspace=workspace), encoding="utf-8")
    created = []
    for category in categories:
        case_dir = workspace / category
        create_case_template(case_dir)
        created.append(case_dir)
    return created


def parse_args():
    parser = argparse.ArgumentParser(description="Initialize an ignored private AURA denoise evaluation workspace.")
    parser.add_argument("--input-dir", default=Path("~/record_jn/aura_eval_audio").expanduser(), type=Path)
    parser.add_argument("--categories", default=",".join(DEFAULT_CATEGORIES))
    return parser.parse_args()


def main():
    args = parse_args()
    categories = tuple(item.strip() for item in args.categories.split(",") if item.strip())
    created = init_workspace(args.input_dir, categories=categories)
    print(f"Initialized {len(created)} evaluation case folders under {args.input_dir}")
    for case_dir in created:
        print(case_dir)


if __name__ == "__main__":
    main()
