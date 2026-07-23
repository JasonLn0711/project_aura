import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aura.llm.summary import (
    DEFAULT_SUMMARY_MODEL,
    SummarySettings,
    format_summary_block,
    summarize_transcript,
    transcript_has_content,
)
from summary.layered_summary_pipeline import LayeredSummaryResult


class SummaryTests(unittest.TestCase):
    def test_summary_settings_default_to_local_gemma4_ollama(self):
        settings = SummarySettings()

        self.assertEqual(DEFAULT_SUMMARY_MODEL, "google/gemma-4-E4B-it")
        self.assertFalse(hasattr(settings, "temperature"))
        self.assertFalse(hasattr(settings, "max_new_tokens"))
        self.assertFalse(hasattr(settings, "enabled"))
        self.assertFalse(hasattr(settings, "model_id"))

    def test_transcript_content_detection(self):
        self.assertFalse(transcript_has_content(""))
        self.assertFalse(transcript_has_content("  \n"))
        self.assertTrue(transcript_has_content("meeting transcript"))

    def test_summarize_transcript_uses_layered_pipeline(self):
        class Result:
            markdown = "# Meeting Summary\n\n## Topic\n\nTest"

        with patch("aura.llm.summary.generate_layered_summary", return_value=Result()) as generate:
            with patch("aura.llm.summary.save_layered_outputs") as save_outputs:
                markdown = summarize_transcript("corrected transcript", SummarySettings())

        generate.assert_called_once_with("corrected transcript")
        save_outputs.assert_called_once()
        self.assertEqual(markdown, Result.markdown)

    def test_summarize_transcript_writes_evidence_into_the_selected_session(self):
        result = LayeredSummaryResult(
            summary={"decisions": [], "action_items": []},
            markdown="# Meeting Summary",
            validation_log=[],
            field_outputs={},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "meeting"
            session_dir.mkdir()
            (session_dir / "session.json").write_text(
                json.dumps({"meeting_id": "meeting-001"}),
                encoding="utf-8",
            )
            settings = SummarySettings(
                session_dir=str(session_dir),
                meeting_id="meeting-001",
                evidence_segments=({"segment_id": "seg-1"},),
                transcript_sha256="prepared-transcript-sha256",
            )

            with patch("aura.llm.summary.generate_layered_summary", return_value=result):
                markdown = summarize_transcript("corrected transcript", settings)

            payload = json.loads((session_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(markdown, "# Meeting Summary")
            self.assertEqual(payload["meeting_id"], "meeting-001")
            self.assertEqual(payload["transcript_sha256"], "prepared-transcript-sha256")

    def test_format_summary_block(self):
        self.assertEqual(format_summary_block("摘要"), "\n\n===== LLM Summary =====\n摘要")


if __name__ == "__main__":
    unittest.main()
