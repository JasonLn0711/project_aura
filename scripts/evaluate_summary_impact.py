from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_postprocess.fuzzy_corrector import DEFAULT_GLOSSARY_PATH, load_glossary  # noqa: E402

DEFAULT_ARTIFACT_ROOTS = (REPO_ROOT,)
DEFAULT_REPORT_JSON = REPO_ROOT / "reports" / "asr_correction_summary_impact_report.json"
DEFAULT_REPORT_MD = REPO_ROOT / "reports" / "asr_correction_summary_impact_report.md"
EXCLUDE_DIRS = {".git", ".venv", "dist", "__pycache__", ".pytest_cache"}
SUMMARY_MARKER = "===== LLM Summary ====="
EVALUATED_CATEGORIES = ("organizations", "people", "technical_terms", "medical_terms", "regulatory_terms")
REGULATORY_TERMS = ("510(k)", "510k", "FDA", "TFDA", "IRB", "SaMD")


@dataclass(frozen=True)
class ArtifactSet:
    file_id: str
    raw_transcript: Path
    corrected_transcript: Path
    correction_log: Path
    raw_summary: Path | None
    corrected_summary: Path | None


def repo_relative(path: Path, base: Path = REPO_ROOT) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.name


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts)


def read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_summary_text(text: str) -> str:
    if SUMMARY_MARKER in text:
        return text.split(SUMMARY_MARKER, 1)[1]
    return text


def summary_candidate_paths(base_path: Path) -> list[Path]:
    parent = base_path.parent
    stem = base_path.stem
    if stem.endswith("_raw"):
        base = stem[: -len("_raw")]
        return [
            parent / f"{base}_raw_summary.txt",
            parent / f"{base}_summary_raw.txt",
            parent / f"{base}_summary.txt",
            parent / f"{base}_raw_summary.json",
        ]
    if stem.endswith("_corrected"):
        base = stem[: -len("_corrected")]
        return [
            parent / f"{base}_corrected_summary.txt",
            parent / f"{base}_summary_corrected.txt",
            parent / f"{base}_summary.txt",
            parent / f"{base}_corrected_summary.json",
        ]
    return []


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def discover_artifact_sets(roots: list[Path]) -> list[ArtifactSet]:
    raw_files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*_raw.txt"):
            if not is_excluded(path):
                raw_files.append(path)

    artifact_sets: list[ArtifactSet] = []
    for raw_path in sorted(set(raw_files), key=lambda item: item.as_posix()):
        base = raw_path.with_name(raw_path.stem[: -len("_raw")])
        corrected_path = raw_path.with_name(f"{base.name}_corrected.txt")
        log_path = raw_path.with_name(f"{base.name}_correction_log.json")
        if not corrected_path.exists() or not log_path.exists():
            continue
        artifact_sets.append(
            ArtifactSet(
                file_id=repo_relative(base),
                raw_transcript=raw_path,
                corrected_transcript=corrected_path,
                correction_log=log_path,
                raw_summary=first_existing(summary_candidate_paths(raw_path)),
                corrected_summary=first_existing(summary_candidate_paths(corrected_path)),
            )
        )
    return artifact_sets


def load_domain_terms(glossary_path: Path = DEFAULT_GLOSSARY_PATH) -> dict[str, list[str]]:
    glossary = load_glossary(glossary_path)
    terms: dict[str, list[str]] = {}
    for category in ("organizations", "people", "technical_terms", "medical_terms"):
        raw_terms = glossary.get(category) or []
        terms[category] = sorted({term for term in raw_terms if isinstance(term, str) and term}, key=str.lower)
    terms["regulatory_terms"] = sorted(set(REGULATORY_TERMS))
    return terms


def term_present(text: str, term: str) -> bool:
    if not term:
        return False
    if re.search(r"[A-Za-z0-9]", term):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, flags=re.IGNORECASE))
    return term in text


def terms_in_text(text: str, domain_terms: dict[str, list[str]]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for category in EVALUATED_CATEGORIES:
        found[category] = [term for term in domain_terms.get(category, []) if term_present(text, term)]
    return found


def read_correction_entries(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]
    if isinstance(payload, dict):
        entries = payload.get("correction_log") or payload.get("corrections") or []
        return [entry for entry in entries if isinstance(entry, dict)]
    return []


def correction_term_evidence(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    for entry in entries:
        item = {
            "original": str(entry.get("original") or entry.get("span") or ""),
            "corrected": str(entry.get("corrected") or ""),
            "category": str(entry.get("category") or ""),
            "review_status": str(entry.get("review_status") or ("accepted" if entry.get("accepted", True) else "rejected")),
        }
        if bool(entry.get("accepted", True)):
            accepted.append(item)
        elif item["review_status"] == "manual_review_required":
            manual.append(item)
        else:
            rejected.append(item)
    return {"accepted": accepted, "rejected": rejected, "manual_review_required": manual}


def compare_artifact_set(artifact: ArtifactSet, domain_terms: dict[str, list[str]]) -> dict[str, Any]:
    raw_summary = normalize_summary_text(read_text(artifact.raw_summary))
    corrected_summary = normalize_summary_text(read_text(artifact.corrected_summary))
    raw_transcript = read_text(artifact.raw_transcript)
    corrected_transcript = read_text(artifact.corrected_transcript)
    correction_entries = read_correction_entries(artifact.correction_log)
    evidence = correction_term_evidence(correction_entries)

    raw_summary_terms = terms_in_text(raw_summary, domain_terms)
    corrected_summary_terms = terms_in_text(corrected_summary, domain_terms)
    raw_transcript_terms = terms_in_text(raw_transcript, domain_terms)
    corrected_transcript_terms = terms_in_text(corrected_transcript, domain_terms)

    raw_error_spans = sorted(
        {
            entry["original"]
            for entry in evidence["accepted"]
            if entry["original"] and term_present(raw_summary, entry["original"])
        }
    )
    corrected_canonical_terms = sorted(
        {
            entry["corrected"]
            for entry in evidence["accepted"]
            if entry["corrected"] and term_present(corrected_summary, entry["corrected"])
        }
    )
    rejected_leaks = sorted(
        {
            entry["corrected"]
            for entry in evidence["rejected"]
            if entry["corrected"] and term_present(corrected_summary, entry["corrected"])
        }
    )
    manual_review_leaks = sorted(
        {
            entry["corrected"]
            for entry in evidence["manual_review_required"]
            if entry["corrected"] and term_present(corrected_summary, entry["corrected"])
        }
    )
    introduced_terms = {
        category: sorted(set(corrected_summary_terms[category]) - set(corrected_transcript_terms[category]))
        for category in EVALUATED_CATEGORIES
    }

    raw_term_count = sum(len(values) for values in raw_summary_terms.values())
    corrected_term_count = sum(len(values) for values in corrected_summary_terms.values())
    return {
        "file_id": artifact.file_id,
        "has_raw_summary": artifact.raw_summary is not None,
        "has_corrected_summary": artifact.corrected_summary is not None,
        "raw_summary_domain_term_count": raw_term_count,
        "corrected_summary_domain_term_count": corrected_term_count,
        "domain_term_delta": corrected_term_count - raw_term_count,
        "raw_asr_error_spans_in_summary": raw_error_spans,
        "corrected_canonical_terms_in_summary": corrected_canonical_terms,
        "rejected_or_denied_terms_in_corrected_summary": rejected_leaks,
        "manual_review_terms_in_corrected_summary": manual_review_leaks,
        "corrected_summary_introduced_terms": introduced_terms,
        "raw_summary_terms": raw_summary_terms,
        "corrected_summary_terms": corrected_summary_terms,
    }


def aggregate_rows(rows: list[dict[str, Any]], discovered_artifact_sets: int) -> dict[str, Any]:
    category_preservation = {
        category: {
            "raw_summary_terms": sum(len(row["raw_summary_terms"][category]) for row in rows),
            "corrected_summary_terms": sum(len(row["corrected_summary_terms"][category]) for row in rows),
        }
        for category in EVALUATED_CATEGORIES
    }
    return {
        "discovered_complete_artifact_sets": discovered_artifact_sets,
        "evaluated_files": len(rows),
        "files_with_both_summaries": sum(1 for row in rows if row["has_raw_summary"] and row["has_corrected_summary"]),
        "total_raw_summary_domain_terms": sum(row["raw_summary_domain_term_count"] for row in rows),
        "total_corrected_summary_domain_terms": sum(row["corrected_summary_domain_term_count"] for row in rows),
        "domain_term_delta": sum(row["domain_term_delta"] for row in rows),
        "raw_asr_error_spans_in_summary": sum(len(row["raw_asr_error_spans_in_summary"]) for row in rows),
        "corrected_canonical_terms_in_summary": sum(len(row["corrected_canonical_terms_in_summary"]) for row in rows),
        "rejected_or_denied_term_leaks": sum(len(row["rejected_or_denied_terms_in_corrected_summary"]) for row in rows),
        "manual_review_term_leaks": sum(len(row["manual_review_terms_in_corrected_summary"]) for row in rows),
        "category_preservation": category_preservation,
    }


def build_report(artifact_sets: list[ArtifactSet], domain_terms: dict[str, list[str]]) -> dict[str, Any]:
    rows = [compare_artifact_set(artifact, domain_terms) for artifact in artifact_sets]
    return {
        "scope": {
            "mode": "audit_only_existing_artifacts",
            "external_model_calls": False,
            "raw_email_or_pdf_read": False,
            "raw_transcript_context_emitted": False,
            "claim_scope": "internal_quality_gate_not_final_empirical_claim",
        },
        "aggregate": aggregate_rows(rows, discovered_artifact_sets=len(artifact_sets)),
        "per_file": rows,
    }


def markdown_table(rows: list[dict[str, Any]], headers: list[str]) -> str:
    if not rows:
        return "_No complete summary-impact artifact pairs were available._\n"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")).replace("\n", " ") for header in headers) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    rows = [
        {
            "file_id": row["file_id"],
            "raw_terms": row["raw_summary_domain_term_count"],
            "corrected_terms": row["corrected_summary_domain_term_count"],
            "delta": row["domain_term_delta"],
            "raw_error_spans": len(row["raw_asr_error_spans_in_summary"]),
            "canonical_terms": len(row["corrected_canonical_terms_in_summary"]),
            "denied_leaks": len(row["rejected_or_denied_terms_in_corrected_summary"]),
            "manual_review_leaks": len(row["manual_review_terms_in_corrected_summary"]),
        }
        for row in report["per_file"]
    ]
    return "\n".join(
        [
            "# ASR Correction Summary-Impact Evaluation Report",
            "",
            "## Scope",
            "",
            "- Mode: audit-only existing artifacts.",
            "- External model/API calls: false.",
            "- Raw email/PDF content read: false.",
            "- Raw transcript context emitted: false.",
            "- This is an internal quality gate, not a final empirical claim.",
            "",
            "## Aggregate Metrics",
            "",
            f"- Complete artifact sets discovered: {aggregate['discovered_complete_artifact_sets']}",
            f"- Evaluated files: {aggregate['evaluated_files']}",
            f"- Files with both summaries: {aggregate['files_with_both_summaries']}",
            f"- Raw summary domain terms: {aggregate['total_raw_summary_domain_terms']}",
            f"- Corrected summary domain terms: {aggregate['total_corrected_summary_domain_terms']}",
            f"- Domain term delta: {aggregate['domain_term_delta']}",
            f"- Raw ASR error spans found in summaries: {aggregate['raw_asr_error_spans_in_summary']}",
            f"- Corrected canonical terms found in summaries: {aggregate['corrected_canonical_terms_in_summary']}",
            f"- Rejected/denied term leaks: {aggregate['rejected_or_denied_term_leaks']}",
            f"- Manual-review term leaks: {aggregate['manual_review_term_leaks']}",
            "",
            "## Per-File Comparison",
            "",
            markdown_table(
                rows,
                [
                    "file_id",
                    "raw_terms",
                    "corrected_terms",
                    "delta",
                    "raw_error_spans",
                    "canonical_terms",
                    "denied_leaks",
                    "manual_review_leaks",
                ],
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
    parser = argparse.ArgumentParser(description="Evaluate summary impact of ASR glossary correction from existing artifacts.")
    parser.add_argument("--artifact-root", action="append", type=Path, default=[])
    parser.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY_PATH)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_REPORT_MD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = args.artifact_root or list(DEFAULT_ARTIFACT_ROOTS)
    domain_terms = load_domain_terms(args.glossary)
    artifact_sets = discover_artifact_sets(roots)
    report = build_report(artifact_sets, domain_terms)
    write_reports(report, args.json_out, args.markdown_out)
    print(json.dumps(report["aggregate"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
