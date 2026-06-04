import unittest

from aura.llm.summary import (
    DEFAULT_SUMMARY_MODEL,
    SummarySettings,
    build_summary_prompt,
    format_summary_block,
    transcript_has_content,
)


class SummaryTests(unittest.TestCase):
    def test_summary_prompt_requires_taiwan_traditional_chinese(self):
        prompt = build_summary_prompt("[00:00:01] hello")

        self.assertIn("台灣常用的繁體中文", prompt)
        self.assertIn("不要使用簡體中文", prompt)
        self.assertIn("待辦事項", prompt)
        self.assertIn("[00:00:01] hello", prompt)

    def test_summary_settings_default_to_gemma4_nvfp8(self):
        settings = SummarySettings(enabled=True)

        self.assertEqual(settings.model_id, DEFAULT_SUMMARY_MODEL)
        self.assertIn("gemma-4-E4B-it-fp8", settings.model_id)
        self.assertEqual(settings.quantization, "nvfp8")
        self.assertEqual(settings.language, "台灣繁體中文")

    def test_transcript_content_detection(self):
        self.assertFalse(transcript_has_content(""))
        self.assertFalse(transcript_has_content("  \n"))
        self.assertTrue(transcript_has_content("meeting transcript"))

    def test_format_summary_block(self):
        self.assertEqual(format_summary_block("摘要"), "\n\n===== LLM Summary =====\n摘要")


if __name__ == "__main__":
    unittest.main()
