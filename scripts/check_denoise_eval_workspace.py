#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CaseCheck:
    category: str
    case_dir: str
    input_path: str | None
    has_input: bool
    duration_seconds: float | None
    has_reference: bool
    reference_chars: int
    rare_term_count: int
    warnings: list[str]
    errors: list[str]

    @property
    def ready(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class WorkspaceCheck:
    input_dir: str
    ready: bool
    ready_case_count: int
    case_count: int
    min_cases: int
    cases: list[CaseCheck]
    errors: list[str]
    warnings: list[str]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def count_rare_terms(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


def probe_duration_seconds(input_path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not input_path.exists():
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    return round(duration, 3) if duration > 0 else None


def check_case(case_dir: Path, min_duration: float, max_duration: float, max_reference_chars_per_second: float) -> CaseCheck:
    warnings = []
    errors = []
    input_path = case_dir / "input.wav"
    reference_text = read_text(case_dir / "reference.txt")
    rare_term_count = count_rare_terms(case_dir / "rare_terms.txt")
    duration = probe_duration_seconds(input_path)

    if not input_path.exists():
        errors.append("missing input.wav")
    elif duration is None:
        warnings.append("could not probe audio duration")
    else:
        if duration < min_duration:
            warnings.append(f"duration {duration:.1f}s is shorter than recommended {min_duration:.1f}s")
        if duration > max_duration:
            warnings.append(f"duration {duration:.1f}s is longer than recommended {max_duration:.1f}s")

    if not reference_text:
        errors.append("missing trusted reference.txt for CER/WER")
    elif duration is not None:
        chars_per_second = len(reference_text) / duration
        if chars_per_second > max_reference_chars_per_second:
            errors.append(
                "reference.txt is too long for the clip duration "
                f"({chars_per_second:.1f} chars/s); use a clip-level trusted reference"
            )
    if rare_term_count == 0:
        warnings.append("rare_terms.txt is empty; rare-term hit rate will be uninformative")

    return CaseCheck(
        category=case_dir.name,
        case_dir=str(case_dir),
        input_path=str(input_path) if input_path.exists() else None,
        has_input=input_path.exists(),
        duration_seconds=duration,
        has_reference=bool(reference_text),
        reference_chars=len(reference_text),
        rare_term_count=rare_term_count,
        warnings=warnings,
        errors=errors,
    )


def discover_case_dirs(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        return []
    return sorted(path for path in input_dir.iterdir() if path.is_dir())


def check_workspace(
    input_dir: Path,
    min_cases: int = 10,
    min_duration: float = 30.0,
    max_duration: float = 90.0,
    max_reference_chars_per_second: float = 45.0,
) -> WorkspaceCheck:
    cases = [
        check_case(case_dir, min_duration, max_duration, max_reference_chars_per_second)
        for case_dir in discover_case_dirs(input_dir)
    ]
    ready_cases = [case for case in cases if case.ready]
    errors = []
    warnings = []
    if not input_dir.exists():
        errors.append(f"input directory does not exist: {input_dir}")
    if len(ready_cases) < min_cases:
        errors.append(f"ready case count {len(ready_cases)} is below required minimum {min_cases}")
    for case in cases:
        warnings.extend(f"{case.category}: {warning}" for warning in case.warnings)
    return WorkspaceCheck(
        input_dir=str(input_dir),
        ready=not errors,
        ready_case_count=len(ready_cases),
        case_count=len(cases),
        min_cases=min_cases,
        cases=cases,
        errors=errors,
        warnings=warnings,
    )


def render_markdown(check: WorkspaceCheck) -> str:
    lines = [
        "# Denoise Evaluation Workspace Check",
        "",
        f"- Input dir: `{check.input_dir}`",
        f"- Ready: `{check.ready}`",
        f"- Ready cases: `{check.ready_case_count}/{check.min_cases}`",
        "",
        "| Category | Ready | Duration | Reference chars | Rare terms | Errors | Warnings |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for case in check.cases:
        duration = "" if case.duration_seconds is None else f"{case.duration_seconds:.1f}"
        errors = "; ".join(case.errors)
        warnings = "; ".join(case.warnings)
        lines.append(
            f"| {case.category} | {case.ready} | {duration} | {case.reference_chars} | "
            f"{case.rare_term_count} | {errors} | {warnings} |"
        )
    if check.errors:
        lines.extend(["", "## Blocking Errors"])
        lines.extend(f"- {error}" for error in check.errors)
    if check.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in check.warnings)
    lines.append("")
    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description="Check readiness of a private AURA denoise evaluation workspace.")
    parser.add_argument("--input-dir", default=Path("~/record_jn/aura_eval_audio").expanduser(), type=Path)
    parser.add_argument("--min-cases", default=10, type=int)
    parser.add_argument("--min-duration", default=30.0, type=float)
    parser.add_argument("--max-duration", default=90.0, type=float)
    parser.add_argument("--max-reference-chars-per-second", default=45.0, type=float)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    return parser.parse_args()


def main():
    args = parse_args()
    check = check_workspace(
        input_dir=args.input_dir,
        min_cases=args.min_cases,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        max_reference_chars_per_second=args.max_reference_chars_per_second,
    )
    if args.json:
        print(json.dumps(asdict(check), ensure_ascii=False, indent=2))
    else:
        print(render_markdown(check))
    raise SystemExit(0 if check.ready else 1)


if __name__ == "__main__":
    main()
