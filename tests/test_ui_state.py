import os
import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPlainTextEdit
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
            self.assertIsInstance(tab.text_area, QPlainTextEdit)
            self.assertFalse(hasattr(tab, "btn_summary"))
            tab.update_log("[00:00:00] 原始逐字稿")
            self.assertFalse(tab.editor_edited)
            with tempfile.TemporaryDirectory() as tmpdir:
                for edited in (False, True):
                    tab.text_area.setPlainText("使用者編輯" if edited else "原始逐字稿")
                    tab.editor_edited = edited
                    tab.refinement_revision = tab.transcript_revision
                    tab.current_recording_metrics = {}
                    tab.final_recording_thread = SimpleNamespace(
                        result_lines=["[00:00:00] 精確逐字稿"],
                        result_segments=[ReviewSegment("seg-test", 0, 1000, "精確逐字稿", state=FINAL)],
                    )
                    tab.default_transcript_base_path = lambda: str(Path(tmpdir) / "meeting")
                    tab.finalize_recording_after_live_asr_idle = MagicMock()
                    tab.on_final_recording_pass_finished()
                    if edited:
                        self.assertEqual(tab.text_area.toPlainText(), "使用者編輯")
                        self.assertEqual((Path(tmpdir) / "meeting_refined.txt").read_text(), "[00:00:00] 精確逐字稿\n")
                    else:
                        self.assertEqual(tab.text_area.toPlainText(), "[00:00:00] 精確逐字稿")

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

    def test_editor_input_is_preserved_on_save(self):
        tab = self.make_tab()
        tab.settings = SimpleNamespace(chinese_punctuation_enabled=True)
        tab.combo_lang = FakeCombo()

        prepared = tab.prepare_transcript_input("[00:00:01] 志德灣和 iMBS 開會")

        self.assertEqual(prepared.corrected_text, "[00:00:01] 志德灣和 iMBS 開會")


if __name__ == "__main__":
    unittest.main()
