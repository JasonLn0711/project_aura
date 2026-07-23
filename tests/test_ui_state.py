import os
import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from aura.review import FINAL, ReviewSegment
from aura.ui.messages import UI_TEXT
from aura.ui.transcript_io import prepare_transcript
from aura.ui.transcription_tab import (
    TranscriptionTab,
    ensure_output_directory_writable,
    safe_recording_suffix,
)


class FakeStyle:
    def unpolish(self, _widget):
        pass

    def polish(self, _widget):
        pass


class FakeButton:
    def __init__(self, checked=False):
        self.checked = checked
        self.enabled = None
        self.properties = {}
        self.text = ""
        self._style = FakeStyle()

    def isChecked(self):
        return self.checked

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setProperty(self, key, value):
        self.properties[key] = value

    def setText(self, text):
        self.text = text

    def style(self):
        return self._style


class FakePanel:
    def __init__(self):
        self.visible = None

    def setVisible(self, visible):
        self.visible = visible


class FakeSplitter:
    def __init__(self):
        self.sizes = None

    def setSizes(self, sizes):
        self.sizes = sizes


class FakeTextArea:
    def __init__(self, text):
        self.text = text

    def toPlainText(self):
        return self.text


class FakeCombo:
    def currentData(self):
        return "zh"


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, name, **fields):
        self.events.append((name, fields))


class UiStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_tab(self):
        tab = TranscriptionTab.__new__(TranscriptionTab)
        tab.strings = UI_TEXT
        tab.audit = FakeAudit()
        return tab

    def test_transcription_tab_initializes_schedule_and_consent_controls(self):
        with (
            patch("aura.ui.transcription_tab.TranscriberThread.start"),
            patch.object(TranscriptionTab, "apply_model_settings"),
            patch.object(TranscriptionTab, "refresh_runtime_diagnostics"),
            patch.object(TranscriptionTab, "check_for_updates"),
        ):
            tab = TranscriptionTab(audit=FakeAudit())

        try:
            self.assertTrue(tab.check_recording_consent.isEnabled())
            self.assertFalse(tab.time_schedule_start.isEnabled())
            self.assertFalse(tab.check_schedule_auto_stop.isEnabled())
            self.assertFalse(tab.time_schedule_end.isEnabled())
        finally:
            tab.executor.shutdown(wait=False, cancel_futures=True)
            tab.deleteLater()

    def test_settings_toggle_opens_readable_side_panel(self):
        tab = self.make_tab()
        tab.btn_toggle_settings = FakeButton(checked=True)
        tab.settings_scroll = FakePanel()
        tab.body_splitter = FakeSplitter()

        tab.toggle_settings()

        self.assertEqual(tab.btn_toggle_settings.text, UI_TEXT.hide_advanced_settings)
        self.assertTrue(tab.settings_scroll.visible)
        self.assertEqual(tab.body_splitter.sizes, [180, 460, 590])

    def test_runtime_log_toggle_controls_log_visibility(self):
        tab = self.make_tab()
        tab.btn_toggle_runtime_log = FakeButton(checked=True)
        tab.runtime_log = FakePanel()

        tab.toggle_runtime_log()

        self.assertEqual(tab.btn_toggle_runtime_log.text, UI_TEXT.hide_runtime_log)
        self.assertTrue(tab.runtime_log.visible)

    def test_summary_stays_disabled_until_transcript_exists(self):
        tab = self.make_tab()
        tab.btn_summary = FakeButton()
        tab.text_area = FakeTextArea("")
        tab.pending_files = []
        tab.file_thread = None
        tab.import_summary_pending = False
        tab.finalize_recording_pending = False
        tab.scheduled_recording_pending = False
        tab.recorder_thread = None
        tab.summary_thread = None
        tab.ollama_runtime_thread = None
        tab.ollama_pull_thread = None

        tab.update_summary_button_state()
        self.assertFalse(tab.btn_summary.enabled)

        tab.text_area.text = "A reviewed transcript"
        tab.update_summary_button_state()
        self.assertTrue(tab.btn_summary.enabled)

    def test_recording_button_uses_danger_state_while_recording(self):
        tab = self.make_tab()
        tab.btn_record = FakeButton()
        tab.scheduled_recording_pending = False
        tab.recorder_thread = object()

        tab.update_record_button_label()

        self.assertEqual(tab.btn_record.text, UI_TEXT.stop_recording)
        self.assertEqual(tab.btn_record.properties["role"], "danger")

    def test_recording_consent_is_explicit_for_each_session(self):
        tab = self.make_tab()
        tab.check_recording_consent = FakeButton(checked=False)

        self.assertFalse(TranscriptionTab.recording_consent_confirmed(tab))

        tab.check_recording_consent.checked = True
        self.assertTrue(TranscriptionTab.recording_consent_confirmed(tab))

    def test_recording_suffix_cannot_escape_the_session_folder(self):
        self.assertEqual(
            safe_recording_suffix("../../董事會 / Q3"),
            "董事會_Q3",
        )

    def test_output_write_probe_leaves_no_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "custom"

            resolved = ensure_output_directory_writable(output)

            self.assertEqual(resolved, output.resolve())
            self.assertEqual(list(output.iterdir()), [])

    def test_summary_input_is_prepared_with_punctuation_then_glossary_correction(self):
        tab = self.make_tab()
        tab.settings = SimpleNamespace(chinese_punctuation_enabled=True)
        tab.combo_lang = FakeCombo()

        prepared = tab.prepare_transcript_input("[00:00:01] 志德灣和 iMBS 開會")

        self.assertEqual(prepared.corrected_text, "[00:00:01] 智德萬和 iMVS 開會。")

    def test_summary_settings_use_the_canonical_session_and_review_segments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recording_dir = Path(tmpdir) / "meeting"
            session_dir = recording_dir / "meeting_session"
            session_dir.mkdir(parents=True)
            (session_dir / "session.json").write_text(
                json.dumps({"meeting_id": "meeting-canonical"}),
                encoding="utf-8",
            )
            tab = self.make_tab()
            tab.settings = SimpleNamespace(
                chinese_punctuation_enabled=True,
            )
            tab.current_recording_metrics = {
                "workflow": "recording",
                "base_path": str(recording_dir / "meeting"),
                "source_path": str(recording_dir / "meeting.wav"),
            }
            tab.current_import_metrics = None
            tab.current_meeting_id = None
            tab.text_area = SimpleNamespace(
                review=SimpleNamespace(
                    segments=[
                        ReviewSegment("seg-1", 0, 1000, "確認內容", state=FINAL),
                    ]
                )
            )

            prepared = prepare_transcript("確認內容。", language="zh")
            settings = tab.summary_settings(prepared)

            self.assertEqual(settings.session_dir, str(session_dir))
            self.assertEqual(settings.meeting_id, "meeting-canonical")
            self.assertEqual(settings.evidence_segments[0]["segment_id"], "seg-1")
            self.assertEqual(settings.transcript_sha256, prepared.content_sha256)
            self.assertEqual(tab.current_recording_metrics["meeting_id"], "meeting-canonical")


if __name__ == "__main__":
    unittest.main()
