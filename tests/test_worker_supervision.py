import threading
import time
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import Mock, patch

from reuse_fixtures import SessionCore
from aura.session_core import now
from aura.worker import InferenceWorker


class WorkerSupervisionTests(unittest.TestCase):
    def test_export_watchdog_allows_measured_progress_beyond_total_timeout(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = Path(root) / 'session.json'
            manifest.write_text(json.dumps({'enhancement_progress': {'completed_samples': 0}}))
            worker = object.__new__(InferenceWorker)
            worker.pipe = Mock()
            worker.process = Mock()
            worker.closed = threading.Event()
            elapsed = [0]
            def poll(_timeout):
                elapsed[0] += .6
                manifest.write_text(json.dumps({'enhancement_progress': {'completed_samples': int(elapsed[0] * 16000)}}))
                return elapsed[0] > 3
            worker.pipe.poll.side_effect = poll
            worker.pipe.recv.return_value = (True, {'path': 'retained.m4a'})
            with patch.dict('os.environ', {'AURA_WORKER_WATCHDOG_SECONDS': '1'}), patch('time.monotonic', side_effect=lambda: elapsed[0]):
                self.assertEqual(worker.submit(None, 'export', {'directory': root}).result()['path'], 'retained.m4a')
            self.assertGreater(elapsed[0], 3)
            worker.process.terminate.assert_not_called()

    def test_export_unchanged_progress_still_times_out(self):
        worker = object.__new__(InferenceWorker)
        worker.pipe = Mock()
        worker.pipe.poll.return_value = False
        worker.process = Mock()
        worker.closed = threading.Event()
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'session.json').write_text('{"enhancement_progress":{"completed_samples":16000}}')
            with patch.dict('os.environ', {'AURA_WORKER_WATCHDOG_SECONDS': '.01'}):
                with self.assertRaisesRegex(RuntimeError, 'watchdog'):
                    worker.submit(None, 'export', {'directory': root}).result()
        worker.process.terminate.assert_called_once()

    def test_watchdog_terminates_stuck_process(self):
        worker = object.__new__(InferenceWorker)
        worker.pipe = Mock()
        worker.pipe.poll.return_value = False
        worker.process = Mock()
        worker.process.is_alive.return_value = True
        worker.closed = threading.Event()
        with patch.dict('os.environ', {'AURA_WORKER_WATCHDOG_SECONDS': '.01'}):
            with self.assertRaisesRegex(RuntimeError, 'watchdog'):
                worker.submit(None, 'chunk', {}).result()
        worker.process.terminate.assert_called_once()
        worker.process.kill.assert_called_once()
        self.assertTrue(worker.closed.is_set())

    def test_capture_deadline_does_not_wait_for_inference(self):
        entered = threading.Event()
        release = threading.Event()
        def execute(kind, payload):
            entered.set()
            release.wait(5)
            return {'text':'', 'start_sample':0, 'end_sample':480}
        with tempfile.TemporaryDirectory() as root:
            core = SessionCore(root, executor=execute)
            try:
                with core.changed:
                    s = core._new({}, 'recording')
                    s.update(producer_connected=True)
                    s['enhancement']['processed_samples'] = 480
                    core._job(s, 'chunk', start=0, end=480, terminal=True, path='fixture')
                self.assertTrue(entered.wait(2))
                with core.changed:
                    s['stop_at'] = now()
                deadline = time.monotonic()+2
                while s['state'] == 'recording' and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(s['state'], 'stopping')
                self.assertFalse(release.is_set())
            finally:
                release.set()
                core.close()
