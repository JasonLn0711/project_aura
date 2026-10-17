import threading
import time
import tempfile
import unittest
from unittest.mock import Mock, patch

from reuse_fixtures import SessionCore
from aura.session_core import now
from aura.worker import InferenceWorker


class WorkerSupervisionTests(unittest.TestCase):
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
