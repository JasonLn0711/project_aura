import tempfile
import unittest
from unittest.mock import Mock, patch

from reuse_fixtures import SessionCore
from aura.terminal import TerminalStatus


class CaptureSignalTests(unittest.TestCase):
    def test_unrecognized_audio_warns_then_clears_on_speech(self):
        detector = Mock()
        detector.is_speech.return_value = False
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', return_value=detector):
            core = SessionCore(root, executor=lambda *args: {})
            try:
                with core.changed:
                    s = core._new({'capture_location':'client'}, 'recording')
                for i in range(334):
                    core.ingest(s['id'], i, (1000).to_bytes(2, 'little') * 480, ['mixed'])
                from test_asr_recovery import wait_for
                wait_for(core, s['id'], lambda item: item['enhancement']['processed_samples'] == 334 * 480)
                self.assertIn('no speech detected', s['capture_warning'])
                self.assertEqual(s['capture_signal']['speech_frames'], 0)
                self.assertEqual(core.db.execute("SELECT count(*) FROM jobs WHERE kind='chunk'").fetchone()[0], 0)
                detector.is_speech.return_value = True
                core.ingest(s['id'], 334, (1000).to_bytes(2, 'little') * 480, ['mixed'])
                wait_for(core, s['id'], lambda item: item['enhancement']['processed_samples'] == 335 * 480)
                self.assertNotIn('capture_warning', s)
                self.assertEqual(s['capture_signal']['speech_frames'], 1)
            finally:
                core.close()

    def test_terminal_keeps_no_speech_warning_visible_after_stop(self):
        status = TerminalStatus()
        status.session = {'state':'ready','capture_warning':'Audio received, but no speech detected; no audio sent to ASR.'}
        self.assertTrue(status.has_warning())
        self.assertTrue(any('no speech detected' in text for _,text in status.lines()))

    def test_guard_requires_sustained_secondary_speech_and_resets(self):
        import numpy as np
        from types import SimpleNamespace
        from aura.audio.vad import SileroStreamVAD
        class Session:
            def get_inputs(self):
                return [SimpleNamespace(name=n) for n in ('input','h','c')]
            def run(self, _, feed):
                return np.array([0.01]), feed['h'], feed['c']
        with patch('faster_whisper.vad.get_vad_model', return_value=SimpleNamespace(session=Session())):
            vad = SileroStreamVAD()
            vad.secondary = Mock()
            vad.secondary.is_speech.return_value = True
            frame = np.full(480, 1000, dtype=np.int16).tobytes()
            self.assertFalse(any(vad.is_speech(frame, 16000) for _ in range(9)))
            self.assertTrue(vad.is_speech(frame, 16000))
            self.assertTrue(vad.guard_used)
            vad.secondary.is_speech.return_value = False
            self.assertFalse(vad.is_speech(frame, 16000))
            vad.secondary.is_speech.return_value = True
            self.assertFalse(vad.is_speech(frame, 16000))
            self.assertFalse(vad.is_speech(bytes(960), 16000))
