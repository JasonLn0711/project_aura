import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

from aura.session_core import SessionCore, options_for
from reuse_fixtures import IdentityReuseWorker
from test_shared_sessions import Speech, fake_inference, wait_state
from test_asr_recovery import wait_for


class ReuseSessionTests(unittest.TestCase):
    def test_fixed_strategy_migrates_preferences_and_rejects_old_explicit_profiles(self):
        self.assertEqual(options_for(preferences={'profile': 'light'})['profile'], 'reuse-v1')
        with self.assertRaisesRegex(ValueError, 'removed'):
            options_for({'profile': 'light'})

    def test_stop_enhances_original_and_never_queues_full_asr(self):
        original = b'\x01\x02' * 480
        enhanced = b'\x03\x04' * 480
        seen = []
        class Worker(IdentityReuseWorker):
            def push(self, pcm):
                return enhanced
            def enhance_file(self, source, target):
                with wave.open(str(source), 'rb') as f:
                    seen.append(f.readframes(f.getnframes()))
                return super().enhance_file(source, target)
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', return_value=Speech()), patch('aura.audio.reuse.ReuseWorker', Worker):
            core = SessionCore(root, executor=fake_inference, enhancement_worker_factory=Worker)
            try:
                sid = core.request('record')['id']
                wait_state(core, sid, 'recording')
                for i in range(12):
                    core.ingest(sid, i, original, ['mixed'])
                core.request('edit', {'session_id': sid, 'revision': 0, 'text': 'User edit'})
                core.request('stop', {'session_id': sid})
                result = wait_state(core, sid, 'ready')
                self.assertEqual(result['transcript'], 'User edit')
                self.assertEqual(seen, [original * 12])
                jobs = list(core.db.execute('SELECT kind,payload FROM jobs WHERE session=?', (sid,)))
                self.assertFalse(any(row['kind'] == 'file' for row in jobs))
                chunks = [json.loads(row['payload']) for row in jobs if row['kind'] == 'chunk']
                self.assertTrue(chunks)
                self.assertTrue(all(Path(c['path']).name == 'enhanced.pcm' for c in chunks))
                self.assertTrue(result['delivery_committed'])
                self.assertFalse(list(core.directory(sid).rglob('*.pcm')))
                self.assertFalse(list(core.directory(sid).rglob('*.wav')))
                before = len(jobs)
                core.request('recover', {'session_id': sid})
                self.assertEqual(core.db.execute('SELECT count(*) FROM jobs WHERE session=?', (sid,)).fetchone()[0], before)
            finally:
                core.close()

    def test_enhancement_failure_retains_raw_without_asr_fallback(self):
        class FailedWorker(IdentityReuseWorker):
            def push(self, pcm):
                raise RuntimeError('Synthetic enhancement failure')
        with tempfile.TemporaryDirectory() as root:
            core = SessionCore(root, executor=fake_inference, enhancement_worker_factory=FailedWorker)
            try:
                sid = core.request('record')['id']
                wait_state(core, sid, 'recording')
                core.ingest(sid, 0, b'\x01\x02' * 480, ['mixed'])
                result = wait_for(core, sid, lambda s: s['state'] == 'failed')
                self.assertIn('Synthetic enhancement failure', result['error'])
                self.assertEqual((core.directory(sid) / '.capture/mixed.pcm').stat().st_size, 960)
                self.assertEqual(core.db.execute("SELECT count(*) FROM jobs WHERE kind IN ('chunk','file','export')").fetchone()[0], 0)
            finally:
                core.close()

    def test_recovery_waits_for_regenerated_enhanced_prefix(self):
        import threading
        from aura.audio.recording_session import RecordingSession
        started, release, dispatched = threading.Event(), threading.Event(), threading.Event()
        class PausedWorker(IdentityReuseWorker):
            def push(self, pcm):
                started.set()
                if not release.wait(3):
                    raise RuntimeError('Test replay watchdog')
                return pcm
        def execute(kind, payload):
            if kind == 'chunk':
                dispatched.set()
                self.assertGreaterEqual(Path(payload['path']).stat().st_size, payload['end'] * 2)
            return fake_inference(kind, payload)
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', return_value=Speech()), patch('aura.audio.reuse.ReuseWorker', IdentityReuseWorker):
            core = SessionCore(root, executor=execute, enhancement_worker_factory=PausedWorker)
            with core.changed:
                session = core._new({}, 'failed')
                sid = session['id']
                rec = RecordingSession.start(core.directory(sid), recording_name=sid, capture_mode='system', sample_rate=16000, sample_width=2)
                rec.append_pcm({'mixed': b'\x01\x02' * 1440})
                rec.checkpoint()
                core.recordings[sid] = rec
                session.update(samples=1440, input_sequence=3)
                session['enhancement']['processed_samples'] = 1440
                output = core.directory(sid) / '.capture/enhanced.pcm'
                output.write_bytes(b'\x01\x02' * 1440)
                core._job(session, 'chunk', path=str(output), start=0, end=1440, terminal=True)
                core._save(session)
            core.close()
            core = SessionCore(root, executor=execute, enhancement_worker_factory=PausedWorker)
            try:
                core.request('recover', {'session_id': sid})
                self.assertTrue(started.wait(2))
                self.assertFalse(dispatched.wait(.1))
                release.set()
                result = wait_state(core, sid, 'ready')
                self.assertTrue(dispatched.is_set())
                self.assertEqual(result['work']['done'], 1)
            finally:
                release.set()
                core.close()
