import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication, QPlainTextEdit
from aura.ui.transcription_tab import TranscriptionTab, safe_recording_suffix, ensure_output_directory_writable


def snapshot(**changes):
    return dict(id='test-session', title='Meeting', state='recording', source='microphone', capture_location='server',
                options={'profile':'light'}, transcript='原始文字', revision=1, **changes)


class UiStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.patch = patch('aura.ui.transcription_tab.ServiceWorker')
        self.worker = self.patch.start().return_value
        self.tab = TranscriptionTab(audit=MagicMock())

    def tearDown(self):
        self.tab.editor_edited = False
        self.tab.stop_threads()
        self.tab.deleteLater()
        self.patch.stop()

    def test_shared_workspace_records_directly(self):
        from aura.metadata import __version__
        self.assertEqual(self.tab.version_banner.text(), f"AURA v{__version__}")
        self.assertIsInstance(self.tab.text_area, QPlainTextEdit)
        self.assertFalse(hasattr(self.tab, "check_recording_consent"))
        self.assertEqual(self.tab.profile.currentData(), 'light')
        self.tab.start_recording_session()
        command, args = self.worker.submit.call_args.args
        self.assertEqual(command, 'record')
        self.assertNotIn("consent", args)
        self.assertFalse(hasattr(self.tab, 'transcriber_thread'))

    def test_pause_and_stop_target_the_attached_session(self):
        self.tab.current = snapshot()
        self.tab.pause_resume()
        self.worker.submit.assert_called_with('pause', {'session_id':'test-session'})
        self.tab.current['state'] = 'paused'
        self.tab.pause_resume()
        self.worker.submit.assert_called_with('resume', {'session_id':'test-session'})
        self.tab.command('stop')
        self.worker.submit.assert_called_with('stop', {'session_id':'test-session'})

    def test_incoming_transcript_preserves_unsaved_edit_and_base_revision(self):
        s = snapshot()
        self.tab.current = s
        self.tab.render(s)
        self.tab.text_area.setPlainText('使用者編輯')
        updated = {**s, 'transcript':'辨識更新', 'revision':2}
        self.tab.receive('sessions', [updated], {})
        self.assertEqual(self.tab.text_area.toPlainText(), '使用者編輯')
        self.assertEqual(self.tab.current['revision'], 1)
        self.tab.save_editor_transcript()
        self.worker.submit.assert_called_with('edit', {'session_id':'test-session','revision':1,'text':'使用者編輯'})

    def test_edit_ack_does_not_clear_newer_local_changes(self):
        s = snapshot()
        self.tab.current = s
        self.tab.text_area.setPlainText('new edit')
        self.tab.receive('edit', s, {'text':'old edit'})
        self.assertTrue(self.tab.editor_edited)

    def test_recording_suffix_and_output_probe(self):
        self.assertEqual(safe_recording_suffix('../../董事會 / Q3'), '董事會_Q3')
        with tempfile.TemporaryDirectory() as root:
            path = ensure_output_directory_writable(Path(root)/'custom')
            self.assertEqual(list(path.iterdir()), [])

    def test_editor_input_preserves_lexical_content(self):
        self.assertEqual(self.tab.prepare_transcript_input('[00:00:01] 志德灣和 iMBS 開會').corrected_text,
                         '[00:00:01] 志德灣和 iMBS 開會')
