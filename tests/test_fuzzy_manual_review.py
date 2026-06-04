from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_fuzzy_manual_review import (
    QUEUE_FIELDS,
    build_manual_review_package,
    build_manual_review_rows,
)


def sample_report() -> dict:
    return {
        "summary": {
            "total_corrections": 6,
            "accepted_corrections": 6,
            "rejected_candidates": 0,
            "high_risk_manual_review_required": True,
        },
        "accepted_corrections_all": [
            {
                "source_transcript": "meeting_a.txt",
                "category": "organizations",
                "original": "陽明院",
                "corrected": "陽明醫院",
                "score": 85.71,
                "is_alias": False,
                "high_risk_reasons": [],
            },
            {
                "source_transcript": "meeting_b.txt",
                "category": "people",
                "original": "jason",
                "corrected": "Jason",
                "score": 100.0,
                "is_alias": False,
                "high_risk_reasons": ["people"],
            },
            {
                "source_transcript": "meeting_c.txt",
                "category": "medical_terms",
                "original": "SAMD",
                "corrected": "SaMD",
                "score": 100.0,
                "is_alias": False,
                "high_risk_reasons": ["medical_terms"],
            },
            {
                "source_transcript": "meeting_d.txt",
                "category": "technical_terms",
                "original": "api",
                "corrected": "API",
                "score": 100.0,
                "is_alias": True,
                "high_risk_reasons": [],
            },
            {
                "source_transcript": "meeting_e.txt",
                "category": "technical_terms",
                "original": "510k",
                "corrected": "510(k)",
                "score": 100.0,
                "is_alias": True,
                "high_risk_reasons": ["number"],
            },
            {
                "source_transcript": "meeting_f.txt",
                "category": "technical_terms",
                "original": "ordinary",
                "corrected": "ordinary",
                "score": 100.0,
                "is_alias": False,
                "high_risk_reasons": [],
            },
        ],
    }


class FuzzyManualReviewTests(unittest.TestCase):
    def test_manual_review_queue_contains_low_score_cases(self) -> None:
        rows = build_manual_review_rows(sample_report())

        self.assertTrue(
            any(row["original"] == "陽明院" and "score_85_to_94_99" in row["watch_flag"] for row in rows)
        )

    def test_manual_review_queue_contains_all_people_cases(self) -> None:
        rows = build_manual_review_rows(sample_report())

        self.assertTrue(any(row["category"] == "people" and row["original"] == "jason" for row in rows))

    def test_manual_review_queue_contains_all_medical_cases(self) -> None:
        rows = build_manual_review_rows(sample_report())

        self.assertTrue(any(row["category"] == "medical_terms" and row["original"] == "SAMD" for row in rows))

    def test_manual_review_queue_contains_watch_cases(self) -> None:
        rows = build_manual_review_rows(sample_report())

        self.assertTrue(any(row["corrected"] == "510(k)" and "watch_term" in row["watch_flag"] for row in rows))

    def test_manual_review_queue_has_no_raw_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "audit.json"
            queue_path = root / "queue.csv"
            guide_path = root / "guide.md"
            summary_path = root / "summary.json"
            audit_path.write_text(json.dumps(sample_report(), ensure_ascii=False), encoding="utf-8")

            build_manual_review_package(audit_path, queue_path, guide_path, summary_path)
            with queue_path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)

        self.assertEqual(reader.fieldnames, list(QUEUE_FIELDS))
        self.assertNotIn("context", reader.fieldnames or [])
        self.assertNotIn("raw_transcript", reader.fieldnames or [])
        self.assertNotIn("email", reader.fieldnames or [])
        self.assertTrue(rows)

    def test_manual_review_labels_are_blank(self) -> None:
        rows = build_manual_review_rows(sample_report())

        self.assertTrue(rows)
        self.assertTrue(all(row["review_label"] == "" for row in rows))
        self.assertTrue(all(row["review_note"] == "" for row in rows))


if __name__ == "__main__":
    unittest.main()
