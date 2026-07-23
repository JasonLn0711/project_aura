import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from aura.ui.transcription_tab import TranscriptionTab
from summary.field_schemas import OLLAMA_MODEL_TAG


class FakeButton:
    def __init__(self):
        self.enabled_states = []

    def setEnabled(self, enabled):
        self.enabled_states.append(enabled)


class FakeTextArea:
    def __init__(self):
        self.read_only_states = []
        self.enabled_states = []

    def setReadOnly(self, read_only):
        self.read_only_states.append(read_only)

    def setEnabled(self, enabled):
        self.enabled_states.append(enabled)


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


class FakeRuntimeThread:
    instances = []
    emit_ready_on_start = False
    emit_model_missing_on_start = False

    def __init__(self):
        self.status_updated = FakeSignal()
        self.ready = FakeSignal()
        self.model_missing = FakeSignal()
        self.failed = FakeSignal()
        self.server_process_started = FakeSignal()
        self.finished = FakeSignal()
        self.started = False
        FakeRuntimeThread.instances.append(self)

    def isRunning(self):
        return False

    def start(self):
        self.started = True
        if self.emit_ready_on_start:
            self.ready.emit()
        if self.emit_model_missing_on_start:
            self.model_missing.emit(OLLAMA_MODEL_TAG)
        self.finished.emit()


class SummaryUiRuntimeTests(unittest.TestCase):
    def setUp(self):
        FakeRuntimeThread.instances = []
        FakeRuntimeThread.emit_ready_on_start = False
        FakeRuntimeThread.emit_model_missing_on_start = False

    def make_tab(self):
        tab = TranscriptionTab.__new__(TranscriptionTab)
        tab.btn_summary = FakeButton()
        tab.btn_record = FakeButton()
        tab.btn_import = FakeButton()
        tab.btn_reload_model = FakeButton()
        tab.btn_confirm_claim = FakeButton()
        tab.btn_reject_claim = FakeButton()
        tab.btn_edit_claim = FakeButton()
        tab.text_area = FakeTextArea()
        tab.summary_thread = None
        tab.ollama_runtime_thread = None
        tab.ollama_pull_thread = None
        tab.summary_audit_actor = None
        tab.summary_audit_started_perf = None
        tab.summary_workflow_busy = False
        tab.transcript_revision = 7
        tab.settings = SimpleNamespace(chinese_punctuation_enabled=True)
        tab.combo_lang = MagicMock()
        tab.combo_lang.currentData.return_value = "zh"
        tab.audit = MagicMock()
        tab.update_status_only = MagicMock()
        tab.update_summary_button_state = MagicMock()
        tab.summary_settings = MagicMock(return_value=SimpleNamespace(session_dir="/tmp/session"))
        tab.start_summary = MagicMock()
        tab.on_ollama_model_missing = MagicMock()
        tab.on_ollama_runtime_failed = MagicMock()
        tab.on_ollama_server_process_started = MagicMock()
        return tab

    def test_runtime_ready_calls_start_summary(self):
        tab = self.make_tab()
        FakeRuntimeThread.emit_ready_on_start = True

        with patch("aura.ui.transcription_tab.OllamaRuntimeThread", FakeRuntimeThread):
            tab.prepare_llm_runtime_then_summarize("corrected transcript")

        self.assertEqual(len(FakeRuntimeThread.instances), 1)
        self.assertTrue(FakeRuntimeThread.instances[0].started)
        args, kwargs = tab.start_summary.call_args
        self.assertEqual(args[0].corrected_text, "corrected transcript")
        self.assertEqual(kwargs["summary_revision"], 7)
        self.assertIs(kwargs["settings"], tab.summary_settings.return_value)
        self.assertIsNone(kwargs["finished_callback"])
        self.assertIsNone(kwargs["summary_ready_callback"])

    def test_model_missing_does_not_call_start_summary(self):
        tab = self.make_tab()
        FakeRuntimeThread.emit_model_missing_on_start = True

        with patch("aura.ui.transcription_tab.OllamaRuntimeThread", FakeRuntimeThread):
            tab.prepare_llm_runtime_then_summarize("corrected transcript")

        self.assertEqual(len(FakeRuntimeThread.instances), 1)
        tab.start_summary.assert_not_called()
        args, kwargs = tab.on_ollama_model_missing.call_args
        self.assertEqual(args[0], OLLAMA_MODEL_TAG)
        self.assertEqual(args[1].corrected_text, "corrected transcript")
        self.assertEqual(kwargs["summary_revision"], 7)
        self.assertIs(kwargs["settings"], tab.summary_settings.return_value)

    def test_runtime_receives_only_the_corrected_prepared_transcript(self):
        tab = self.make_tab()
        FakeRuntimeThread.emit_ready_on_start = True

        with patch("aura.ui.transcription_tab.OllamaRuntimeThread", FakeRuntimeThread):
            tab.prepare_llm_runtime_then_summarize("[00:00:01] 志德灣和 iMBS 開會")

        prepared = tab.start_summary.call_args.args[0]
        self.assertEqual(prepared.corrected_text, "[00:00:01] 智德萬和 iMVS 開會。")

    def test_preflight_freezes_workflow_controls_and_transcript_editing(self):
        tab = self.make_tab()

        with patch("aura.ui.transcription_tab.OllamaRuntimeThread", FakeRuntimeThread):
            tab.prepare_llm_runtime_then_summarize("corrected transcript")

        self.assertTrue(tab.summary_workflow_busy)
        self.assertEqual(tab.btn_record.enabled_states[-1], False)
        self.assertEqual(tab.btn_import.enabled_states[-1], False)
        self.assertEqual(tab.text_area.read_only_states[-1], True)
        self.assertEqual(tab.text_area.enabled_states[-1], False)
        self.assertEqual(tab.btn_edit_claim.enabled_states[-1], False)

    def test_empty_transcript_does_not_start_runtime(self):
        tab = self.make_tab()

        with patch("aura.ui.transcription_tab.OllamaRuntimeThread", FakeRuntimeThread):
            tab.prepare_llm_runtime_then_summarize("  \n")

        self.assertEqual(FakeRuntimeThread.instances, [])
        tab.start_summary.assert_not_called()


if __name__ == "__main__":
    unittest.main()
