import unittest
from unittest.mock import MagicMock, patch

from aura.ui.transcription_tab import TranscriptionTab


class FakeButton:
    def __init__(self):
        self.enabled_states = []

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
            self.model_missing.emit("gemma4:e4b-it-q4_K_M")
        self.finished.emit()


class SummaryUiRuntimeTests(unittest.TestCase):
    def setUp(self):
        FakeRuntimeThread.instances = []
        FakeRuntimeThread.emit_ready_on_start = False
        FakeRuntimeThread.emit_model_missing_on_start = False

    def make_tab(self):
        tab = TranscriptionTab.__new__(TranscriptionTab)
        tab.btn_summary = FakeButton()
        tab.summary_thread = None
        tab.ollama_runtime_thread = None
        tab.ollama_pull_thread = None
        tab.update_status_only = MagicMock()
        tab.update_summary_button_state = MagicMock()
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
        tab.start_summary.assert_called_once_with(
            "corrected transcript",
            finished_callback=None,
            summary_ready_callback=None,
        )

    def test_model_missing_does_not_call_start_summary(self):
        tab = self.make_tab()
        FakeRuntimeThread.emit_model_missing_on_start = True

        with patch("aura.ui.transcription_tab.OllamaRuntimeThread", FakeRuntimeThread):
            tab.prepare_llm_runtime_then_summarize("corrected transcript")

        self.assertEqual(len(FakeRuntimeThread.instances), 1)
        tab.start_summary.assert_not_called()
        tab.on_ollama_model_missing.assert_called_once_with(
            "gemma4:e4b-it-q4_K_M",
            "corrected transcript",
            finished_callback=None,
            summary_ready_callback=None,
        )

    def test_empty_transcript_does_not_start_runtime(self):
        tab = self.make_tab()

        with patch("aura.ui.transcription_tab.OllamaRuntimeThread", FakeRuntimeThread):
            tab.prepare_llm_runtime_then_summarize("  \n")

        self.assertEqual(FakeRuntimeThread.instances, [])
        tab.start_summary.assert_not_called()


if __name__ == "__main__":
    unittest.main()
