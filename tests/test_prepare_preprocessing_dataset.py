import unittest

from scripts.prepare_preprocessing_dataset import best_window, parse_review_srt, parse_timestamped_text


class PreparePreprocessingDatasetTests(unittest.TestCase):
    def test_timestamp_parser_removes_segment_ids(self):
        entries = parse_timestamped_text(
            "[00:00:05] [seg-a] 第一段足夠長的逐字稿內容，用來建立待人工覆核的草稿。\n"
            "[00:00:25] [seg-b] 第二段也會進入同一個六十秒裁切視窗，並保留原始語意。\n"
        )

        self.assertEqual(entries[0][0], 5)
        self.assertNotIn("seg-", entries[0][1])

    def test_best_window_extends_audio_to_the_last_selected_segment_end(self):
        segments = parse_review_srt(
            "1\n00:00:05,000 --> 00:00:25,000\n第一段足夠長的逐字稿內容，用來建立待人工覆核的草稿。\n\n"
            "2\n00:00:25,000 --> 00:01:07,240\n第二段也會進入同一個六十秒裁切視窗，並保留原始語意。\n\n"
            "3\n00:01:07,240 --> 00:01:20,000\n下一段不在名義六十秒視窗內。\n"
        )

        start, end, text = best_window(segments, duration=90, candidate_starts=[5]) or (-1, -1, "")
        self.assertEqual(start, 5)
        self.assertEqual(end, 67.24)
        self.assertIn("第二段", text)
        self.assertNotIn("下一段", text)
        self.assertIsNone(best_window(segments, duration=67, candidate_starts=[5]))

    def test_best_window_uses_the_nearest_complete_earlier_anchor(self):
        segments = [
            (0.0, 2.0, "前段"),
            (2.0, 61.0, "完整內容" * 30),
            (61.0, 65.0, "媒體之外的尾段"),
        ]

        start, end, _ = best_window(segments, duration=62, candidate_starts=[2.0, 0.0]) or (-1, -1, "")

        self.assertEqual(start, 0.0)
        self.assertEqual(end, 61.0)

    def test_best_window_requires_a_complete_sixty_second_source_window(self):
        segments = [(40.0, 70.0, "這段來源內容足夠長，但原始媒體沒有完整的六十秒可用視窗。" * 2)]

        self.assertIsNone(best_window(segments, duration=90))


if __name__ == "__main__":
    unittest.main()
