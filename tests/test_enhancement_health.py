from fake_diarization import FakeDiarization
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from aura.audio.enhancement_health import EnhancementHealth
from aura.session_core import SessionCore
from aura.audio.recording_session import RecordingSession
from reuse_fixtures import IdentityReuseWorker
from test_shared_sessions import fake_inference, wait_state
from test_asr_recovery import wait_for


class EnergySpeech:
    def is_speech(self, pcm, _rate):
        return bool(np.max(np.abs(np.frombuffer(pcm, '<i2').astype(float))) >= 80)


class HealthTests(unittest.TestCase):
    def test_review_warning_does_not_offer_recovery_for_already_submitted_audio(self):
        from aura.audio.enhancement_health import gap_warning
        s = dict(state='ready',enhancement=dict(health=dict(status='healthy'),gaps=[
            dict(status='pending',review_required_ranges=[[0,480]])]))
        warning = gap_warning(s)
        self.assertIn('submitted intervals need review',warning)
        self.assertIn('/inspect',warning)
        self.assertNotIn('/recover',warning)
        s['enhancement']['gaps'].append(dict(status='pending'))
        self.assertIn('1 enhancement gaps',gap_warning(s))
        self.assertIn('/recover after stop',gap_warning(s))

    def test_recovery_warms_vad_on_context_without_accepting_context_only_speech(self):
        from aura.reuse_recovery import usable_enhancement
        class WarmSpeech(EnergySpeech):
            def __init__(self):
                self.frames = 0
            def is_speech(self, pcm, rate):
                self.frames += 1
                return self.frames > 10 and super().is_speech(pcm, rate)
        voice = np.full(480 * 30, 1000, '<i2').tobytes()
        with patch('aura.audio.vad.SileroStreamVAD', WarmSpeech):
            self.assertTrue(usable_enhancement(voice, voice, 480 * 20))
            self.assertFalse(usable_enhancement(voice, voice[:480 * 20 * 2] + bytes(480 * 10 * 2), 480 * 20))

    def test_warning_and_cli_json_report_pending_gaps_and_recovery_language(self):
        import contextlib
        import io
        from unittest.mock import Mock
        from aura.cli import execute, inspect_session, parser
        from aura.terminal import TerminalStatus
        session = dict(id='test', state='ready', title='Meeting', enhancement={
            'health': {'status': 'healthy'}, 'gaps': [dict(id='gap', status='pending')]})
        view = TerminalStatus()
        view.session = session
        self.assertTrue(view.has_warning())
        self.assertTrue(any('enhancement gaps' in text for _, text in view.lines()))
        client = Mock()
        client.resolve_session.return_value = session
        client.request.side_effect = lambda command, args=None: (
            {'recover': True, 'recover_language': True} if command == 'capabilities' else session)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            execute(client, parser().parse_args(['--json', 'recover', 'test', '--language', 'zh']))
            self.assertEqual(json.loads(output.getvalue())['enhancement'], session['enhancement'])
        client.request.assert_any_call('recover', {'session_id': 'test', 'language': 'zh'})
        with contextlib.redirect_stdout(io.StringIO()) as output:
            inspect_session(session, machine=False)
            self.assertIn('enhancement', output.getvalue())

    def test_recent_no_speech_warning_returns_after_initial_speech(self):
        from unittest.mock import Mock
        detector = Mock()
        detector.is_speech.return_value = True
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', return_value=detector):
            core = SessionCore(root, diarization_factory=FakeDiarization, executor=fake_inference, enhancement_worker_factory=IdentityReuseWorker)
            try:
                sid = core.request('record')['id']
                wait_state(core, sid, 'recording')
                core.ingest(sid, 0, np.full(480, 1000, '<i2').tobytes(), ['mixed'])
                wait_for(core, sid, lambda s: s['enhancement']['processed_samples'] == 480)
                detector.is_speech.return_value = False
                for seq in range(1, 335):
                    core.ingest(sid, seq, np.full(480, 1000, '<i2').tobytes(), ['mixed'])
                s = wait_for(core, sid, lambda s: s['enhancement']['processed_samples'] == 335 * 480)
                self.assertIn('no speech detected', s['capture_warning'])
                self.assertGreater(s['capture_signal']['speech_frames'], 0)
            finally:
                core.close()

    def observe(self, guard, count, source=1000, output=0, speech=True):
        events = []
        for _ in range(count):
            event = guard.observe(480, source, output, speech, output >= 80)
            if event:
                events.append(event)
        return events

    def test_suppression_after_success_resets_once_and_tracks_restoration(self):
        guard = EnhancementHealth()
        self.assertEqual(self.observe(guard, 100, output=1000), [])
        events = self.observe(guard, 100)
        self.assertEqual([e['event'] for e in events], ['suppression'])
        self.assertEqual(events[0]['start_sample'], 48000)
        self.assertEqual([e['event'] for e in self.observe(guard, 100)], ['unresolved'])
        self.assertEqual(self.observe(guard, 100), [])
        self.assertEqual([e['event'] for e in self.observe(guard, 34, output=1000)], ['restored'])
        self.assertEqual([e['event'] for e in self.observe(guard, 100)], ['suppression'])

    def test_silence_and_unvoiced_noise_do_not_reset_model(self):
        guard = EnhancementHealth()
        self.assertEqual(self.observe(guard, 500, source=0, speech=False), [])
        self.assertEqual(self.observe(guard, 500, source=1000, speech=False), [])
        self.assertEqual(self.observe(guard, 500, source=1000, output=100), [])

    def test_live_consumer_recovers_after_speech_without_raw_asr(self):
        workers = []

        class Worker(IdentityReuseWorker):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.frames = self.resets = 0
                workers.append(self)

            def push(self, pcm, **kwargs):
                self.frames += 1
                return pcm if self.frames <= 60 or self.resets else bytes(len(pcm))

            def reset(self, **kwargs):
                self.resets += 1

        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', EnergySpeech):
            core = SessionCore(root, diarization_factory=FakeDiarization, executor=fake_inference, enhancement_worker_factory=Worker)
            try:
                sid = core.request('record')['id']
                wait_state(core, sid, 'recording')
                # This assertion covers the legacy reset-only contract. The
                # guarded online repair path has its own integration tests.
                with core.changed:
                    core.sessions[sid]['enhancement']['policy'] = 'reference-v1'
                for seq in range(220):
                    core.ingest(sid, seq, np.full(480, 1000, '<i2').tobytes(), ['mixed'])
                s = wait_for(core, sid, lambda s: s['enhancement']['processed_samples'] == 220 * 480)
                self.assertEqual(workers[0].resets, 1)
                self.assertEqual(s['enhancement']['health']['status'], 'healthy')
                self.assertTrue(s['enhancement']['gaps'])
                self.assertEqual(s['enhancement']['gaps'][0]['status'], 'pending')
                self.assertEqual((core.directory(sid) / '.capture/enhanced.pcm').stat().st_size, s['samples'] * 2)
                jobs = [json.loads(r[0]) for r in core.db.execute("SELECT payload FROM jobs WHERE kind='chunk'")]
                self.assertTrue(all(Path(j['path']).name == 'enhanced.pcm' for j in jobs))
            finally:
                core.close()

    def test_recovery_fills_interior_gap_preserves_edits_and_is_idempotent(self):
        seen = []
        workers = []

        class ContextSuppressedWorker(IdentityReuseWorker):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.resets = 0
                workers.append(self)

            def push(self, pcm, **kwargs):
                return pcm if self.resets else bytes(len(pcm))

            def reset(self, **kwargs):
                self.resets += 1

        def execute(kind, payload):
            if kind == 'chunk':
                seen.append(payload)
            return fake_inference(kind, payload)

        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', EnergySpeech), \
                patch('aura.audio.reuse.ReuseWorker', IdentityReuseWorker):
            core = SessionCore(root, diarization_factory=FakeDiarization, executor=execute, enhancement_worker_factory=ContextSuppressedWorker)
            try:
                with core.changed:
                    s = core._new({'options': {'language': 'en'}}, 'recoverable')
                    sid = s['id']
                    rec = RecordingSession.start(core.directory(sid), recording_name=sid,
                        capture_mode='system', sample_rate=16000, sample_width=2)
                    rec.append_pcm({'mixed': np.full(480 * 30, 1000, '<i2').tobytes()})
                    paths = rec.finalize(keep_pcm=True)
                    s.update(samples=480 * 30, input_sequence=30, transcript='Human edit', edited=True)
                    s['artifacts']['wav'] = str(paths['mixed'])
                    s['enhancement'].update(live_complete=True, processed_samples=480 * 30)
                    for start, end in ((0, 4800), (9600, 14400)):
                        core._job(s, 'chunk', path=str(paths['mixed']), start=start, end=end, terminal=True)
                    core.db.execute("UPDATE jobs SET state='done' WHERE session=?", (sid,))
                    core._save(s)
                core.request('recover', {'session_id': sid, 'language': 'zh'})
                result = wait_state(core, sid, 'ready')
                self.assertEqual([(p['start'], p['end']) for p in seen], [(4800, 9600)])
                self.assertEqual(workers[0].resets, 1)
                self.assertEqual(seen[0]['options']['language'], 'zh')
                self.assertNotEqual(Path(seen[0]['path']).name, 'mixed.pcm')
                self.assertEqual(result['options']['language'], 'en')
                self.assertEqual(result['transcript'], 'Human edit')
                self.assertTrue(result['artifacts'].get('recovered.txt'))
                self.assertFalse(any(g['status'] == 'pending' for g in result['enhancement']['gaps']))
                self.assertTrue(result['delivery_committed'])
                before = core.db.execute('SELECT count(*) FROM jobs').fetchone()[0]
                core.request('recover', {'session_id': sid})
                self.assertEqual(core.db.execute('SELECT count(*) FROM jobs').fetchone()[0], before)
            finally:
                core.close()

    def test_pending_enhancement_gap_retains_original_after_export(self):
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', EnergySpeech), \
                patch('aura.audio.reuse.ReuseWorker', IdentityReuseWorker):
            core = SessionCore(root, diarization_factory=FakeDiarization, executor=fake_inference, enhancement_worker_factory=IdentityReuseWorker)
            try:
                sid = core.request('record')['id']
                wait_state(core, sid, 'recording')
                for seq in range(12):
                    core.ingest(sid, seq, np.full(480, 1000, '<i2').tobytes(), ['mixed'])
                wait_for(core, sid, lambda s: s['enhancement']['processed_samples'] == 12 * 480)
                with core.changed:
                    core.sessions[sid]['enhancement']['gaps'] = [dict(id='guard-test',
                        start_sample=0, end_sample=5760, status='pending', reason='suppression')]
                core.request('stop', {'session_id': sid})
                result = wait_state(core, sid, 'ready')
                self.assertFalse(result.get('delivery_committed', False))
                self.assertTrue((core.directory(sid) / '.capture/mixed.pcm').is_file())
                self.assertTrue(Path(result['artifacts']['m4a']).is_file())
                from aura.audio.retention import complete_recording_m4a
                with self.assertRaisesRegex(ValueError, 'Enhancement gaps'):
                    complete_recording_m4a(core.directory(sid) / 'session.json', result['artifacts']['m4a'])
            finally:
                core.close()

    def test_new_capture_interval_rechecks_health_and_preserves_old_gap(self):
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', EnergySpeech):
            core = SessionCore(root, diarization_factory=FakeDiarization, executor=fake_inference, enhancement_worker_factory=IdentityReuseWorker)
            try:
                sid = core.request('record')['id']
                wait_state(core, sid, 'recording')
                for seq in range(40):
                    core.ingest(sid, seq, np.full(480, 1000, '<i2').tobytes(), ['mixed'])
                wait_for(core, sid, lambda s: s['enhancement']['processed_samples'] == 40 * 480)
                with core.changed:
                    s = core.sessions[sid]
                    s['enhancement']['health']['status'] = 'blocked'
                    s['enhancement']['gaps'] = [dict(id='old-gap', reason='suppression',
                        start_sample=0, end_sample=480, status='pending')]
                core.request('pause', {'session_id': sid})
                wait_for(core, sid, lambda s: s['enhancement']['completed_boundaries'] == 1)
                core.request('resume', {'session_id': sid})
                for seq in range(40, 80):
                    core.ingest(sid, seq, np.full(480, 1000, '<i2').tobytes(), ['mixed'])
                result = wait_for(core, sid, lambda s: s['enhancement']['processed_samples'] == 80 * 480)
                self.assertEqual(result['enhancement']['health']['status'], 'healthy')
                self.assertEqual(result['enhancement']['gaps'][0]['end_sample'], 480)
                self.assertEqual(result['enhancement']['gaps'][0]['status'], 'pending')
            finally:
                core.close()

    def test_recovery_finalizes_pcm_when_service_was_interrupted_after_live_flush(self):
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', EnergySpeech), \
                patch('aura.audio.reuse.ReuseWorker', IdentityReuseWorker):
            core = SessionCore(root, diarization_factory=FakeDiarization, executor=fake_inference, enhancement_worker_factory=IdentityReuseWorker)
            try:
                with core.changed:
                    s = core._new({}, 'recoverable')
                    sid = s['id']
                    recording = RecordingSession.start(core.directory(sid), recording_name=sid,
                        capture_mode='system', sample_rate=16000, sample_width=2)
                    recording.append_pcm({'mixed': np.full(5760, 1000, '<i2').tobytes()})
                    recording.checkpoint()
                    recording._close()
                    s.update(samples=5760, input_sequence=12)
                    s['enhancement'].update(live_complete=True, processed_samples=5760)
                    core._save(s)
                core.request('recover', {'session_id': sid})
                result = wait_state(core, sid, 'ready')
                self.assertIn('m4a', result['artifacts'])
                self.assertTrue(result['delivery_committed'])
                self.assertFalse(list(core.directory(sid).rglob('*.pcm')))
            finally:
                core.close()

    def test_empty_recovery_asr_keeps_gap_and_original_for_explicit_retry(self):
        from unittest.mock import Mock
        detector = Mock()
        detector.is_speech.return_value = False
        def execute(kind, payload):
            result = fake_inference(kind, payload)
            if kind == 'chunk':
                result['text'] = ''
            return result
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', return_value=detector), \
                patch('aura.audio.reuse.ReuseWorker', IdentityReuseWorker):
            core = SessionCore(root, diarization_factory=FakeDiarization, executor=execute, enhancement_worker_factory=IdentityReuseWorker)
            try:
                sid = core.request('record')['id']
                wait_state(core, sid, 'recording')
                for seq in range(12):
                    core.ingest(sid, seq, np.full(480, 1000, '<i2').tobytes(), ['mixed'])
                wait_for(core, sid, lambda s: s['enhancement']['processed_samples'] == 5760)
                with core.changed:
                    core.sessions[sid]['enhancement']['gaps'] = [dict(id='suppressed', reason='suppression',
                        start_sample=0, end_sample=5760, status='pending')]
                core.request('stop', {'session_id': sid})
                wait_state(core, sid, 'ready')
                detector.is_speech.return_value = True
                core.request('recover', {'session_id': sid, 'language': 'zh'})
                result = wait_state(core, sid, 'ready')
                self.assertFalse(result['transcript'])
                self.assertTrue(any(g['status'] == 'pending' for g in result['enhancement']['gaps']))
                self.assertEqual(result['work']['failed'], 1)
                self.assertFalse(result.get('delivery_committed', False))
                self.assertTrue((core.directory(sid) / '.capture/mixed.pcm').is_file())
            finally:
                core.close()
