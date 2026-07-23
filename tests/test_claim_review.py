import json
import tempfile
import unittest
from pathlib import Path

from aura.claim_review import load_claims, record_claim_edit, record_claim_review


class ClaimReviewTests(unittest.TestCase):
    def test_claim_review_is_append_only_and_does_not_rewrite_model_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            summary_path = session_dir / "summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "meeting_id": "meeting-1",
                        "claims": [
                            {
                                "claim_id": "claim-1",
                                "field": "action_items",
                                "text": "整理驗收清單",
                                "source_segment_ids": ["seg-1"],
                                "support_status": "supported",
                                "review_status": "unreviewed",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            original_summary = summary_path.read_bytes()

            confirmed = record_claim_review(session_dir, "claim-1", "confirmed")
            rejected = record_claim_review(session_dir, "claim-1", "rejected")

            self.assertEqual(confirmed["review_status"], "confirmed")
            self.assertEqual(rejected["review_status"], "rejected")
            self.assertEqual(summary_path.read_bytes(), original_summary)
            self.assertEqual(load_claims(session_dir)[0]["review_status"], "rejected")
            events = (session_dir / "review_events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(line)["event"] for line in events], ["claim.confirmed", "claim.rejected"])

    def test_claim_review_rejects_unknown_claim_or_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            (session_dir / "summary.json").write_text(
                json.dumps({"meeting_id": "meeting-1", "claims": []}),
                encoding="utf-8",
            )

            with self.assertRaises(KeyError):
                record_claim_review(session_dir, "missing", "confirmed")
            with self.assertRaises(ValueError):
                record_claim_review(session_dir, "missing", "approved")

    def test_unsupported_claim_cannot_be_confirmed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            (session_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "meeting_id": "meeting-1",
                        "claims": [
                            {
                                "claim_id": "claim-unsupported",
                                "field": "action_items",
                                "text": "沒有來源的動作",
                                "source_segment_ids": [],
                                "support_status": "unsupported",
                                "review_status": "unreviewed",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "source evidence"):
                record_claim_review(
                    session_dir, "claim-unsupported", "confirmed"
                )

    def test_claim_edit_is_an_append_only_human_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            summary_path = session_dir / "summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "meeting_id": "meeting-1",
                        "claims": [
                            {
                                "claim_id": "claim-1",
                                "field": "decisions",
                                "text": "模型原文",
                                "source_segment_ids": ["seg-1"],
                                "support_status": "supported",
                                "review_status": "unreviewed",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            original_summary = summary_path.read_bytes()

            record_claim_review(session_dir, "claim-1", "confirmed")
            edited = record_claim_edit(session_dir, "claim-1", "人員校訂內容")

            self.assertEqual(edited["text"], "人員校訂內容")
            self.assertEqual(edited["review_status"], "edited")
            self.assertEqual(load_claims(session_dir)[0]["text"], "人員校訂內容")
            self.assertEqual(load_claims(session_dir)[0]["review_status"], "edited")
            self.assertEqual(summary_path.read_bytes(), original_summary)
            event = json.loads(
                (session_dir / "review_events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[-1]
            )
            self.assertEqual(event["event"], "claim.edited")


if __name__ == "__main__":
    unittest.main()
