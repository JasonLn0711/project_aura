from fake_diarization import FakeDiarization
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np

from aura.session_core import SessionCore
from aura.reuse_live_repair import resolve_live_gaps
from reuse_fixtures import IdentityReuseWorker
from test_enhancement_health import EnergySpeech
from test_shared_sessions import fake_inference, wait_state
from test_asr_recovery import wait_for


class LiveRepairTests(unittest.TestCase):
    def test_stopped_recovery_resolves_failed_live_attempt_but_retains_submitted_review(self):
        from aura.reuse_recovery import resolve_scanned_gaps
        failed = dict(id='failed',reason='live_repair',status='pending',start_sample=480,end_sample=960)
        submitted = dict(id='submitted',reason='live_repair',submitted=True,status='pending',start_sample=960,end_sample=1440)
        parent = dict(id='parent',reason='suppression',status='pending',start_sample=0,end_sample=1440,
                      review_required_ranges=[[0,480]])
        recovered = dict(id='recovered',reason='recovery',status='resolved',start_sample=480,end_sample=960)
        s = dict(samples=1440,enhancement=dict(recovery_scanned_samples=1440,
            gaps=[failed,submitted,parent,recovered]))
        resolve_scanned_gaps(s)
        self.assertEqual(failed['status'],'resolved')
        self.assertEqual(submitted['status'],'pending')
        self.assertEqual(parent['status'],'pending')

    def exercise(self, repair_succeeds):
        workers, seen = [], []

        class Worker(IdentityReuseWorker):
            def __init__(self, mode, **kw):
                super().__init__(mode, **kw)
                self.repair = 'live-repair' in str(kw.get('log_path', ''))
                self.frames = self.resets = 0
                workers.append(self)

            def push(self, pcm, **kw):
                self.frames += 1
                if self.repair:
                    return pcm if repair_succeeds else bytes(len(pcm))
                return pcm if self.frames <= 60 or self.resets else bytes(len(pcm))

            def reset(self, **kw): self.resets += 1

        def execute(kind, payload):
            if kind == 'chunk': seen.append(payload)
            return fake_inference(kind, payload)

        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', EnergySpeech), \
                patch('aura.audio.reuse.ReuseWorker', IdentityReuseWorker):
            core = SessionCore(root, diarization_factory=FakeDiarization, executor=execute, enhancement_worker_factory=Worker)
            try:
                sid = core.request('record', {'options': {'live_max_segment_len_sec': 4}})['id']
                wait_state(core, sid, 'recording')
                for seq in range(340):
                    core.ingest(sid, seq, np.full(480, 1000, '<i2').tobytes(), ['mixed'])
                s = wait_for(core, sid, lambda s: any(g.get('live_repair') == 'finished'
                    for g in s['enhancement']['gaps']))
                self.assertEqual(s['state'], 'recording')
                self.assertTrue((core.directory(sid) / '.capture/mixed.pcm').exists())
                repair_gaps = [g for g in s['enhancement']['gaps'] if g['reason'] == 'live_repair']
                self.assertTrue(repair_gaps)
                self.assertTrue(all(g['attempts'] <= 2 for g in repair_gaps))
                if repair_succeeds:
                    wait_for(core, sid, lambda s: all(g['status'] == 'resolved'
                        for g in s['enhancement']['gaps'] if g['reason'] == 'live_repair'))
                    self.assertTrue(any(p['split_reason'] == 'live_enhancement_repair' for p in seen))
                else:
                    self.assertTrue(all(g['status'] == 'pending' and g['attempts'] == 2 for g in repair_gaps))
                    self.assertFalse(any(p['split_reason'] == 'live_enhancement_repair' for p in seen))
                # Test edit preservation, with a current revision captured under
                # the same lock as the edit; live jobs may still commit here.
                with core.changed:
                    current = core.request('get', {'session_id':sid})
                    core.request('edit', {'session_id':sid, 'revision':current['revision'], 'text':'Human edit'})
                core.request('stop', {'session_id':sid})
                final = wait_state(core, sid, 'ready')
                self.assertEqual(final['transcript'], 'Human edit')
                self.assertIsNone(core.live_repair.active_session)
                self.assertTrue(all(Path(p['path']).name != 'mixed.pcm' for p in seen))
                ranges = sorted((p['start'],p['end']) for p in seen)
                self.assertTrue(all(b <= c for (a,b),(c,d) in zip(ranges,ranges[1:])))
                starts = [s['start_ms'] for s in final['segments']]
                self.assertEqual(starts, sorted(starts))
            finally:
                core.close()

    def test_live_repair_fills_holes_without_replacing_edits_or_overlapping_jobs(self):
        self.exercise(True)

    def test_failed_repair_is_bounded_and_does_not_fail_capture(self):
        self.exercise(False)

    def test_backlog_hysteresis_and_stop_cancellation(self):
        with tempfile.TemporaryDirectory() as root:
            core = SessionCore(root, diarization_factory=FakeDiarization, executor=fake_inference, enhancement_worker_factory=IdentityReuseWorker)
            done = threading.Event()
            errors = []
            try:
                with core.changed:
                    s = core._new({}, 'recording')
                    s['samples'] = 32000
                    core.live_repair.active_session = s['id']
                def checkpoint():
                    try: core.live_repair._checkpoint()
                    except InterruptedError as exc: errors.append(str(exc))
                    finally: done.set()
                t = threading.Thread(target=checkpoint)
                t.start()
                wait_for(core, s['id'], lambda s: core.live_repair.paused)
                with core.changed:
                    s['enhancement']['input_samples'] = 20000
                    core.changed.notify_all()
                self.assertFalse(done.wait(.05))  # Still above the resume threshold.
                with core.changed:
                    s['enhancement']['input_samples'] = 24000
                    core.changed.notify_all()
                self.assertTrue(done.wait(2))
                t.join()
                self.assertFalse(errors)
                done.clear()
                with core.changed:
                    s['enhancement']['input_samples'] = 0
                t = threading.Thread(target=checkpoint)
                t.start()
                wait_for(core, s['id'], lambda s: core.live_repair.paused)
                with core.changed:
                    s['state'] = 'paused'
                    core.changed.notify_all()
                self.assertTrue(done.wait(2))
                t.join()
                self.assertTrue(errors)
                core.live_repair.active_session = None
            finally:
                core.close()

    def test_submitted_coverage_and_open_episodes_are_not_marked_restored(self):
        parent = dict(id='p',status='pending',closed=True,live_repair='finished',review_required_ranges=[[0,480]])
        child = dict(id='c',parent_id='p',status='resolved')
        session = dict(enhancement=dict(gaps=[parent,child]))
        resolve_live_gaps(session)
        self.assertEqual(parent['status'],'pending')
        parent['review_required_ranges'] = []
        parent['closed'] = False
        resolve_live_gaps(session)
        self.assertEqual(parent['status'],'pending')
        parent['closed'] = True
        resolve_live_gaps(session)
        self.assertEqual(parent['status'],'resolved')
