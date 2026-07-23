import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from aura.review import CONFIRMED, FINAL, ReviewSegment
from aura.review import TranscriptReview
from aura.ui.transcript_review_table import TranscriptReviewTable
from aura.ui.transcript_io import prepare_transcript
from aura.ui.transcription_tab import TranscriptionTab
from aura.ui.messages import UI_TEXT


class TranscriptReviewTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_table_edits_and_confirms_structured_segment(self):
        table = TranscriptReviewTable()
        table.set_segments(
            [
                ReviewSegment(
                    segment_id="seg-1",
                    start_ms=1000,
                    end_ms=2500,
                    text="原始文字",
                    speaker="SPEAKER_UNKNOWN",
                    state=FINAL,
                )
            ]
        )

        table.item(0, table.SPEAKER_COLUMN).setText("王小明")
        table.item(0, table.TEXT_COLUMN).setText("校訂文字")
        table.confirm_row(0)

        segment = table.review.segments[0]
        self.assertEqual(
            (segment.segment_id, segment.speaker, segment.text, segment.state, segment.revision),
            ("seg-1", "王小明", "校訂文字", CONFIRMED, 3),
        )
        self.assertEqual(table.toPlainText(), "[00:00:01] [seg-1] 王小明: 校訂文字")

    def test_summary_text_stays_separate_from_editable_transcript_rows(self):
        table = TranscriptReviewTable()

        table.append("[00:00:01] 第一段")
        table.append("\n\n===== LLM Summary =====\n摘要")

        self.assertEqual(table.rowCount(), 1)
        self.assertEqual(
            table.toPlainText(),
            f"[00:00:01] [{table.review.segments[0].segment_id}] 第一段"
            "\n\n===== LLM Summary =====\n摘要",
        )

    def test_new_segments_clear_summary_from_the_previous_document(self):
        table = TranscriptReviewTable()
        table.setPlainText("[00:00:01] 第一場\n\n===== LLM Summary =====\n舊摘要")

        table.set_segments([ReviewSegment("seg-new", 0, 1000, "第二場", state=FINAL)])

        self.assertNotIn("舊摘要", table.toPlainText())

    def test_unchecking_confirmed_row_does_not_desynchronize_saved_state(self):
        table = TranscriptReviewTable()
        table.set_segments(
            [ReviewSegment("seg-1", 0, 1000, "內容", state=CONFIRMED)]
        )

        table.item(0, table.STATE_COLUMN).setCheckState(
            Qt.CheckState.Unchecked
        )

        self.assertEqual(table.review.segments[0].state, CONFIRMED)
        self.assertEqual(
            table.item(0, table.STATE_COLUMN).checkState(),
            Qt.CheckState.Checked,
        )

    def test_next_pending_review_skips_confirmed_segments(self):
        table = TranscriptReviewTable()
        table.set_segments(
            [
                ReviewSegment(
                    "seg-1", 0, 1000, "已覆核", state=CONFIRMED
                ),
                ReviewSegment("seg-2", 1000, 2000, "待覆核", state=FINAL),
            ]
        )
        table.selectRow(0)

        selected = table.select_next_pending()

        self.assertEqual(selected.segment_id, "seg-2")
        self.assertEqual(table.currentRow(), 1)

    def test_transcription_tab_saves_review_into_canonical_import_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "meeting"
            tab = TranscriptionTab.__new__(TranscriptionTab)
            tab.strings = UI_TEXT
            tab.text_area = TranscriptReviewTable()
            tab.text_area.set_segments(
                [ReviewSegment("seg-1", 0, 1000, "內容", state=FINAL)]
            )
            tab.current_meeting_id = None
            tab.review_audio_path = None
            metrics = {"workflow": "import", "source_path": "/tmp/meeting.wav"}

            saved = tab.save_review_artifacts(base, metrics)

            session_dir = Path(tmpdir) / "meeting_session"
            manifest = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
            segments = json.loads((session_dir / "segments.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["meeting_id"], manifest["meeting_id"])
            self.assertEqual(segments["meeting_id"], manifest["meeting_id"])
            self.assertIn("review_srt", saved)

            tab.transcript_revision = 0
            tab.update_summary_button_state = MagicMock()
            tab.reset_summary_claims = MagicMock()
            tab.audit = MagicMock()
            tab.text_area.review.edit("seg-1", text="人員修正內容")
            tab.on_review_changed(tab.text_area.review.segments[0])

            reloaded = TranscriptReview.load(session_dir)
            self.assertEqual(reloaded.segments[0].text, "人員修正內容")

    def test_recording_final_pass_replaces_provisional_rows_with_final_segments(self):
        final_segment = ReviewSegment(
            "seg-final",
            1200,
            2500,
            "會後精確逐字稿",
            speaker="SPEAKER_01",
            state=FINAL,
        )
        tab = TranscriptionTab.__new__(TranscriptionTab)
        tab.text_area = TranscriptReviewTable()
        tab.text_area.append("[00:00:01] 會中暫定逐字稿")
        tab.final_recording_thread = type(
            "FinalThread",
            (),
            {"result_segments": [final_segment], "result_lines": ["unused"]},
        )()
        tab.current_recording_metrics = {}
        tab.timestamp_now = lambda: "2026-07-23T12:00:00+08:00"
        tab.add_stage_duration = MagicMock()
        tab.append_recording_event = MagicMock()
        tab.finalize_recording_after_live_asr_idle = MagicMock()

        tab.on_final_recording_pass_finished()

        self.assertEqual(tab.text_area.review.segments, [final_segment])
        self.assertIsNone(tab.final_recording_thread)
        self.assertTrue(tab.current_recording_metrics["final_recording_pass_completed"])
        tab.finalize_recording_after_live_asr_idle.assert_called_once_with()

    def test_play_selected_segment_uses_keyboard_focusable_action_path(self):
        tab = TranscriptionTab.__new__(TranscriptionTab)
        tab.text_area = TranscriptReviewTable()
        tab.text_area.set_segments(
            [ReviewSegment("seg-1", 1250, 2500, "來源內容", state=FINAL)]
        )
        tab.text_area.selectRow(0)
        tab.play_review_segment = MagicMock()

        tab.play_selected_segment()

        tab.play_review_segment.assert_called_once_with(1250)

    def test_final_recording_pass_never_reuses_previous_session_audio(self):
        tab = TranscriptionTab.__new__(TranscriptionTab)
        tab.current_recording_metrics = {}
        tab.review_audio_path = Path("/tmp/previous-session.wav")
        tab.transcriber_thread = type("Transcriber", (), {"model": object()})()

        self.assertFalse(tab.start_final_recording_pass())

    def test_saved_recording_keeps_review_rows_and_source_session_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "recording"
            tab = TranscriptionTab.__new__(TranscriptionTab)
            tab.strings = UI_TEXT
            tab.finalize_recording_pending = True
            tab.status_label = MagicMock()
            tab.current_recording_metrics = None
            tab.text_area = TranscriptReviewTable()
            tab.text_area.set_segments(
                [ReviewSegment("seg-1", 0, 1000, "會後覆核內容", state=FINAL)]
            )
            tab.prepare_transcript_input = lambda text: prepare_transcript(
                text,
                enable_punctuation=False,
                enable_glossary_correction=False,
            )
            tab.default_transcript_base_path = lambda: str(base)
            tab.review_audio_path = None
            tab.current_review_session_dir = None
            tab.current_review_meeting_id = None
            tab.current_review_audio_path = None
            tab.current_meeting_id = None
            tab.transcript_revision = 0
            tab.remember_output_folder = MagicMock()
            tab.audit = MagicMock()
            tab.restore_post_recording_controls = MagicMock()

            with patch(
                "aura.ui.transcription_tab.remove_transcript_backup"
            ):
                tab.save_and_clear_recording_transcript()

            self.assertEqual(tab.text_area.rowCount(), 1)
            self.assertEqual(tab.text_area.review.segments[0].segment_id, "seg-1")
            self.assertEqual(
                tab.current_review_session_dir,
                Path(tmpdir) / "recording_session",
            )


if __name__ == "__main__":
    unittest.main()
