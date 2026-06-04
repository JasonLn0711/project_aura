from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_JSON = REPO_ROOT / "reports" / "asr_fuzzy_correction_audit_report.json"
DEFAULT_QUEUE_CSV = REPO_ROOT / "reports" / "asr_fuzzy_manual_review_queue.csv"
DEFAULT_GUIDE_MD = REPO_ROOT / "reports" / "asr_fuzzy_manual_review_guide.md"
DEFAULT_SUMMARY_JSON = REPO_ROOT / "reports" / "asr_fuzzy_manual_review_summary.json"
QUEUE_FIELDS = ("source_file", "category", "original", "corrected", "score", "watch_flag", "review_label", "review_note")
VALID_REVIEW_LABELS = ("ACCEPT", "REJECT", "UNSURE")
WATCH_TERMS = ("Gamma", "Gemma", "Qwen", "iMVS", "iMBS", "IRB", "510(k)", "510k")


def load_audit_report(path: Path = DEFAULT_AUDIT_JSON) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _entry_key(entry: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(entry.get("source_transcript") or entry.get("source_file") or ""),
        str(entry.get("category") or ""),
        str(entry.get("original") or ""),
        str(entry.get("corrected") or ""),
        str(entry.get("score") or ""),
    )


def _has_watch_term(entry: dict[str, Any]) -> bool:
    combined = f"{entry.get('original', '')} {entry.get('corrected', '')}"
    return any(term.lower() in combined.lower() for term in WATCH_TERMS)


def _queue_reason(entry: dict[str, Any]) -> str:
    reasons: list[str] = []
    score = float(entry.get("score") or 0.0)
    category = str(entry.get("category") or "")
    if 85 <= score < 95:
        reasons.append("score_85_to_94_99")
    if category == "people":
        reasons.append("people")
    if category == "medical_terms":
        reasons.append("medical_terms")
    if bool(entry.get("is_alias")):
        reasons.append("alias")
    if _has_watch_term(entry):
        reasons.append("watch_term")
    for reason in entry.get("high_risk_reasons") or []:
        reasons.append(f"high_risk:{reason}")
    return ";".join(dict.fromkeys(reasons))


def build_manual_review_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    accepted = list(report.get("accepted_corrections_all") or [])
    if not accepted:
        accepted = _fallback_accepted_entries(report)

    rows_by_key: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for entry in accepted:
        reason = _queue_reason(entry)
        if not reason:
            continue
        row = {
            "source_file": str(entry.get("source_transcript") or ""),
            "category": str(entry.get("category") or ""),
            "original": str(entry.get("original") or ""),
            "corrected": str(entry.get("corrected") or ""),
            "score": str(entry.get("score") or ""),
            "watch_flag": reason,
            "review_label": "",
            "review_note": "",
        }
        rows_by_key[_entry_key(entry)] = row

    return sorted(
        rows_by_key.values(),
        key=lambda row: (
            row["source_file"],
            row["category"],
            row["original"],
            row["corrected"],
            float(row["score"] or 0.0),
        ),
    )


def _fallback_accepted_entries(report: dict[str, Any]) -> list[dict[str, Any]]:
    sections = (
        "lowest_score_accepted_30",
        "people_accepted_corrections",
        "medical_terms_accepted_corrections",
        "alias_accepted_corrections",
        "watch_term_corrections",
    )
    seen: set[tuple[str, str, str, str, str]] = set()
    entries: list[dict[str, Any]] = []
    for section in sections:
        for entry in report.get(section) or []:
            key = _entry_key(entry)
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
    return entries


def write_queue_csv(rows: list[dict[str, str]], path: Path = DEFAULT_QUEUE_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def build_summary(report: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any]:
    labels = Counter(row["review_label"] for row in rows)
    reason_counts = Counter()
    category_counts = Counter(row["category"] for row in rows)
    for row in rows:
        for reason in filter(None, row["watch_flag"].split(";")):
            reason_counts[reason] += 1
    return {
        "audit_source": "reports/asr_fuzzy_correction_audit_report.json",
        "queue_file": "reports/asr_fuzzy_manual_review_queue.csv",
        "guide_file": "reports/asr_fuzzy_manual_review_guide.md",
        "total_queue_rows": len(rows),
        "review_label_allowed_values": list(VALID_REVIEW_LABELS),
        "review_labels_blank": labels.get("", 0) == len(rows),
        "category_counts": dict(sorted(category_counts.items())),
        "watch_flag_counts": dict(sorted(reason_counts.items())),
        "audit_summary": report.get("summary", {}),
        "contains_raw_context": False,
    }


def write_summary_json(summary: dict[str, Any], path: Path = DEFAULT_SUMMARY_JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_guide(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# ASR Fuzzy Correction Manual Review Guide",
            "",
            "## Purpose",
            "",
            "This package supports manual review before committing the ASR fuzzy correction feature. The review queue contains only correction spans and source transcript filenames. It does not include raw transcript context, raw Gmail content, or raw PDF content.",
            "",
            "## Queue Files",
            "",
            "- `reports/asr_fuzzy_manual_review_queue.csv` is the reviewer work queue.",
            "- `reports/asr_fuzzy_manual_review_summary.json` records queue counts and blank-label status.",
            "- Source audit: `reports/asr_fuzzy_correction_audit_report.json`.",
            "",
            "## Review Labels",
            "",
            "- `ACCEPT`: 明顯 ASR 錯字，且 corrected 是正確專有名詞。",
            "- `REJECT`: 可能改變語意，或 original 本身可成立。",
            "- `UNSURE`: 需要回聽音檔或看上下文。",
            "",
            "Leave `review_label` blank until a human reviewer makes the call. Legal values are `ACCEPT`, `REJECT`, and `UNSURE`.",
            "",
            "## Review Scope",
            "",
            "- Score 85-94.99 accepted corrections.",
            "- All `people` accepted corrections.",
            "- All `medical_terms` accepted corrections.",
            "- All alias corrections.",
            "- Watch cases for Gamma/Gemma/Qwen/iMVS/IRB/510(k).",
            "",
            "## Decision Rule",
            "",
            "- If every reviewed row is `ACCEPT`, proceed to commit.",
            "- If any row is `REJECT`, add the case to a denylist or raise the relevant category threshold, then rerun tests and the audit.",
            "- If any row is `UNSURE`, do not auto-correct that pattern; route it to `manual_review_required` behavior.",
            "",
            "## Current Queue Summary",
            "",
            f"- Total queue rows: {summary['total_queue_rows']}",
            f"- Review labels blank: {summary['review_labels_blank']}",
            f"- Contains raw context: {summary['contains_raw_context']}",
            "",
        ]
    )


def write_guide(summary: dict[str, Any], path: Path = DEFAULT_GUIDE_MD) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_guide(summary), encoding="utf-8")


def build_manual_review_package(
    audit_json: Path = DEFAULT_AUDIT_JSON,
    queue_csv: Path = DEFAULT_QUEUE_CSV,
    guide_md: Path = DEFAULT_GUIDE_MD,
    summary_json: Path = DEFAULT_SUMMARY_JSON,
) -> dict[str, Any]:
    report = load_audit_report(audit_json)
    rows = build_manual_review_rows(report)
    summary = build_summary(report, rows)
    write_queue_csv(rows, queue_csv)
    write_summary_json(summary, summary_json)
    write_guide(summary, guide_md)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a manual review queue for ASR fuzzy corrections.")
    parser.add_argument("--audit-json", type=Path, default=DEFAULT_AUDIT_JSON)
    parser.add_argument("--queue-csv", type=Path, default=DEFAULT_QUEUE_CSV)
    parser.add_argument("--guide-md", type=Path, default=DEFAULT_GUIDE_MD)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY_JSON)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_manual_review_package(args.audit_json, args.queue_csv, args.guide_md, args.summary_json)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
