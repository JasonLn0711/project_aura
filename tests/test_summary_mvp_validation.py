import unittest

from aura.summary_mvp.schema import TranscriptChunk
from aura.summary_mvp.validation import validate_summary


class SummaryMvpValidationTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            TranscriptChunk(
                chunk_id="c001",
                start="00:00:01",
                end="00:00:30",
                text="會議討論 demo 部署限制與 GPU 風險",
            )
        ]

    def test_accepts_grounded_schema(self):
        summary = {
            "meeting_summary": "會議討論 demo 部署限制。",
            "main_topics": [{"topic": "demo 部署", "evidence_chunks": ["c001"]}],
            "key_points": [{"point": "GPU 風險", "evidence_chunks": ["c001"]}],
            "decisions_or_tentative_conclusions": [{"content": "部署限制待確認", "status": "tentative", "evidence_chunks": ["c001"]}],
            "open_questions": [{"question": "GPU 風險如何處理", "evidence_chunks": ["c001"]}],
            "risks_and_constraints": [{"risk": "GPU 風險", "evidence_chunks": ["c001"]}],
            "possible_next_steps": [{"step": "比較 demo 部署限制", "confidence": "medium", "evidence_chunks": ["c001"]}],
            "low_confidence_sections": [{"reason": "weak evidence", "evidence_chunks": ["c001"]}],
        }

        result = validate_summary(summary, self.chunks)

        self.assertTrue(result.valid_json)
        self.assertTrue(result.required_fields_present)
        self.assertTrue(result.evidence_chunks_exist)
        self.assertTrue(result.no_speaker_attribution)
        self.assertTrue(result.no_owner_specific_next_steps)

    def test_rejects_unknown_evidence_and_owner_claim(self):
        summary = {
            "meeting_summary": "Jason said demo is done.",
            "main_topics": [{"topic": "demo", "evidence_chunks": ["c999"]}],
            "key_points": [],
            "decisions_or_tentative_conclusions": [],
            "open_questions": [],
            "risks_and_constraints": [],
            "possible_next_steps": [{"step": "由Jason負責部署", "confidence": "high", "evidence_chunks": ["c001"]}],
            "low_confidence_sections": [],
        }

        result = validate_summary(summary, self.chunks)

        self.assertFalse(result.evidence_chunks_exist)
        self.assertFalse(result.no_speaker_attribution)
        self.assertFalse(result.no_owner_specific_next_steps)


if __name__ == "__main__":
    unittest.main()
