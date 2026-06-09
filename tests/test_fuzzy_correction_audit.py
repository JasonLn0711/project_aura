from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_fuzzy_corrections import (
    build_entries,
    build_report,
    discover_correction_logs,
    discover_transcripts,
    high_risk_reasons,
    render_markdown,
)


class FuzzyCorrectionAuditTests(unittest.TestCase):
    def test_build_report_counts_categories_aliases_and_high_risk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "sample_correction_log.json"
            log_path.write_text(
                json.dumps(
                    {
                        "source_transcript": "sample_transcript.txt",
                        "correction_log": [
                            {
                                "original": "I R B",
                                "corrected": "IRB",
                                "score": 100.0,
                                "category": "technical_terms",
                                "accepted": True,
                            },
                            {
                                "original": "陽名醫院",
                                "corrected": "陽明醫院",
                                "score": 88.0,
                                "category": "medical_terms",
                                "accepted": True,
                            },
                            {
                                "original": "王小名",
                                "corrected": "王小明",
                                "score": 90.0,
                                "category": "people",
                                "accepted": True,
                            },
                            {
                                "original": "510k",
                                "corrected": "510(k)",
                                "score": 70.0,
                                "category": "technical_terms",
                                "accepted": False,
                                "review_status": "manual_review_required",
                                "review_reason": "regulatory_numeric_context_required",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            entries = build_entries(
                [log_path],
                alias_pairs={("technical_terms", "I R B", "IRB")},
            )
            report = build_report([log_path], [], [], entries)

        self.assertEqual(report["summary"]["total_corrections"], 4)
        self.assertEqual(report["summary"]["accepted_corrections"], 3)
        self.assertEqual(report["summary"]["rejected_candidates"], 1)
        self.assertTrue(report["summary"]["high_risk_manual_review_required"])
        self.assertEqual(report["category_counts"]["aliases"], 1)
        self.assertEqual(report["category_counts"]["medical_terms"], 1)
        self.assertEqual(report["category_counts"]["people"], 1)
        self.assertEqual(len(report["lowest_score_accepted_30"]), 3)
        self.assertEqual(len(report["people_accepted_corrections"]), 1)
        self.assertEqual(len(report["medical_terms_accepted_corrections"]), 1)
        self.assertEqual(len(report["alias_accepted_corrections"]), 1)
        self.assertEqual(len(report["watch_term_corrections"]), 1)
        self.assertEqual(len(report["chinese_score_85_to_90_accepted"]), 2)
        self.assertEqual(len(report["rejected_candidates"]), 1)
        self.assertEqual(len(report["manual_review_required"]), 1)
        self.assertEqual(report["manual_review_required"][0]["review_reason"], "regulatory_numeric_context_required")

    def test_high_risk_reasons_detect_number_date_negation_and_categories(self) -> None:
        self.assertIn("people", high_risk_reasons("佳生", "佳聖", "people"))
        self.assertIn("medical_terms", high_risk_reasons("流式細胞", "流式細胞儀", "medical_terms"))
        self.assertIn("number", high_risk_reasons("510k", "510(k)", "technical_terms"))
        self.assertIn("date", high_risk_reasons("2026-6-4", "2026-06-04", "technical_terms"))
        self.assertIn("negation", high_risk_reasons("沒有", "沒", "technical_terms"))

    def test_discovery_excludes_non_transcript_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".venv").mkdir()
            (root / "src" / "pkg.egg-info").mkdir(parents=True)
            (root / "meeting").mkdir()
            (root / "meeting" / "transcript_meeting.txt").write_text("IR B", encoding="utf-8")
            (root / "requirements.txt").write_text("rapidfuzz", encoding="utf-8")
            (root / ".venv" / "ignored.txt").write_text("ignored", encoding="utf-8")
            (root / "src" / "pkg.egg-info" / "SOURCES.txt").write_text("ignored", encoding="utf-8")

            transcripts = discover_transcripts([root])

        self.assertEqual([path.name for path in transcripts], ["transcript_meeting.txt"])

    def test_markdown_does_not_require_raw_transcript_text(self) -> None:
        report = {
            "scope": {
                "correction_log_files_scanned": 1,
                "transcript_files_scanned": 0,
                "generated_correction_log_files": 0,
            },
            "summary": {
                "total_corrections": 0,
                "accepted_corrections": 0,
                "rejected_candidates": 0,
                "high_risk_manual_review_required": False,
            },
            "category_counts": {},
            "score_distribution": {},
            "top_20_changes": [],
            "lowest_score_accepted_30": [],
            "people_accepted_corrections": [],
            "medical_terms_accepted_corrections": [],
            "alias_accepted_corrections": [],
            "watch_term_corrections": [],
            "chinese_score_85_to_90_accepted": [],
            "high_risk_corrections": [],
        }

        rendered = render_markdown(report)

        self.assertIn("Raw email and raw PDF content are not read or emitted", rendered)
        self.assertIn("Total corrections/candidates: 0", rendered)

    def test_discover_correction_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = root / "a_correction_log.json"
            expected.write_text("[]", encoding="utf-8")
            ignored_dir = root / ".venv"
            ignored_dir.mkdir()
            (ignored_dir / "b_correction_log.json").write_text("[]", encoding="utf-8")

            logs = discover_correction_logs([root])

        self.assertEqual(logs, [expected])


if __name__ == "__main__":
    unittest.main()
