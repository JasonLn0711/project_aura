#!/usr/bin/env python3
"""Synchronize Project AURA release version files."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_version(raw_version: str) -> str:
    version = raw_version.strip()
    if version.startswith("v"):
        version = version[1:]
    if not SEMVER_PATTERN.fullmatch(version):
        raise ValueError("Version must use MAJOR.MINOR.PATCH, for example 1.6.0")
    return version


def normalize_release_date(raw_date: str | None = None) -> str:
    release_date = (raw_date or date.today().isoformat()).strip()
    if not DATE_PATTERN.fullmatch(release_date):
        raise ValueError("Release date must use YYYY-MM-DD, for example 2026-05-29")
    return release_date


def replace_once(text: str, pattern: re.Pattern[str], replacement: str, file_path: Path) -> str:
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Expected one version match in {file_path}, found {count}")
    return updated


def update_file(file_path: Path, replacements: list[tuple[re.Pattern[str], str]], dry_run: bool) -> bool:
    original = file_path.read_text(encoding="utf-8")
    updated = original
    for pattern, replacement in replacements:
        updated = replace_once(updated, pattern, replacement, file_path)
    if updated == original:
        return False
    if not dry_run:
        file_path.write_text(updated, encoding="utf-8")
    return True


def update_files(
    version: str,
    repo_root: Path = REPO_ROOT,
    release_date: str | None = None,
    dry_run: bool = False,
) -> list[Path]:
    normalized = normalize_version(version)
    normalized_date = normalize_release_date(release_date)
    specs = {
        repo_root / "pyproject.toml": [
            (re.compile(r'(?m)^version = "[^"]+"$'), f'version = "{normalized}"'),
        ],
        repo_root / "src/aura/metadata.py": [
            (re.compile(r'(?m)^__version__ = "[^"]+"$'), f'__version__ = "{normalized}"'),
            (re.compile(r'(?m)^__date__ = "[^"]+"$'), f'__date__ = "{normalized_date}"'),
        ],
        repo_root / "README.md": [
            (
                re.compile(r"(?m)^\| Refactor Version \| `[^`]+` \|$"),
                f"| Refactor Version | `{normalized}` |",
            ),
            (
                re.compile(r"(?m)^\| Current Release Tag \| `v?[^`]+` \|$"),
                f"| Current Release Tag | `v{normalized}` |",
            ),
        ],
    }

    changed = []
    for file_path, replacements in specs.items():
        if update_file(file_path, replacements, dry_run):
            changed.append(file_path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Target version, with or without leading v")
    parser.add_argument("--date", dest="release_date", help="Release update date in YYYY-MM-DD form")
    parser.add_argument("--dry-run", action="store_true", help="Report files that would change")
    args = parser.parse_args()

    changed = update_files(args.version, release_date=args.release_date, dry_run=args.dry_run)
    action = "Would update" if args.dry_run else "Updated"
    if changed:
        for file_path in changed:
            print(f"{action}: {file_path.relative_to(REPO_ROOT)}")
    else:
        print(f"Version already synchronized: {normalize_version(args.version)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
