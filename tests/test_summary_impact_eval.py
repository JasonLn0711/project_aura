from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_summary_impact import (
    build_report,
    compare_artifact_set,
    discover_artifact_sets,
    load_domain_terms,
    render_markdown,
)


class SummaryImpactEvaluationTests(unittest.TestCase):
    def make_artifacts(self, root: Path) -> Path:
        base = root / "sample_meeting"
        (root / "sample_meeting_raw.txt").write_text(
            "SANITIZED raw transcript mentions 志德灣, iMBS, detector, and max.",
            encoding="utf-8",
        )
        (root / "sample_meeting_corrected.txt").write_text(
            "SANITIZED corrected transcript mentions 智德萬, iMVS, detector, and max.",
            encoding="utf-8",
        )
        (root / "sample_meeting_correction_log.json").write_text(
            json.dumps(
                [
                    {
                        "original": "志德灣",
                        "corrected": "智德萬",
                        "category": "organizations",
                        "accepted": True,
                    },
                    {
                        "original": "iMBS",
                        "corrected": "iMVS",
                        "category": "technical_terms",
                        "accepted": True,
                    },
                    {
                        "original": "detector",
                        "corrected": "Detector+",
                        "category": "technical_terms",
                        "accepted": False,
                        "review_status": "denylist",
                    },
                    {
                        "original": "max",
                        "corrected": "Max",
                        "category": "people",
                        "accepted": False,
                        "review_status": "manual_review_required",
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "sample_meeting_raw_summary.txt").write_text(
            "Summary says 志德灣 and iMBS joined the meeting.",
            encoding="utf-8",
        )
        (root / "sample_meeting_corrected_summary.txt").write_text(
            "Summary says 智德萬 and iMVS joined. Detector+ and Max should be flagged.",
            encoding="utf-8",
        )
        return base

    def test_summary_impact_report_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.make_artifacts(root)
            artifacts = discover_artifact_sets([root])
            report = build_report(artifacts, load_domain_terms())

        self.assertIn("scope", report)
        self.assertIn("aggregate", report)
        self.assertIn("per_file", report)
        self.assertEqual(report["scope"]["mode"], "audit_only_existing_artifacts")
        self.assertFalse(report["scope"]["external_model_calls"])
        self.assertEqual(report["aggregate"]["evaluated_files"], 1)

    def test_detects_corrected_domain_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.make_artifacts(root)
            row = compare_artifact_set(discover_artifact_sets([root])[0], load_domain_terms())

        self.assertIn("智德萬", row["corrected_canonical_terms_in_summary"])
        self.assertIn("iMVS", row["corrected_canonical_terms_in_summary"])

    def test_detects_raw_asr_error_spans(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.make_artifacts(root)
            row = compare_artifact_set(discover_artifact_sets([root])[0], load_domain_terms())

        self.assertIn("志德灣", row["raw_asr_error_spans_in_summary"])
        self.assertIn("iMBS", row["raw_asr_error_spans_in_summary"])

    def test_rejected_terms_do_not_count_as_improvements(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.make_artifacts(root)
            row = compare_artifact_set(discover_artifact_sets([root])[0], load_domain_terms())

        self.assertIn("Detector+", row["rejected_or_denied_terms_in_corrected_summary"])
        self.assertNotIn("Detector+", row["corrected_canonical_terms_in_summary"])

    def test_manual_review_terms_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.make_artifacts(root)
            row = compare_artifact_set(discover_artifact_sets([root])[0], load_domain_terms())

        self.assertIn("Max", row["manual_review_terms_in_corrected_summary"])

    def test_no_raw_transcript_context_in_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.make_artifacts(root)
            report = build_report(discover_artifact_sets([root]), load_domain_terms())
            rendered = render_markdown(report)
            serialized = json.dumps(report, ensure_ascii=False)

        self.assertNotIn("SANITIZED raw transcript mentions", rendered)
        self.assertNotIn("SANITIZED raw transcript mentions", serialized)
        self.assertNotIn("joined the meeting", rendered)
        self.assertIn("raw_transcript_context_emitted", serialized)


if __name__ == "__main__":
    unittest.main()
