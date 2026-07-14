import unittest

from aura.ui.messages import UI_TEXT
from aura.ui.transcription_tab import TranscriptionTab


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


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, name, **fields):
        self.events.append((name, fields))


class UiStateTests(unittest.TestCase):
    def make_tab(self):
        tab = TranscriptionTab.__new__(TranscriptionTab)
        tab.strings = UI_TEXT
        tab.audit = FakeAudit()
        return tab

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


if __name__ == "__main__":
    unittest.main()
