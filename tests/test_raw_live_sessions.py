"""Raw live ASR and final offline enhancement are separate contracts."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aura.session_core import SessionCore
from reuse_fixtures import IdentityReuseWorker
from test_shared_sessions import Speech, fake_inference, wait_state
from test_asr_recovery import wait_for


class RawLiveTests(unittest.TestCase):
    def test_raw_live_pause_resume_and_offline_export(self):
        modes, submitted = [], []
        frame = b'\x01\x02' * 480

        class OfflineWorker(IdentityReuseWorker):
            def __init__(self, mode, **kwargs):
                modes.append(mode)
                if mode != 'offline':
                    raise AssertionError('Live RE-USE must not start')
                super().__init__(mode, **kwargs)

        def execute(kind, payload):
            if kind == 'chunk':
                start, end = payload['start'], payload['end']
                pcm = Path(payload['path']).read_bytes()[start * 2:end * 2]
                self.assertEqual(pcm, frame * ((end - start) // 480))
                submitted.append((start, end))
            return fake_inference(kind, payload)

        with tempfile.TemporaryDirectory() as root, \
                patch.dict('os.environ', {'AURA_LIVE_IMPLEMENTATION': 'stream-v2'}), \
                patch('aura.audio.vad.SileroStreamVAD', Speech), \
                patch('aura.audio.reuse.ReuseWorker', OfflineWorker):
            core = SessionCore(root, executor=execute, enhancement_worker_factory=OfflineWorker)
            try:
                sid = core.request('record', {'options': {'live_max_segment_len_sec': 2}})['id']
                session = wait_state(core, sid, 'recording')
                self.assertFalse(session['enhancement']['live_enabled'])
                for i in range(80):
                    core.ingest(sid, i, frame, ['mixed'])
                wait_for(core, sid, lambda s: bool(s['live_text']))
                self.assertEqual(modes, [])
                core.request('pause', {'session_id': sid})
                wait_state(core, sid, 'paused')
                core.request('resume', {'session_id': sid})
                for i in range(80, 100):
                    core.ingest(sid, i, frame, ['mixed'])
                core.request('stop', {'session_id': sid})
                result = wait_state(core, sid, 'ready')
                self.assertEqual(modes, ['offline'])
                self.assertEqual(sum(end - start for start, end in submitted), 48000)
                self.assertTrue(result['delivery_committed'])
                self.assertFalse(list(core.directory(sid).rglob('*.pcm')))
                self.assertTrue(Path(result['artifacts']['m4a']).is_file())
            finally:
                core.close()

    def test_stopped_raw_recovery_never_loads_live_model(self):
        from aura.audio.recording_session import RecordingSession
        modes = []

        class OfflineWorker(IdentityReuseWorker):
            def __init__(self, mode, **kwargs):
                modes.append(mode)
                if mode != 'offline':
                    raise AssertionError('Recovery must retain raw live ASR')
                super().__init__(mode, **kwargs)

        with tempfile.TemporaryDirectory() as root, \
                patch('aura.audio.vad.SileroStreamVAD', Speech), \
                patch('aura.audio.reuse.ReuseWorker', OfflineWorker):
            core = SessionCore(root, executor=fake_inference, enhancement_worker_factory=OfflineWorker)
            try:
                with core.changed:
                    session = core._new({}, 'failed')
                    sid = session['id']
                    rec = RecordingSession.start(core.directory(sid), recording_name=sid,
                        capture_mode='system', sample_rate=16000, sample_width=2)
                    rec.append_pcm({'mixed': b'\x01\x02' * 1440})
                    rec.checkpoint()
                    rec._close()
                    session.update(samples=1440, input_sequence=3)
                    session['enhancement']['live_complete'] = True
                    core._save(session)
                core.request('recover', {'session_id': sid})
                result = wait_state(core, sid, 'ready')
                self.assertTrue(result['live_text'])
                self.assertEqual(modes, ['offline'])
                self.assertTrue(result['delivery_committed'])
            finally:
                core.close()
