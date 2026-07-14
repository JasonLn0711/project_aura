#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aura.audit import analyze_audit_events, read_audit_events, render_audit_markdown  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize local Project AURA audit JSONL files.")
    parser.add_argument("paths", nargs="*", type=Path, help="Audit files or directories; defaults to AURA audit dir.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    events, read_issues = read_audit_events(args.paths or None)
    report = analyze_audit_events(events, read_issues)
    content = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else render_audit_markdown(report)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        try:
            args.output.chmod(0o600)
        except OSError:
            pass
    else:
        print(content, end="" if content.endswith("\n") else "\n")
    return 0 if report["kpis"]["audit_integrity_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
