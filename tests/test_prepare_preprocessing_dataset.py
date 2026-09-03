import unittest

from scripts.prepare_preprocessing_dataset import best_window, parse_timestamped_text


class PreparePreprocessingDatasetTests(unittest.TestCase):
    def test_timestamp_parser_builds_a_dense_clip_without_segment_ids(self):
        entries = parse_timestamped_text(
            "[00:00:05] [seg-a] 第一段足夠長的逐字稿內容，用來建立待人工覆核的草稿。\n"
            "[00:00:25] [seg-b] 第二段也會進入同一個六十秒裁切視窗，並保留原始語意。\n"
        )

        start, text = best_window(entries, duration=90) or (-1, "")
        self.assertEqual(start, 5)
        self.assertNotIn("seg-", text)
        self.assertIn("第二段", text)


if __name__ == "__main__":
    unittest.main()
