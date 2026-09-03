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
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".mp4"}


@dataclass(frozen=True)
class Candidate:
    category: str
    audio: Path
    transcript: Path
    start: int
    text: str


def parse_timestamped_text(text: str) -> list[tuple[int, str]]:
    entries = []
    for line in text.splitlines():
        match = TIMESTAMP.match(line.strip())
        if match and match.group(4).strip():
            hours, minutes, seconds = map(int, match.groups()[:3])
            entries.append((hours * 3600 + minutes * 60 + seconds, match.group(4).strip()))
    return entries


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


def best_window(entries: list[tuple[int, str]], duration: float) -> tuple[int, str] | None:
    windows = []
    for start, _ in entries:
        if start + 30 > duration:
            continue
        text = " ".join(value for timestamp, value in entries if start <= timestamp < start + 60)
        if len(text) >= 50:
            windows.append((len(text), start, text))
    if not windows:
        return None
    _, start, text = max(windows, key=lambda item: (item[0], -item[1]))
    return start, text


def discover(root: Path) -> list[Candidate]:
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
        try:
            entries = parse_timestamped_text(transcripts[0].read_text(encoding="utf-8", errors="ignore"))
            window = best_window(entries, media_duration(audio_files[0]))
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        if window:
            candidates.append(Candidate(category_for(folder), audio_files[0], transcripts[0], window[0], window[1]))
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


def prepare(root: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"dataset already exists: {output}")
    output.mkdir(parents=True, mode=0o700)
    manifest = {"datasetId": "DATA-AURA-PREPROCESS-v1", "preparedOn": date.today().isoformat(), "asrExecuted": False, "cases": []}

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

    chosen = select(discover(root))
    if len(chosen) < 12:
        raise RuntimeError(f"only {len(chosen)} eligible private recordings were found")
    for index, candidate in enumerate(chosen, 1):
        case_id = f"private-{index:02d}"
        case_dir = output / case_id
        case_dir.mkdir(mode=0o700)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", str(candidate.start), "-t", "60", "-i", str(candidate.audio), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(case_dir / "input.wav")],
            check=True,
        )
        (case_dir / "input.wav").chmod(0o600)
        private_write(case_dir / "ground-truth.draft.txt", candidate.text + "\n")
        private_write(case_dir / "rare-terms.draft.txt", "\n".join(rare_terms(candidate.text)) + "\n")
        case = {
            "caseId": case_id,
            "sourceClass": "private_local",
            "category": candidate.category,
            "clipStartSeconds": candidate.start,
            "clipDurationSeconds": 60,
            "gtStatus": "DRAFT_GT",
            "sourceAudio": str(candidate.audio),
            "sourceTranscript": str(candidate.transcript),
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
        default=Path("~/.local/share/project-aura-next/studies/STUDY-AURA-NEXT-001/datasets/DATA-AURA-PREPROCESS-v1").expanduser(),
    )
    args = parser.parse_args()
    manifest = prepare(args.root.resolve(), args.output.expanduser().resolve())
    print(json.dumps({"dataset": manifest["datasetId"], "caseCount": len(manifest["cases"]), "asrExecuted": False}))


if __name__ == "__main__":
    main()
