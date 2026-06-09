import tempfile
import unittest
from pathlib import Path

from aura.ui.transcript_io import (
    SUMMARY_MARKER,
    final_transcript_text,
    split_transcript_sections,
    transcript_artifact_paths,
    transcript_text_for_save,
    write_transcript_artifacts,
    write_transcript_file,
)


class TranscriptIoTests(unittest.TestCase):
    def test_transcript_text_for_save_strips_and_adds_newline(self):
        self.assertEqual(transcript_text_for_save("  hello\n"), "hello\n")

    def test_transcript_text_for_save_keeps_empty_content_empty(self):
        self.assertEqual(transcript_text_for_save(" \n "), "")

    def test_write_transcript_file_creates_parent_and_writes_clean_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "transcript.txt"

            saved = write_transcript_file(path, "  [00:00:01] hello\n\n")

            self.assertTrue(saved)
            self.assertEqual(path.read_text(encoding="utf-8"), "[00:00:01] hello\n")

    def test_write_transcript_file_skips_empty_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "transcript.txt"

            saved = write_transcript_file(path, " \n ")

            self.assertFalse(saved)
            self.assertFalse(path.exists())

    def test_split_transcript_sections_extracts_raw_and_summary(self):
        raw, summary = split_transcript_sections(f"[00:00:01] hello\n\n{SUMMARY_MARKER}\n重點摘要")

        self.assertEqual(raw, "[00:00:01] hello")
        self.assertEqual(summary, "重點摘要")

    def test_final_transcript_text_combines_raw_and_summary(self):
        text = final_transcript_text("[00:00:01] hello", f"\n\n{SUMMARY_MARKER}\n重點摘要")

        self.assertEqual(text, f"[00:00:01] hello\n\n{SUMMARY_MARKER}\n重點摘要")

    def test_transcript_artifact_paths_use_base_stem(self):
        paths = transcript_artifact_paths("/tmp/meeting.txt")

        self.assertEqual(paths["raw"], Path("/tmp/meeting_raw.txt"))
        self.assertEqual(paths["corrected"], Path("/tmp/meeting_corrected.txt"))
        self.assertEqual(paths["final"], Path("/tmp/meeting_final.txt"))
        self.assertEqual(paths["summary"], Path("/tmp/meeting_summary.txt"))
        self.assertEqual(paths["correction_log"], Path("/tmp/meeting_correction_log.json"))
        self.assertEqual(paths["metrics"], Path("/tmp/meeting_processing_metrics.json"))

    def test_write_transcript_artifacts_writes_raw_corrected_final_summary_log_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "meeting"

            saved = write_transcript_artifacts(
                base,
                "[00:00:01] 志德灣和 iMBS 開會",
                f"\n\n{SUMMARY_MARKER}\n重點摘要",
                metrics={"workflow": "unit", "outputs": {"ignored": Path("/tmp/old")}},
            )

            self.assertEqual(set(saved), {"raw", "corrected", "final", "summary", "correction_log", "metrics"})
            self.assertEqual(saved["raw"].read_text(encoding="utf-8"), "[00:00:01] 志德灣和 iMBS 開會\n")
            self.assertEqual(saved["corrected"].read_text(encoding="utf-8"), "[00:00:01] 智德萬和 iMVS 開會\n")
            self.assertEqual(saved["summary"].read_text(encoding="utf-8"), "重點摘要\n")
            self.assertEqual(
                saved["final"].read_text(encoding="utf-8"),
                f"[00:00:01] 智德萬和 iMVS 開會\n\n{SUMMARY_MARKER}\n重點摘要\n",
            )
            correction_log_text = saved["correction_log"].read_text(encoding="utf-8")
            self.assertIn('"original": "志德灣"', correction_log_text)
            self.assertIn('"corrected": "iMVS"', correction_log_text)
            metrics_text = saved["metrics"].read_text(encoding="utf-8")
            self.assertIn('"workflow": "unit"', metrics_text)
            self.assertIn('"glossary_correction"', metrics_text)
            self.assertIn('"correction_count": 2', metrics_text)
            self.assertIn("meeting_final.txt", metrics_text)


if __name__ == "__main__":
    unittest.main()
