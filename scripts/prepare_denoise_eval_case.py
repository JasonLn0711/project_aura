#!/usr/bin/env python3
import argparse
import shutil
import subprocess
from pathlib import Path


def read_reference_text(reference_text: str | None, reference_file: Path | None) -> str | None:
    if reference_text and reference_file:
        raise ValueError("use either --reference-text or --reference-file, not both")
    if reference_text:
        return reference_text.strip()
    if reference_file:
        return reference_file.read_text(encoding="utf-8").strip()
    return None


def write_if_requested(path: Path, content: str | None, overwrite: bool):
    if content is None:
        return
    if path.exists() and path.read_text(encoding="utf-8").strip() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")
    path.write_text(content.strip() + "\n", encoding="utf-8")


def append_notes(case_dir: Path, notes: list[str]):
    if not notes:
        return
    notes_path = case_dir / "notes.md"
    existing = notes_path.read_text(encoding="utf-8") if notes_path.exists() else "# Evaluation Case Notes\n"
    extra = "\n".join(f"- {note.strip()}" for note in notes if note.strip())
    if not extra:
        return
    notes_path.write_text(existing.rstrip() + "\n\n## Preparation Notes\n" + extra + "\n", encoding="utf-8")


def prepare_eval_case(
    source: Path,
    case_dir: Path,
    start: float,
    duration: float,
    sample_rate: int,
    channels: int,
    reference_text: str | None = None,
    rare_terms: list[str] | None = None,
    notes: list[str] | None = None,
    overwrite: bool = False,
) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to prepare evaluation clips")
    if not source.exists():
        raise FileNotFoundError(source)
    if duration <= 0:
        raise ValueError("duration must be positive")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if channels <= 0:
        raise ValueError("channels must be positive")

    case_dir.mkdir(parents=True, exist_ok=True)
    output_path = case_dir / "input.wav"
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"{output_path} already exists; pass --overwrite to replace it")

    command = [
        ffmpeg,
        "-y" if overwrite else "-n",
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-i",
        str(source),
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-sample_fmt",
        "s16",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)

    write_if_requested(case_dir / "reference.txt", reference_text, overwrite=overwrite)
    if rare_terms:
        write_if_requested(case_dir / "rare_terms.txt", "\n".join(rare_terms), overwrite=overwrite)
    append_notes(
        case_dir,
        [
            f"Source: {source}",
            f"Clip: start={start:.3f}s, duration={duration:.3f}s, sample_rate={sample_rate}, channels={channels}",
            *(notes or []),
        ],
    )
    return output_path


def parse_args():
    parser = argparse.ArgumentParser(description="Prepare one AURA denoise evaluation case from a source recording.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--start", default=0.0, type=float)
    parser.add_argument("--duration", default=60.0, type=float)
    parser.add_argument("--sample-rate", default=48000, type=int)
    parser.add_argument("--channels", default=1, type=int)
    parser.add_argument("--reference-text", help="Clip-level trusted reference text for CER/WER.")
    parser.add_argument("--reference-file", type=Path, help="Clip-level trusted reference file for CER/WER.")
    parser.add_argument("--rare-term", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    reference_text = read_reference_text(args.reference_text, args.reference_file)
    output_path = prepare_eval_case(
        source=args.source,
        case_dir=args.case_dir,
        start=args.start,
        duration=args.duration,
        sample_rate=args.sample_rate,
        channels=args.channels,
        reference_text=reference_text,
        rare_terms=args.rare_term,
        notes=args.note,
        overwrite=args.overwrite,
    )
    print(output_path)


if __name__ == "__main__":
    main()
