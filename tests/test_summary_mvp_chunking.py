import json
import unittest
from pathlib import Path

from aura.summary_mvp.chunking import build_sliding_window_chunks, build_time_chunks
from aura.summary_mvp.schema import load_transcript_payload


FIXTURE = Path("tests/fixtures/asr_transcripts/synthetic_meeting_001.json")


class SummaryMvpChunkingTests(unittest.TestCase):
    def setUp(self):
        self.transcript = load_transcript_payload(json.loads(FIXTURE.read_text(encoding="utf-8")))

    def test_time_based_chunking_uses_stable_chunk_ids(self):
        chunks = build_time_chunks(self.transcript, window_seconds=90)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].chunk_id, "c001")
        self.assertEqual(chunks[0].start, "00:00:01")
        self.assertIn("英文版 demo", chunks[0].text)

    def test_sliding_window_chunking_retains_overlap(self):
        chunks = build_sliding_window_chunks(self.transcript, max_chars=130, overlap_chars=50)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].chunk_id, "c001")
        self.assertTrue(set(chunks[0].source_segment_ids) & set(chunks[1].source_segment_ids))


if __name__ == "__main__":
    unittest.main()
