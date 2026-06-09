from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_g4e4b_pipeline_validity import (
    build_report,
    context_rows,
    file_signature,
    transcript_pair_status,
)


class G4E4BPipelineValidityTests(unittest.TestCase):
    def test_file_signature_does_not_emit_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw.txt"
            path.write_text("private transcript text", encoding="utf-8")
            signature = file_signature(path)

        self.assertTrue(signature["exists"])
        self.assertEqual(signature["bytes"], len("private transcript text"))
        self.assertNotIn("private transcript text", json.dumps(signature))
        self.assertRegex(signature["sha256"], r"^[0-9a-f]{64}$")

    def test_transcript_pair_status_detects_identical_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "sample_raw.txt"
            corrected = root / "sample_final.txt"
            raw.write_text("same transcript", encoding="utf-8")
            corrected.write_text("same transcript", encoding="utf-8")
            manifest = {
                "selected_artifact_sets": [
                    {
                        "file_id": "sample",
                        "raw_transcript": raw.as_posix(),
                        "corrected_transcript": corrected.as_posix(),
                    }
                ]
            }
            rows = [{"file_id": "sample", "transcript_audio_context_label": "summarizer_failure"}]
            statuses = transcript_pair_status(rows, manifest)

        self.assertEqual(len(statuses), 1)
        self.assertTrue(statuses[0]["transcripts_identical"])
        self.assertFalse(statuses[0]["valid_paired_comparison"])

    def test_build_report_blocks_quality_claim_without_positive_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "sample_raw.txt"
            corrected = root / "sample_final.txt"
            raw.write_text("same transcript", encoding="utf-8")
            corrected.write_text("same transcript", encoding="utf-8")
            manifest = {
                "selected_artifact_sets": [
                    {
                        "file_id": "sample",
                        "raw_transcript": raw.as_posix(),
                        "corrected_transcript": corrected.as_posix(),
                    }
                ]
            }
            report = build_report(
                manifest,
                {"complete_artifact_sets": 1, "evaluated_files": 1, "summary_generation_failures": 1},
                {"label_counts": {"UNSURE": 1}, "preferred_summary_counts": {"raw": 1}},
                {
                    "review_completed": True,
                    "positive_summary_impact_evidence_rows": 0,
                    "any_positive_summary_impact_evidence": False,
                    "overall_quality_improvement_claim_allowed": False,
                },
                [{"file_id": "sample", "transcript_audio_context_label": "summarizer_failure"}],
            )

        self.assertFalse(report["pipeline_valid_for_quality_evidence"])
        self.assertFalse(report["overall_quality_improvement_claim_allowed"])
        self.assertFalse(report["human_review_required"])
        self.assertEqual(report["identical_transcript_pairs"], 1)
        self.assertEqual(report["invalid_paired_comparison_rows"], 1)
        self.assertEqual(report["positive_summary_impact_evidence_rows"], 0)
        self.assertFalse(report["raw_transcript_text_emitted"])

    def test_context_rows_reads_completed_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sheet.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["file_id", "transcript_audio_context_label"])
                writer.writeheader()
                writer.writerow({"file_id": "a", "transcript_audio_context_label": "exclude_from_quality_claim"})

            rows = context_rows(path)

        self.assertEqual(rows, [{"file_id": "a", "transcript_audio_context_label": "exclude_from_quality_claim"}])


if __name__ == "__main__":
    unittest.main()
