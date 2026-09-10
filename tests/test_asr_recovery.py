from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aura.asr.models import ASROutputError, ParakeetModel
from aura.session_core import SessionCore
from test_shared_sessions import Speech, fake_inference


def wait_for(core, sid, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        s = core.request('get', {'session_id': sid})
        if predicate(s):
            return s
        time.sleep(.01)
    raise AssertionError({k: s.get(k) for k in ('state', 'error', 'work', 'asr_issues')})


class RecoveryTests(unittest.TestCase):
    def test_short_chunk_uses_text_and_switches_retained_decoding_mode(self):
        import numpy as np
        from contextlib import nullcontext
        class Decoding:
            compute_timestamps = True
            def get(self, name):
                return getattr(self, name)
        self.enterContext(patch.dict('sys.modules', {
            'omegaconf': SimpleNamespace(open_dict=lambda _: nullcontext()),
            'soundfile': None,  # Array input must not require the optional file decoder.
        }))
        class Model:
            cfg = SimpleNamespace(decoding=Decoding())
            modes = []
            def change_decoding_strategy(self, cfg, **kwargs):
                self.modes.append(cfg.compute_timestamps)
            def transcribe(self, audio, **kwargs):
                self_check = self.cfg.decoding.compute_timestamps
                assert self_check == kwargs['timestamps']
                return [SimpleNamespace(text='Hi', timestamp={'segment': [dict(start=0, end=.8, segment='Hi')]})]
        adapter = ParakeetModel.__new__(ParakeetModel)
        adapter.model = Model()
        # Invalid model timing for 120 ms is irrelevant to capture-timed live text.
        self.assertEqual(adapter.transcribe_chunk(np.zeros(1920)), 'Hi')
        self.assertEqual(adapter.transcribe(np.zeros(16000))[0][0].text, 'Hi')
        self.assertEqual(adapter.transcribe_chunk(np.zeros(1920)), 'Hi')
        self.assertEqual(adapter.model.modes, [False, True, False])
        with self.assertRaises(ASROutputError):
            adapter.transcribe(np.zeros(1920))

    def test_gap_continues_recording_recovery_preserves_edits_and_is_idempotent(self):
        attempts = {}
        def execute(kind, payload):
            if kind == 'chunk':
                self.assertTrue(Path(payload['path']).is_file())
                start = payload['start']
                attempts[start] = attempts.get(start, 0) + 1
                if start == 0 and attempts[start] == 1:
                    raise ASROutputError('Synthetic bad output')
                return dict(text=f'part {start}', start_sample=start, end_sample=payload['end'])
            return fake_inference(kind, payload)
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', return_value=Speech()):
            core = SessionCore(root, executor=execute)
            try:
                sid = core.request('record', {'options': {'audio_format': 'wav'}})['id']
                wait_for(core, sid, lambda s: s['state'] == 'recording')
                with self.assertRaisesRegex(ValueError, 'active'):
                    core.request('recover', {'session_id': sid})
                for seq in range(4):
                    core.ingest(sid, seq, b'\0\1' * 480, ['mixed'])
                with core.changed:
                    core._flush(core.sessions[sid])
                s = wait_for(core, sid, lambda s: bool(s.get('asr_issues')))
                self.assertEqual(s['state'], 'recording')
                self.assertIsNone(s['error'])
                for seq in range(4, 8):
                    core.ingest(sid, seq, b'\0\1' * 480, ['mixed'])
                core.request('stop', {'session_id': sid})
                s = wait_for(core, sid, lambda s: s['state'] == 'ready')
                self.assertEqual(s['work']['failed'], 1)
                self.assertTrue((Path(root) / 'sessions' / sid / '.capture/mixed.pcm').exists())
                core.request('edit', {'session_id': sid, 'revision': s['revision'], 'text': 'Human edit'})
                core.request('recover', {'session_id': sid})
                s = wait_for(core, sid, lambda s: s['state'] == 'ready')
                self.assertEqual(s['transcript'], 'Human edit')
                self.assertEqual(s['asr_issues'][0]['status'], 'resolved')
                self.assertEqual([x['start_ms'] for x in s['segments']], [0, 120])
                self.assertEqual(s['work']['failed'], 0)
                self.assertTrue(core.request('export', {'session_id': sid, 'format': 'recovered'})['path'])
                before = dict(attempts)
                core.request('recover', {'session_id': sid})
                self.assertEqual(attempts, before)
            finally:
                core.close()

    def test_recovery_reads_exact_wav_interval_and_rejects_truncated_audio(self):
        import wave
        import numpy as np
        from aura import session_runtime
        from aura.session_core import options_for
        from aura.asr.models import PARAKEET
        seen = []
        model = SimpleNamespace(transcribe_chunk=lambda audio, **kw: seen.append(audio.copy()) or 'recovered')
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'saved.wav'
            with wave.open(str(path), 'wb') as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(16000)
                out.writeframes(np.arange(2400, dtype='<i2').tobytes())
            payload = dict(path=str(path), start=480, end=2400, directory=root,
                           options=options_for({'asr_model': PARAKEET, 'profile': 'off'}))
            with patch.object(session_runtime, '_model', model), patch('aura.asr.models.runtime_receipt', return_value={}), patch('aura.audio.meeting_distance.apply_live_segment_agc', side_effect=lambda a, _: a):
                result = session_runtime.execute('chunk', payload)
                self.assertEqual(result['text'], 'recovered')
                np.testing.assert_allclose(seen[0], np.arange(480, 2400) / 32768)
                payload['end'] = 2401
                with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                    session_runtime.execute('chunk', payload)

    def test_fatal_failure_retains_first_cause_after_capture_failure(self):
        def execute(kind, payload):
            if kind == 'chunk':
                raise RuntimeError('Synthetic fatal worker error')
            return fake_inference(kind, payload)
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', return_value=Speech()):
            core = SessionCore(root, executor=execute)
            try:
                sid = core.request('record')['id']
                wait_for(core, sid, lambda s: s['state'] == 'recording')
                core.ingest(sid, 0, b'\0\1' * 480, ['mixed'])
                with core.changed:
                    core._flush(core.sessions[sid])
                wait_for(core, sid, lambda s: s['state'] == 'failed')
                s = core.request('capture.failed', {'session_id': sid, 'error': 'Session is not accepting audio'})
                self.assertEqual(s['error'], 'Synthetic fatal worker error')
                self.assertEqual(s['capture_error'], 'Session is not accepting audio')
                with self.assertRaises(ValueError):
                    core.ingest(sid, 1, b'\0\1' * 480, ['mixed'])
            finally:
                core.close()
