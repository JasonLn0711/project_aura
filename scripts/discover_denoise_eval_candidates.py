#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma", ".aiff", ".webm", ".mp4"}
TRANSCRIPT_EXTENSIONS = {".txt", ".md"}
DEFAULT_CATEGORY_HINTS = (
    ("lab_sync", "lecture_or_meeting"),
    ("meeting", "lecture_or_meeting"),
    ("sync", "lecture_or_meeting"),
    ("discussion", "lecture_or_meeting"),
    ("seminar", "far_speaker_reverb"),
    ("speech", "far_speaker_reverb"),
    ("withhan", "far_speaker_table_end"),
    ("chat", "far_speaker_overlap"),
)


@dataclass(frozen=True)
class Candidate:
    audio_path: str
    duration_seconds: float | None
    transcript_path: str | None
    transcript_chars: int
    transcript_candidate_only: bool
    suggested_category: str
    prepare_command: str


def shell_quote(path: str | Path) -> str:
    text = str(path)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def probe_duration_seconds(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    return round(duration, 3) if duration > 0 else None


def read_text_length(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").strip())
    except OSError:
        return 0


def transcript_candidates_for_audio(audio_path: Path) -> list[Path]:
    same_dir = audio_path.parent
    stem = audio_path.stem
    candidates = []
    for suffix in TRANSCRIPT_EXTENSIONS:
        candidates.extend(
            [
                same_dir / f"{stem}{suffix}",
                same_dir / f"transcript_{stem}{suffix}",
                same_dir / f"{stem}-transcript{suffix}",
            ]
        )
    candidates.extend(path for path in same_dir.iterdir() if path.suffix.lower() in TRANSCRIPT_EXTENSIONS)
    unique = []
    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not candidate.exists() or not candidate.is_file():
            continue
        seen.add(resolved)
        unique.append(candidate)
    return sorted(unique, key=lambda path: (0 if path.stem == stem or path.stem == f"transcript_{stem}" else 1, len(path.name)))


def best_transcript_for_audio(audio_path: Path) -> tuple[Path | None, int]:
    candidates = transcript_candidates_for_audio(audio_path)
    if not candidates:
        return None, 0
    audio_stem = audio_path.stem.lower()

    def rank(candidate: Path) -> tuple[int, int]:
        stem = candidate.stem.lower()
        suffix = candidate.suffix.lower()
        chars = read_text_length(candidate)
        if suffix == ".txt" and stem == audio_stem:
            return (0, -chars)
        if suffix == ".txt" and stem == f"transcript_{audio_stem}":
            return (1, -chars)
        if suffix == ".txt" and audio_stem in stem:
            return (2, -chars)
        if suffix == ".txt":
            return (3, -chars)
        if audio_stem in stem:
            return (4, -chars)
        return (5, -chars)

    path = min(candidates, key=rank)
    chars = read_text_length(path)
    return path, chars


def suggest_category(audio_path: Path) -> str:
    normalized = str(audio_path).lower().replace(" ", "_")
    for needle, category in DEFAULT_CATEGORY_HINTS:
        if needle in normalized:
            return category
    return "lecture_or_meeting"


def discover_audio_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS)


def build_prepare_command(
    audio_path: Path,
    transcript_path: Path | None,
    eval_dir: Path,
    suggested_category: str,
    start: float,
    duration: float,
    include_transcript_reference: bool = False,
) -> str:
    parts = [
        "python",
        "scripts/prepare_denoise_eval_case.py",
        "--source",
        shell_quote(audio_path),
        "--case-dir",
        shell_quote(eval_dir / suggested_category),
        "--start",
        str(start),
        "--duration",
        str(duration),
    ]
    if transcript_path:
        if include_transcript_reference:
            parts.extend(["--reference-file", shell_quote(transcript_path)])
        else:
            parts.extend(
                [
                    "--note",
                    shell_quote(f"Transcript review source, not a clip-level trusted reference: {transcript_path}"),
                ]
            )
    return " ".join(parts)


def discover_candidates(
    root: Path,
    eval_dir: Path,
    min_duration: float,
    clip_duration: float,
    min_transcript_chars: int,
    limit: int,
    per_folder_limit: int,
    include_transcript_reference: bool = False,
) -> list[Candidate]:
    candidates = []
    for audio_path in discover_audio_files(root):
        duration = probe_duration_seconds(audio_path)
        if duration is not None and duration < min_duration:
            continue
        transcript_path, transcript_chars = best_transcript_for_audio(audio_path)
        if transcript_path and transcript_chars < min_transcript_chars:
            transcript_path = None
        suggested_category = suggest_category(audio_path)
        start = 0.0
        if duration and duration > clip_duration * 2:
            start = max(0.0, round((duration - clip_duration) / 2, 3))
        prepare_command = build_prepare_command(
            audio_path=audio_path,
            transcript_path=transcript_path,
            eval_dir=eval_dir,
            suggested_category=suggested_category,
            start=start,
            duration=clip_duration,
            include_transcript_reference=include_transcript_reference,
        )
        candidates.append(
            Candidate(
                audio_path=str(audio_path),
                duration_seconds=duration,
                transcript_path=str(transcript_path) if transcript_path else None,
                transcript_chars=transcript_chars,
                transcript_candidate_only=bool(transcript_path),
                suggested_category=suggested_category,
                prepare_command=prepare_command,
            )
        )
    candidates.sort(
        key=lambda item: (
            0 if item.transcript_path else 1,
            item.suggested_category,
            -(item.duration_seconds or 0),
            item.audio_path,
        )
    )
    if per_folder_limit <= 0:
        return candidates[:limit]
    selected = []
    folder_counts: dict[str, int] = {}
    for candidate in candidates:
        folder = str(Path(candidate.audio_path).parent)
        if folder_counts.get(folder, 0) >= per_folder_limit:
            continue
        folder_counts[folder] = folder_counts.get(folder, 0) + 1
        selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected


def render_markdown(candidates: list[Candidate], root: Path) -> str:
    lines = [
        "# Denoise Evaluation Candidate Audio",
        "",
        f"- Search root: `{root}`",
        f"- Candidate count: `{len(candidates)}`",
        "- Transcript paths are candidates only; promote them to trusted references only after human review.",
        "- Generated prepare commands add transcript candidates as notes, not as `--reference-file`.",
        "- Transcript contents are intentionally not included in this manifest.",
        "",
        "| # | Category | Duration | Transcript chars | Audio path | Transcript candidate |",
        "| ---: | --- | ---: | ---: | --- | --- |",
    ]
    for index, candidate in enumerate(candidates, start=1):
        duration = "" if candidate.duration_seconds is None else f"{candidate.duration_seconds:.1f}"
        transcript_path = candidate.transcript_path or ""
        lines.append(
            f"| {index} | {candidate.suggested_category} | {duration} | {candidate.transcript_chars} | "
            f"`{candidate.audio_path}` | `{transcript_path}` |"
        )
    if candidates:
        lines.extend(["", "## Prepare Commands", ""])
        for index, candidate in enumerate(candidates, start=1):
            lines.extend([f"### Candidate {index}", "", "```bash", candidate.prepare_command, "```", ""])
    return "\n".join(lines)


def write_outputs(candidates: list[Candidate], output: Path, root: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(candidates, root), encoding="utf-8")
    output.with_suffix(".json").write_text(
        json.dumps([asdict(candidate) for candidate in candidates], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Discover local audio candidates for AURA denoise evaluation.")
    parser.add_argument("--root", default=Path("~/record_jn/record_audio_ubuntu").expanduser(), type=Path)
    parser.add_argument("--eval-dir", default=Path("~/record_jn/aura_eval_audio").expanduser(), type=Path)
    parser.add_argument("--output", default=Path("local_outputs/denoise_eval_candidates/candidates.md"), type=Path)
    parser.add_argument("--min-duration", default=30.0, type=float)
    parser.add_argument("--clip-duration", default=60.0, type=float)
    parser.add_argument("--min-transcript-chars", default=80, type=int)
    parser.add_argument("--limit", default=40, type=int)
    parser.add_argument("--per-folder-limit", default=2, type=int)
    parser.add_argument(
        "--include-transcript-reference",
        action="store_true",
        help="Use transcript candidates as --reference-file. Only use this for clip-level trusted references.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    candidates = discover_candidates(
        root=args.root,
        eval_dir=args.eval_dir,
        min_duration=args.min_duration,
        clip_duration=args.clip_duration,
        min_transcript_chars=args.min_transcript_chars,
        limit=args.limit,
        per_folder_limit=args.per_folder_limit,
        include_transcript_reference=args.include_transcript_reference,
    )
    write_outputs(candidates, args.output, args.root)
    print(f"Wrote {len(candidates)} candidates to {args.output}")
    print(f"JSON: {args.output.with_suffix('.json')}")


if __name__ == "__main__":
    main()
