import unittest
from unittest.mock import patch

from aura.asr.punctuation import (
    TransformersChinesePunctuationRestorer,
    insert_punctuation_by_offsets,
    normalize_chinese_punctuation,
    punctuation_label_to_text,
    restore_chinese_punctuation,
    restore_chinese_punctuation_for_line,
    restore_chinese_punctuation_for_transcript,
    should_restore_traditional_chinese_punctuation,
)


class FakeRestorer:
    def __init__(self):
        self.calls = []

    def restore(self, text):
        self.calls.append(text)
        return f"{text}，完成"


class PunctuationTests(unittest.TestCase):
    def test_detects_traditional_chinese_target(self):
        self.assertTrue(should_restore_traditional_chinese_punctuation("這是一段會議紀錄", "zh"))
        self.assertTrue(should_restore_traditional_chinese_punctuation("你好世界", "zh"))
        self.assertFalse(should_restore_traditional_chinese_punctuation("这是一个会议记录", "zh"))
        self.assertFalse(should_restore_traditional_chinese_punctuation("hello world", "en"))

    def test_normalizes_ascii_punctuation_near_chinese(self):
        self.assertEqual(normalize_chinese_punctuation("這是測試,請確認?"), "這是測試，請確認？")

    def test_rule_fallback_adds_terminal_punctuation(self):
        result = restore_chinese_punctuation("這是測試", language="zh", enable_model=False)

        self.assertEqual(result.text, "這是測試。")
        self.assertEqual(result.backend, "rule_fallback")

    def test_model_restorer_is_used_for_unpunctuated_chinese(self):
        restorer = FakeRestorer()

        result = restore_chinese_punctuation("這是一段需要標點的會議紀錄", language="zh", restorer=restorer)

        self.assertEqual(result.text, "這是一段需要標點的會議紀錄，完成。")
        self.assertEqual(result.backend, "model")
        self.assertEqual(restorer.calls, ["這是一段需要標點的會議紀錄"])

    def test_formatted_line_preserves_timestamp_and_speaker_prefix(self):
        result = restore_chinese_punctuation_for_line(
            "[00:00:01] SPEAKER_01: 這是測試",
            language="zh",
            enable_model=False,
        )

        self.assertEqual(result.text, "[00:00:01] SPEAKER_01: 這是測試。")

    def test_transcript_restoration_preserves_line_structure(self):
        result = restore_chinese_punctuation_for_transcript(
            "[00:00:01] 這是第一句\n[00:00:02] hello",
            language="zh",
            enable_model=False,
        )

        self.assertEqual(result.text, "[00:00:01] 這是第一句。\n[00:00:02] hello")

    def test_insert_punctuation_by_offsets(self):
        result = insert_punctuation_by_offsets("你好世界", {2: "，", 4: "。"})

        self.assertEqual(result, "你好，世界。")

    def test_punctuation_label_suffixes_are_supported(self):
        self.assertEqual(punctuation_label_to_text("S-，"), "，")
        self.assertEqual(punctuation_label_to_text("S-；"), "；")

    def test_model_restorer_keeps_primary_and_fallback_model_ids(self):
        restorer = TransformersChinesePunctuationRestorer(model_id="primary", fallback_model_id="fallback")

        self.assertEqual(restorer.model_ids, ("primary", "fallback"))

    def test_missing_model_dependency_is_actionable_and_cached(self):
        restorer = TransformersChinesePunctuationRestorer()
        real_import = __import__
        transformer_imports = 0

        def import_with_missing_transformers(name, *args, **kwargs):
            nonlocal transformer_imports
            if name == "transformers":
                transformer_imports += 1
                raise ModuleNotFoundError("No module named 'transformers'", name="transformers")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_with_missing_transformers):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "make setup-app"):
                    restorer.restore("這是一段需要標點的會議紀錄")

        self.assertEqual(transformer_imports, 1)


if __name__ == "__main__":
    unittest.main()
