import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from aura.review import FINAL, ReviewSegment
from aura.ui.summary_claims_table import SummaryClaimsTable
from aura.ui.transcript_review_table import TranscriptReviewTable
from aura.ui.transcription_tab import TranscriptionTab


class SummaryClaimsTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_table_loads_sources_and_records_human_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            (session_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "meeting_id": "meeting-1",
                        "claims": [
                            {
                                "claim_id": "claim-1",
                                "field": "decisions",
                                "text": "採用覆核流程",
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
            table = SummaryClaimsTable()

            table.load_session(session_dir)
            table.selectRow(0)
            table.review_selected("confirmed")
            table.edit_selected("採用來源覆核流程")

            self.assertEqual(table.rowCount(), 1)
            self.assertEqual(table.item(0, table.SOURCE_COLUMN).text(), "seg-1")
            self.assertEqual(table.item(0, table.REVIEW_COLUMN).text(), "confirmed")
            self.assertEqual(
                table.item(0, table.CLAIM_COLUMN).text(), "採用來源覆核流程"
            )
            self.assertTrue((session_dir / "review_events.jsonl").exists())

            table.clear_session()
            self.assertEqual(table.rowCount(), 0)
            self.assertIsNone(table.session_dir)

    def test_claim_source_selects_and_plays_the_matching_segment(self):
        text_area = TranscriptReviewTable()
        text_area.set_segments(
            [
                ReviewSegment("seg-1", 0, 1000, "第一段", state=FINAL),
                ReviewSegment("seg-2", 2400, 3300, "第二段", state=FINAL),
            ]
        )
        tab = SimpleNamespace(text_area=text_area, play_review_segment=MagicMock())

        TranscriptionTab.open_claim_source(tab, "seg-2")

        self.assertEqual(tab.text_area.currentRow(), 1)
        tab.play_review_segment.assert_called_once_with(2400)

    def test_claim_review_disk_failure_keeps_table_state_and_reports_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            (session_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "meeting_id": "meeting-1",
                        "claims": [
                            {
                                "claim_id": "claim-1",
                                "field": "decisions",
                                "text": "採用覆核流程",
                                "source_segment_ids": ["seg-1"],
                                "support_status": "supported",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            table = SummaryClaimsTable()
            table.load_session(session_dir)
            table.selectRow(0)
            status_label = MagicMock()
            audit = MagicMock()
            tab = SimpleNamespace(
                summary_claims=table,
                status_label=status_label,
                audit=audit,
            )

            with patch(
                "aura.claim_review._atomic_write",
                side_effect=OSError("disk full"),
            ):
                TranscriptionTab.review_selected_claim(tab, "confirmed")

            self.assertEqual(table.claims[0]["review_status"], "unreviewed")
            self.assertEqual(
                table.item(0, table.REVIEW_COLUMN).text(),
                "unreviewed",
            )
            self.assertFalse((session_dir / "review_events.jsonl").exists())
            self.assertIn(
                "覆核紀錄尚未寫入",
                status_label.setText.call_args.args[0],
            )
            audit.record.assert_called_once()

    def test_claim_edit_disk_failure_keeps_original_claim(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            (session_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "meeting_id": "meeting-1",
                        "claims": [
                            {
                                "claim_id": "claim-1",
                                "field": "decisions",
                                "text": "原始主張",
                                "source_segment_ids": ["seg-1"],
                                "support_status": "supported",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            table = SummaryClaimsTable()
            table.load_session(session_dir)
            table.selectRow(0)
            status_label = MagicMock()
            audit = MagicMock()
            tab = SimpleNamespace(
                summary_claims=table,
                status_label=status_label,
                audit=audit,
            )

            with (
                patch(
                    "aura.ui.transcription_tab.QInputDialog.getText",
                    return_value=("校訂內容", True),
                ),
                patch(
                    "aura.claim_review._atomic_write",
                    side_effect=OSError("disk full"),
                ),
            ):
                TranscriptionTab.edit_selected_claim(tab)

            self.assertEqual(table.claims[0]["text"], "原始主張")
            self.assertEqual(
                table.item(0, table.CLAIM_COLUMN).text(),
                "原始主張",
            )
            self.assertFalse((session_dir / "review_events.jsonl").exists())
            self.assertIn(
                "覆核紀錄尚未寫入",
                status_label.setText.call_args.args[0],
            )
            audit.record.assert_called_once()


if __name__ == "__main__":
    unittest.main()
