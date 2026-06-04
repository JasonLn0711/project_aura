from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_postprocess.fuzzy_corrector import (  # noqa: E402
    DEFAULT_GLOSSARY_PATH,
    correct_transcript,
    load_glossary,
)

DEFAULT_REPORT_JSON = REPO_ROOT / "reports" / "asr_fuzzy_correction_audit_report.json"
DEFAULT_REPORT_MD = REPO_ROOT / "reports" / "asr_fuzzy_correction_audit_report.md"
DEFAULT_GENERATED_LOG_DIR = REPO_ROOT / "reports" / "asr_fuzzy_correction_logs"
DEFAULT_TRANSCRIPT_ROOTS = (REPO_ROOT,)
DEFAULT_EXCLUDE_DIRS = {".git", ".venv", "dist", "__pycache__", ".pytest_cache"}
WATCH_TERMS = ("Gamma", "Gemma", "Qwen", "iMVS", "iMBS", "IRB", "510(k)", "510k")
CJK_NEGATION_TERMS = ("不", "沒有", "沒", "未", "無", "否", "非")
EN_NEGATION_RE = re.compile(r"\b(?:not|no|without)\b", re.IGNORECASE)
DATE_RE = re.compile(r"\d{2,4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?")
NUMBER_RE = re.compile(r"\d")


@dataclass(frozen=True)
class AuditEntry:
    source_transcript: str
    original: str
    corrected: str
    score: float
    category: str
    accepted: bool
    is_alias: bool
    high_risk_reasons: tuple[str, ...]
    review_status: str = "accepted"
    review_reason: str = ""

    def to_json(self) -> dict[str, Any]:
        payload = {
            "source_transcript": self.source_transcript,
            "original": self.original,
            "corrected": self.corrected,
            "score": self.score,
            "category": self.category,
            "accepted": self.accepted,
            "is_alias": self.is_alias,
            "high_risk_reasons": list(self.high_risk_reasons),
            "review_status": self.review_status,
            "review_reason": self.review_reason,
        }
        return payload


def repo_relative(path: Path, base: Path = REPO_ROOT) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.name


def load_alias_pairs(glossary_path: Path = DEFAULT_GLOSSARY_PATH) -> set[tuple[str, str, str]]:
    payload = load_glossary(glossary_path)
    aliases = payload.get("aliases") or {}
    pairs: set[tuple[str, str, str]] = set()
    for category, terms in aliases.items():
        if not isinstance(terms, dict):
            continue
        for corrected, raw_aliases in terms.items():
            if not isinstance(raw_aliases, list):
                continue
            for alias in raw_aliases:
                if isinstance(alias, str):
                    pairs.add((category, alias, corrected))
    return pairs


def high_risk_reasons(original: str, corrected: str, category: str) -> tuple[str, ...]:
    reasons: list[str] = []
    combined = f"{original} {corrected}"
    if category in {"people", "medical_terms"}:
        reasons.append(category)
    if DATE_RE.search(combined):
        reasons.append("date")
    elif NUMBER_RE.search(combined):
        reasons.append("number")
    if any(term in combined for term in CJK_NEGATION_TERMS) or EN_NEGATION_RE.search(combined):
        reasons.append("negation")
    return tuple(dict.fromkeys(reasons))


def discover_transcripts(roots: list[Path]) -> list[Path]:
    transcripts: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.txt"):
            if any(part in DEFAULT_EXCLUDE_DIRS for part in path.parts):
                continue
            if any(part.endswith(".egg-info") for part in path.parts):
                continue
            if path.name == "requirements.txt":
                continue
            transcripts.append(path)
    return sorted(set(transcripts), key=lambda item: item.as_posix())


def generate_correction_logs(
    transcript_paths: list[Path],
    output_dir: Path = DEFAULT_GENERATED_LOG_DIR,
    glossary_path: Path = DEFAULT_GLOSSARY_PATH,
    force: bool = False,
) -> list[Path]:
    if force and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    logs: list[Path] = []
    for index, transcript_path in enumerate(transcript_paths, start=1):
        log_path = output_dir / f"{index:03d}_{transcript_path.stem}_correction_log.json"
        if log_path.exists():
            logs.append(log_path)
            continue
        text = transcript_path.read_text(encoding="utf-8", errors="replace")
        result = correct_transcript(text, glossary_path=glossary_path)
        payload = {
            "source_transcript": repo_relative(transcript_path),
            "correction_log": result.correction_log,
        }
        log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        logs.append(log_path)
    return logs


def discover_correction_logs(roots: list[Path]) -> list[Path]:
    logs: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*correction_log.json"):
            if any(part in DEFAULT_EXCLUDE_DIRS for part in path.parts):
                continue
            logs.append(path)
    return sorted(set(logs), key=lambda item: item.as_posix())


def read_log_entries(path: Path) -> tuple[str, list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return path.name, payload
    if isinstance(payload, dict):
        source = str(payload.get("source_transcript") or path.name)
        raw_entries = payload.get("correction_log") or payload.get("corrections") or []
        if not isinstance(raw_entries, list):
            raise ValueError(f"Correction log entries must be a list: {path}")
        return source, raw_entries
    raise ValueError(f"Unsupported correction log payload: {path}")


def build_entries(log_paths: list[Path], alias_pairs: set[tuple[str, str, str]]) -> list[AuditEntry]:
    entries: list[AuditEntry] = []
    for path in log_paths:
        source, raw_entries = read_log_entries(path)
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                continue
            original = str(raw_entry.get("original") or raw_entry.get("span") or "")
            corrected = str(raw_entry.get("corrected") or "")
            category = str(raw_entry.get("category") or "unknown")
            score = float(raw_entry.get("score") or 0.0)
            accepted = bool(raw_entry.get("accepted", True))
            is_alias = (category, original, corrected) in alias_pairs
            entries.append(
                AuditEntry(
                    source_transcript=source,
                    original=original,
                    corrected=corrected,
                    score=score,
                    category=category,
                    accepted=accepted,
                    is_alias=is_alias,
                    high_risk_reasons=high_risk_reasons(original, corrected, category),
                    review_status=str(raw_entry.get("review_status") or ("accepted" if accepted else "rejected")),
                    review_reason=str(raw_entry.get("review_reason") or ""),
                )
            )
    return entries


def score_distribution(entries: list[AuditEntry]) -> dict[str, int]:
    buckets = Counter()
    for entry in entries:
        if entry.score < 85:
            buckets["<85"] += 1
        elif entry.score < 90:
            buckets["85-89.99"] += 1
        elif entry.score < 95:
            buckets["90-94.99"] += 1
        elif entry.score < 100:
            buckets["95-99.99"] += 1
        else:
            buckets["100"] += 1
    return {bucket: buckets[bucket] for bucket in ("<85", "85-89.99", "90-94.99", "95-99.99", "100")}


def top_changes(entries: list[AuditEntry], limit: int = 20) -> list[dict[str, Any]]:
    counts = Counter((entry.original, entry.corrected, entry.category) for entry in entries if entry.accepted)
    return [
        {"original": original, "corrected": corrected, "category": category, "count": count}
        for (original, corrected, category), count in counts.most_common(limit)
    ]


def entry_rows(entries: list[AuditEntry]) -> list[dict[str, Any]]:
    return [entry.to_json() for entry in entries]


def build_report(
    log_paths: list[Path],
    transcript_paths: list[Path],
    generated_log_paths: list[Path],
    entries: list[AuditEntry],
) -> dict[str, Any]:
    accepted = [entry for entry in entries if entry.accepted]
    rejected = [entry for entry in entries if not entry.accepted]
    category_counts = Counter(entry.category for entry in accepted)
    category_counts["aliases"] = sum(1 for entry in accepted if entry.is_alias)
    high_risk = [entry for entry in accepted if entry.high_risk_reasons]
    watch = [
        entry
        for entry in accepted
        if any(term.lower() in f"{entry.original} {entry.corrected}".lower() for term in WATCH_TERMS)
    ]
    low_score_accepted = sorted(accepted, key=lambda entry: (entry.score, entry.source_transcript, entry.original))[:30]
    chinese_low_score = [
        entry
        for entry in accepted
        if 85 <= entry.score <= 90 and re.search(r"[\u3400-\u9fff]", f"{entry.original}{entry.corrected}")
    ]

    return {
        "scope": {
            "correction_log_files_scanned": len(log_paths),
            "transcript_files_scanned": len(transcript_paths),
            "generated_correction_log_files": len(generated_log_paths),
        },
        "summary": {
            "total_corrections": len(entries),
            "accepted_corrections": len(accepted),
            "rejected_candidates": len(rejected),
            "high_risk_manual_review_required": bool(high_risk),
        },
        "category_counts": {key: category_counts[key] for key in sorted(category_counts)},
        "score_distribution": score_distribution(accepted),
        "accepted_corrections_all": entry_rows(accepted),
        "top_20_changes": top_changes(accepted, limit=20),
        "lowest_score_accepted_30": entry_rows(low_score_accepted),
        "rejected_candidates": entry_rows(rejected),
        "denylist_rejections": entry_rows([entry for entry in rejected if entry.review_status == "denylist"]),
        "manual_review_required": entry_rows(
            [entry for entry in rejected if entry.review_status == "manual_review_required"]
        ),
        "people_accepted_corrections": entry_rows([entry for entry in accepted if entry.category == "people"]),
        "medical_terms_accepted_corrections": entry_rows([entry for entry in accepted if entry.category == "medical_terms"]),
        "alias_accepted_corrections": entry_rows([entry for entry in accepted if entry.is_alias]),
        "watch_term_corrections": entry_rows(watch),
        "chinese_score_85_to_90_accepted": entry_rows(chinese_low_score),
        "high_risk_corrections": entry_rows(high_risk),
        "source_transcript_filenames": sorted({entry.source_transcript for entry in entries}),
    }


def markdown_table(rows: list[dict[str, Any]], headers: list[str], limit: int | None = None) -> str:
    selected = rows[:limit] if limit is not None else rows
    if not selected:
        return "_None._\n"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in selected:
        lines.append("| " + " | ".join(str(row.get(header, "")).replace("\n", " ") for header in headers) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    scope = report["scope"]
    category_counts = report["category_counts"]
    score_distribution_rows = [
        {"bucket": bucket, "count": count} for bucket, count in report["score_distribution"].items()
    ]
    category_rows = [{"category": category, "count": count} for category, count in category_counts.items()]

    return "\n".join(
        [
            "# ASR Fuzzy Correction Audit Report",
            "",
            "## Scope",
            "",
            f"- Correction log files scanned: {scope['correction_log_files_scanned']}",
            f"- Transcript files scanned for audit-only logs: {scope['transcript_files_scanned']}",
            f"- Generated audit-only correction logs: {scope['generated_correction_log_files']}",
            "- Raw email and raw PDF content are not read or emitted by this report.",
            "",
            "## Summary",
            "",
            f"- Total corrections/candidates: {summary['total_corrections']}",
            f"- Accepted corrections: {summary['accepted_corrections']}",
            f"- Rejected candidates: {summary['rejected_candidates']}",
            f"- High-risk manual review required: {summary['high_risk_manual_review_required']}",
            "",
            "## Category Counts",
            "",
            markdown_table(category_rows, ["category", "count"]).rstrip(),
            "",
            "## Score Distribution",
            "",
            markdown_table(score_distribution_rows, ["bucket", "count"]).rstrip(),
            "",
            "## Top 20 Changes",
            "",
            markdown_table(report["top_20_changes"], ["original", "corrected", "category", "count"]).rstrip(),
            "",
            "## Lowest Score Accepted 30",
            "",
            markdown_table(
                report["lowest_score_accepted_30"],
                ["source_transcript", "original", "corrected", "score", "category", "is_alias", "high_risk_reasons"],
            ).rstrip(),
            "",
            "## Rejected Candidates",
            "",
            markdown_table(
                report.get("rejected_candidates", []),
                [
                    "source_transcript",
                    "original",
                    "corrected",
                    "score",
                    "category",
                    "review_status",
                    "review_reason",
                ],
            ).rstrip(),
            "",
            "## Manual Review Required",
            "",
            markdown_table(
                report.get("manual_review_required", []),
                [
                    "source_transcript",
                    "original",
                    "corrected",
                    "score",
                    "category",
                    "review_status",
                    "review_reason",
                ],
            ).rstrip(),
            "",
            "## People Accepted Corrections",
            "",
            markdown_table(
                report["people_accepted_corrections"],
                ["source_transcript", "original", "corrected", "score", "category", "is_alias", "high_risk_reasons"],
            ).rstrip(),
            "",
            "## Medical Terms Accepted Corrections",
            "",
            markdown_table(
                report["medical_terms_accepted_corrections"],
                ["source_transcript", "original", "corrected", "score", "category", "is_alias", "high_risk_reasons"],
            ).rstrip(),
            "",
            "## Alias Accepted Corrections",
            "",
            markdown_table(
                report["alias_accepted_corrections"],
                ["source_transcript", "original", "corrected", "score", "category", "is_alias", "high_risk_reasons"],
            ).rstrip(),
            "",
            "## Watch Term Corrections",
            "",
            markdown_table(
                report["watch_term_corrections"],
                ["source_transcript", "original", "corrected", "score", "category", "is_alias", "high_risk_reasons"],
            ).rstrip(),
            "",
            "## Chinese Score 85 To 90 Accepted",
            "",
            markdown_table(
                report["chinese_score_85_to_90_accepted"],
                ["source_transcript", "original", "corrected", "score", "category", "is_alias", "high_risk_reasons"],
            ).rstrip(),
            "",
            "## High Risk Corrections",
            "",
            markdown_table(
                report["high_risk_corrections"],
                ["source_transcript", "original", "corrected", "score", "category", "is_alias", "high_risk_reasons"],
            ).rstrip(),
            "",
        ]
    )


def write_reports(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit ASR fuzzy correction logs without emitting raw transcript text.")
    parser.add_argument("--logs-root", action="append", type=Path, default=[], help="Root containing *_correction_log.json files.")
    parser.add_argument("--transcript-root", action="append", type=Path, default=[], help="Root containing transcript .txt files.")
    parser.add_argument("--generate-logs", action="store_true", help="Generate audit-only correction logs from transcript roots.")
    parser.add_argument("--generated-log-dir", type=Path, default=DEFAULT_GENERATED_LOG_DIR)
    parser.add_argument("--force-regenerate-logs", action="store_true", help="Delete and rebuild generated audit logs first.")
    parser.add_argument("--max-transcripts", type=int, default=None, help="Limit generated audit-only logs for staged review.")
    parser.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY_PATH)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_REPORT_MD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    transcript_roots = args.transcript_root or list(DEFAULT_TRANSCRIPT_ROOTS)
    log_roots = args.logs_root or [args.generated_log_dir, REPO_ROOT]
    transcript_paths = discover_transcripts(transcript_roots) if args.generate_logs else []
    if args.max_transcripts is not None:
        transcript_paths = transcript_paths[: args.max_transcripts]
    generated_log_paths = (
        generate_correction_logs(
            transcript_paths,
            output_dir=args.generated_log_dir,
            glossary_path=args.glossary,
            force=args.force_regenerate_logs,
        )
        if args.generate_logs
        else []
    )
    log_paths = discover_correction_logs(log_roots)
    entries = build_entries(log_paths, alias_pairs=load_alias_pairs(args.glossary))
    report = build_report(log_paths, transcript_paths, generated_log_paths, entries)
    write_reports(report, args.json_out, args.markdown_out)
    print(f"Wrote {args.json_out}")
    print(f"Wrote {args.markdown_out}")
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
