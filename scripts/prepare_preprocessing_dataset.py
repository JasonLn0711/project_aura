#!/usr/bin/env python3
"""Prepare the local-only hybrid corpus without running ASR."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

TIMESTAMP = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\]\s*(?:\[seg-[^]]+\]\s*)?(.*)$")
SRT_TIMESTAMP = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})$"
)
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".mp4"}
DATASET_ID = "DATA-AURA-PREPROCESS-v2"


@dataclass(frozen=True)
class Candidate:
    category: str
    audio: Path
    transcript: Path
    start: float
    end: float
    text: str


def parse_timestamped_text(text: str) -> list[tuple[int, str]]:
    entries = []
    for line in text.splitlines():
        match = TIMESTAMP.match(line.strip())
        if match and match.group(4).strip():
            hours, minutes, seconds = map(int, match.groups()[:3])
            entries.append((hours * 3600 + minutes * 60 + seconds, match.group(4).strip()))
    return entries


def parse_review_srt(text: str) -> list[tuple[float, float, str]]:
    segments = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = SRT_TIMESTAMP.match(lines[timing_index])
        value = " ".join(lines[timing_index + 1 :]).strip()
        if not match or not value:
            continue
        parts = list(map(int, match.groups()))
        start = parts[0] * 3600 + parts[1] * 60 + parts[2] + parts[3] / 1000
        end = parts[4] * 3600 + parts[5] * 60 + parts[6] + parts[7] / 1000
        if end > start:
            segments.append((start, end, value))
    return segments


def category_for(path: Path) -> str:
    name = str(path).lower()
    if "withhan" in name:
        return "overlap_conversation"
    if any(token in name for token in ("taf", "voiss", "labsync", "withlab")):
        return "technical_meeting"
    if any(token in name for token in ("演講", "ep", "speech", "seminar")):
        return "lecture_or_media"
    return "general_meeting"


def media_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        check=True,
        text=True,
    )
    return float(result.stdout.strip())


def best_window(
    segments: list[tuple[float, float, str]],
    duration: float,
    candidate_starts: list[float] | None = None,
) -> tuple[float, float, str] | None:
    windows = []
    starts = candidate_starts or [int(segment[0]) for segment in segments]
    for start in starts:
        if start + 60 > duration:
            continue
        selected = [segment for segment in segments if start <= segment[0] < start + 60]
        if not selected:
            continue
        end = max(segment[1] for segment in selected)
        if end > duration:
            continue
        text = " ".join(segment[2] for segment in selected)
        if len(text) >= 50:
            windows.append((len(text), start, end, text))
    if not windows:
        return None
    _, start, end, text = max(windows, key=lambda item: (item[0], -item[1]))
    return start, end, text


def discover(root: Path, pinned_starts: dict[Path, float] | None = None) -> list[Candidate]:
    candidates = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")):
        transcripts = sorted(folder.glob("*_final.txt"), key=lambda path: ("transcript_" in path.name, len(path.name)))
        if not transcripts:
            continue
        audio_files = sorted(
            (
                path
                for path in folder.rglob("*")
                if path.is_file()
                and path.suffix.lower() in AUDIO_EXTENSIONS
                and not any(token in path.stem.lower() for token in ("_system", "_microphone", "part"))
            ),
            key=lambda path: (path.suffix.lower() != ".m4a", len(path.parts), len(path.name)),
        )
        if not audio_files:
            continue
        audio = audio_files[0].resolve()
        if pinned_starts is not None and audio not in pinned_starts:
            continue
        try:
            entries = parse_timestamped_text(transcripts[0].read_text(encoding="utf-8", errors="ignore"))
            duration = media_duration(audio_files[0])
            review_srt = transcripts[0].with_name(transcripts[0].name.removesuffix("_final.txt") + "_review.srt")
            if review_srt.is_file():
                segments = parse_review_srt(review_srt.read_text(encoding="utf-8", errors="ignore"))
            else:
                segments = [
                    (start, entries[index + 1][0] if index + 1 < len(entries) else duration, value)
                    for index, (start, value) in enumerate(entries)
                ]
            if pinned_starts is not None:
                pinned_start = pinned_starts[audio]
                earlier_starts = sorted(
                    {start for start, _, _ in segments if start < pinned_start},
                    reverse=True,
                )
                starts = [pinned_start, *earlier_starts]
            else:
                starts = [start for start, _ in entries]
            window = best_window(segments, duration, starts)
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        if window:
            candidates.append(Candidate(category_for(folder), audio, transcripts[0], window[0], window[1], window[2]))
    return candidates


def select(candidates: list[Candidate], limit: int = 12) -> list[Candidate]:
    ordered = sorted(candidates, key=lambda item: hashlib.sha256(str(item.audio).encode()).hexdigest())
    selected = []
    for category in ("overlap_conversation", "technical_meeting", "lecture_or_media", "general_meeting"):
        selected.extend(item for item in ordered if item.category == category and item not in selected and len([x for x in selected if x.category == category]) < 3)
    selected.extend(item for item in ordered if item not in selected and len(selected) < limit)
    return selected[:limit]


def private_write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def rare_terms(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z0-9._+-]{2,}", text)))[:20]


def prepare(root: Path, output: Path, base_dataset: Path | None = None) -> dict:
    if output.exists():
        raise FileExistsError(f"dataset already exists: {output}")
    output.mkdir(parents=True, mode=0o700)
    manifest = {
        "datasetId": DATASET_ID,
        "derivedFrom": "DATA-AURA-PREPROCESS-v1",
        "preparedOn": date.today().isoformat(),
        "asrExecuted": False,
        "cases": [],
    }

    control_root = root / "artifacts/asr-benchmark/2026-07-13-common-voice24-minimum"
    for line in (control_root / "source_manifest.jsonl").read_text(encoding="utf-8").splitlines():
        source = json.loads(line)
        case_dir = output / source["case_id"]
        case_dir.mkdir(mode=0o700)
        shutil.copyfile(control_root / source["audio_path"], case_dir / "input.wav")
        (case_dir / "input.wav").chmod(0o600)
        private_write(case_dir / "ground-truth.txt", source["reference"] + "\n")
        private_write(case_dir / "rare-terms.txt", "")
        case = {"caseId": source["case_id"], "sourceClass": "public_clean_control", "gtStatus": "CONTROL_REFERENCE"}
        private_write(case_dir / "case.json", json.dumps(case, ensure_ascii=False, indent=2) + "\n")
        manifest["cases"].append(case)

    if base_dataset is not None:
        base_manifest = json.loads((base_dataset / "manifest.json").read_text(encoding="utf-8"))
        base_cases = [case for case in base_manifest["cases"] if case["sourceClass"] == "private_local"]
        pinned_starts = {
            Path(case["sourceAudio"]).resolve(): float(case["clipStartSeconds"])
            for case in base_cases
        }
        discovered = {candidate.audio: candidate for candidate in discover(root, pinned_starts)}
        missing = [str(path) for path in pinned_starts if path not in discovered]
        if missing:
            raise RuntimeError(f"could not reproduce {len(missing)} private source windows")
        chosen = [discovered[Path(case["sourceAudio"]).resolve()] for case in base_cases]
    else:
        base_cases = []
        chosen = select(discover(root))
    if len(chosen) < 12:
        raise RuntimeError(f"only {len(chosen)} eligible private recordings were found")
    for index, candidate in enumerate(chosen, 1):
        case_id = base_cases[index - 1]["caseId"] if base_cases else f"private-{index:02d}"
        case_dir = output / case_id
        case_dir.mkdir(mode=0o700)
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-y", "-ss", str(candidate.start),
                "-t", str(candidate.end - candidate.start), "-i", str(candidate.audio),
                "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(case_dir / "input.wav"),
            ],
            check=True,
        )
        (case_dir / "input.wav").chmod(0o600)
        private_write(case_dir / "ground-truth.draft.txt", candidate.text + "\n")
        private_write(case_dir / "rare-terms.draft.txt", "\n".join(rare_terms(candidate.text)) + "\n")
        case = {
            "caseId": case_id,
            "sourceClass": "private_local",
            "category": candidate.category,
            "clipStartSeconds": round(candidate.start, 3),
            "clipEndSeconds": round(candidate.end, 3),
            "clipDurationSeconds": round(candidate.end - candidate.start, 3),
            "gtStatus": "DRAFT_GT",
            "sourceAudio": str(candidate.audio),
            "sourceTranscript": str(candidate.transcript),
        }
        if base_cases and candidate.start != float(base_cases[index - 1]["clipStartSeconds"]):
            case["anchorAdjustment"] = {
                "fromSeconds": float(base_cases[index - 1]["clipStartSeconds"]),
                "toSeconds": round(candidate.start, 3),
                "reason": "nearest_earlier_complete_source_window",
            }
        private_write(case_dir / "case.json", json.dumps(case, ensure_ascii=False, indent=2) + "\n")
        manifest["cases"].append(case)

    private_write(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(f"~/.local/share/project-aura-next/studies/STUDY-AURA-NEXT-001/datasets/{DATASET_ID}").expanduser(),
    )
    parser.add_argument(
        "--base-dataset",
        type=Path,
        default=Path(
            "~/.local/share/project-aura-next/studies/STUDY-AURA-NEXT-001/datasets/DATA-AURA-PREPROCESS-v1"
        ).expanduser(),
    )
    args = parser.parse_args()
    manifest = prepare(
        args.root.resolve(),
        args.output.expanduser().resolve(),
        args.base_dataset.expanduser().resolve(),
    )
    print(json.dumps({"dataset": manifest["datasetId"], "caseCount": len(manifest["cases"]), "asrExecuted": False}))


if __name__ == "__main__":
    main()
