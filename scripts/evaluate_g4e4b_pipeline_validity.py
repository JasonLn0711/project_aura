from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from scripts.run_gemma4_e4b_summary_impact import GATE_NAME  # noqa: E402

DEFAULT_MANIFEST = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_manifest.json"
DEFAULT_MACHINE_REPORT = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_report.json"
DEFAULT_CURRENT_REVIEW = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_current_numctx32768_review_decision.json"
DEFAULT_CONTEXT_DECISION = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_transcript_context_review_decision.json"
DEFAULT_CONTEXT_SHEET = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_transcript_context_review_completed.csv"
DEFAULT_REPORT_JSON = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_pipeline_validity_report.json"
DEFAULT_REPORT_MD = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_pipeline_validity_report.md"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_signature(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "sha256": "", "bytes": 0}
    return {"exists": True, "sha256": sha256_file(path), "bytes": path.stat().st_size}


def resolve_manifest_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def context_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def manifest_by_file_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["file_id"]): item for item in manifest.get("selected_artifact_sets", [])}


def transcript_pair_status(rows: list[dict[str, str]], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = manifest_by_file_id(manifest)
    statuses: list[dict[str, Any]] = []
    for row in rows:
        file_id = row.get("file_id", "")
        item = by_id.get(file_id)
        raw_path = resolve_manifest_path(item["raw_transcript"]) if item else None
        corrected_path = resolve_manifest_path(item["corrected_transcript"]) if item else None
        raw_sig = file_signature(raw_path) if raw_path else {"exists": False, "sha256": "", "bytes": 0}
        corrected_sig = (
            file_signature(corrected_path) if corrected_path else {"exists": False, "sha256": "", "bytes": 0}
        )
        statuses.append(
            {
                "file_id": file_id,
                "context_label": row.get("transcript_audio_context_label", ""),
                "raw_transcript_exists": raw_sig["exists"],
                "corrected_transcript_exists": corrected_sig["exists"],
                "raw_transcript_bytes": raw_sig["bytes"],
                "corrected_transcript_bytes": corrected_sig["bytes"],
                "transcripts_identical": bool(raw_sig["exists"] and raw_sig["sha256"] == corrected_sig["sha256"]),
                "valid_paired_comparison": row.get("transcript_audio_context_label") == "transcript_supported",
            }
        )
    return statuses


def build_report(
    manifest: dict[str, Any],
    machine_report: dict[str, Any],
    current_review: dict[str, Any],
    context_decision: dict[str, Any],
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    labels = Counter(row.get("transcript_audio_context_label", "") for row in rows)
    pair_statuses = transcript_pair_status(rows, manifest)
    identical_pairs = sum(1 for row in pair_statuses if row["transcripts_identical"])
    invalid_pairs = sum(1 for row in pair_statuses if not row["valid_paired_comparison"])
    positive_rows = int(context_decision.get("positive_summary_impact_evidence_rows") or 0)
    summary_failures = int(machine_report.get("summary_generation_failures") or 0)
    quality_claim_allowed = bool(context_decision.get("overall_quality_improvement_claim_allowed"))
    pipeline_valid = (
        positive_rows > 0
        and summary_failures == 0
        and invalid_pairs == 0
        and bool(context_decision.get("any_positive_summary_impact_evidence"))
        and quality_claim_allowed
    )
    return {
        "gate": "G4E4B-PipelineValidity",
        "upstream_gate": GATE_NAME,
        "external_calls": False,
        "cloud_calls": False,
        "raw_transcript_text_emitted": False,
        "review_completed": bool(context_decision.get("review_completed")),
        "human_review_required": False,
        "complete_artifact_sets": machine_report.get("complete_artifact_sets", 0),
        "machine_evaluated_files": machine_report.get("evaluated_files", 0),
        "summary_generation_failures": summary_failures,
        "context_review_rows": len(rows),
        "context_label_counts": dict(labels),
        "identical_transcript_pairs": identical_pairs,
        "invalid_paired_comparison_rows": invalid_pairs,
        "positive_summary_impact_evidence_rows": positive_rows,
        "overall_quality_improvement_claim_allowed": quality_claim_allowed,
        "pipeline_valid_for_quality_evidence": pipeline_valid,
        "current_review_label_counts": current_review.get("label_counts", {}),
        "current_review_preferred_summary_counts": current_review.get("preferred_summary_counts", {}),
        "transcript_pair_status": pair_statuses,
        "decision": (
            "Pipeline validity gate fails for quality-evidence expansion: no positive summary-impact evidence rows, "
            "summarizer/pipeline failures remain, and identical transcript pairs cannot support ASR-correction impact."
        ),
        "next_gate": (
            "Fix paired-output validity before collecting new quality evidence: exclude identical raw/corrected "
            "transcript pairs, require non-empty raw and corrected summaries, and rerun a small local-only sample."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# G4E4B Pipeline Validity Gate",
            "",
            "## Scope",
            "",
            "- Upstream gate: G4E4B-SummaryImpact.",
            "- External calls: false.",
            "- Cloud calls: false.",
            "- Raw transcript text emitted: false.",
            "",
            "## Result",
            "",
            f"- Review completed: {str(report['review_completed']).lower()}",
            f"- Human review required: {str(report['human_review_required']).lower()}",
            f"- Complete artifact sets: {report['complete_artifact_sets']}",
            f"- Machine evaluated files: {report['machine_evaluated_files']}",
            f"- Summary generation failures: {report['summary_generation_failures']}",
            f"- Context review rows: {report['context_review_rows']}",
            f"- Context label counts: {json.dumps(report['context_label_counts'], ensure_ascii=False, sort_keys=True)}",
            f"- Identical transcript pairs: {report['identical_transcript_pairs']}",
            f"- Invalid paired-comparison rows: {report['invalid_paired_comparison_rows']}",
            f"- Positive summary-impact evidence rows: {report['positive_summary_impact_evidence_rows']}",
            f"- Pipeline valid for quality evidence: {str(report['pipeline_valid_for_quality_evidence']).lower()}",
            f"- Overall quality-improvement claim allowed: {str(report['overall_quality_improvement_claim_allowed']).lower()}",
            "",
            "## Decision",
            "",
            report["decision"],
            "",
            "## Next Gate",
            "",
            report["next_gate"],
            "",
        ]
    )


def write_report(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate G4E4B summary-impact pipeline validity.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--machine-report", type=Path, default=DEFAULT_MACHINE_REPORT)
    parser.add_argument("--current-review", type=Path, default=DEFAULT_CURRENT_REVIEW)
    parser.add_argument("--context-decision", type=Path, default=DEFAULT_CONTEXT_DECISION)
    parser.add_argument("--context-sheet", type=Path, default=DEFAULT_CONTEXT_SHEET)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        read_json(args.manifest),
        read_json(args.machine_report),
        read_json(args.current_review),
        read_json(args.context_decision),
        context_rows(args.context_sheet),
    )
    write_report(report, args.report_json, args.report_md)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
