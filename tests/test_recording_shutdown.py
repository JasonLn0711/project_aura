"""Client shutdown detaches; explicit Stop owns recording finalization."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
from aura.ui.transcription_tab import TranscriptionTab


class RecordingShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_gui_shutdown_detaches_without_stopping_shared_session(self):
        with patch('aura.ui.transcription_tab.ServiceWorker') as worker:
            tab = TranscriptionTab(audit=MagicMock())
            tab.stop_threads()
            worker.return_value.stop.assert_called_once()
            self.assertFalse(any(c.args and c.args[0] == 'stop' for c in worker.return_value.submit.call_args_list))
            tab.deleteLater()

    def test_unsent_edit_is_preserved_as_local_draft_on_disconnect(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'AURA_DATA_DIR':root}), patch('aura.ui.transcription_tab.ServiceWorker'):
            tab = TranscriptionTab(audit=MagicMock())
            tab.current = {'id':'session-test'}
            tab.text_area.setPlainText('尚未送出的編輯\n  保留空白')
            tab.stop_threads()
            self.assertEqual((Path(root)/'drafts/session-test.txt').read_text(), '尚未送出的編輯\n  保留空白')
            tab.deleteLater()
