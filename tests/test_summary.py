import unittest
from unittest.mock import patch

from aura.llm.summary import (
    DEFAULT_SUMMARY_MODEL,
    SummarySettings,
    build_summary_prompt,
    format_summary_block,
    summarize_transcript,
    transcript_has_content,
)


class SummaryTests(unittest.TestCase):
    def test_summary_prompt_documents_parallel_layered_runtime(self):
        prompt = build_summary_prompt("[00:00:01] hello")

        self.assertIn("parallel layered extractor", prompt)
        self.assertIn("gemma4:e4b-it-q4_K_M", prompt)
        self.assertIn("corrected transcript only", prompt)
        self.assertIn("correction_log", prompt)
        self.assertIn("[00:00:01] hello", prompt)

    def test_summary_settings_default_to_local_gemma4_ollama(self):
        settings = SummarySettings(enabled=True)

        self.assertEqual(settings.model_id, DEFAULT_SUMMARY_MODEL)
        self.assertEqual(settings.model_id, "google/gemma-4-E4B-it")
        self.assertEqual(settings.quantization, "ollama_q4_K_M_local_tag")
        self.assertEqual(settings.language, "台灣繁體中文")

    def test_transcript_content_detection(self):
        self.assertFalse(transcript_has_content(""))
        self.assertFalse(transcript_has_content("  \n"))
        self.assertTrue(transcript_has_content("meeting transcript"))

    def test_summarize_transcript_uses_layered_pipeline(self):
        class Result:
            markdown = "# Meeting Summary\n\n## Topic\n\nTest"

        with patch("aura.llm.summary.generate_layered_summary", return_value=Result()) as generate:
            with patch("aura.llm.summary.save_layered_outputs") as save_outputs:
                markdown = summarize_transcript("corrected transcript", SummarySettings(enabled=True))

        generate.assert_called_once_with("corrected transcript")
        save_outputs.assert_called_once()
        self.assertEqual(markdown, Result.markdown)

    def test_format_summary_block(self):
        self.assertEqual(format_summary_block("摘要"), "\n\n===== LLM Summary =====\n摘要")


if __name__ == "__main__":
    unittest.main()
