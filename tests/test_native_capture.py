"""Run the compiled helper against the actual WebSocket service with synthetic audio."""
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from aura.sdk import AuraClient
from aura.native_capture import helper
from test_shared_sessions import test_server, wait_state


class NativeCaptureTests(unittest.TestCase):
    def test_native_pcm_forwarding_and_service_restart(self):
        try:
            binary = helper()
        except RuntimeError:
            self.skipTest('Build the Rust helper with make build-capture')
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            pcm = b''.join((i % 32000).to_bytes(2, 'little') * 480 for i in range(100))
            (root / 'input.pcm').write_bytes(pcm)
            server = None
            native = None
            def start():
                process = multiprocessing.get_context('spawn').Process(target=test_server, args=(str(root / 'service'),))
                process.start()
                path = root / 'service/connection.json'
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if path.exists():
                        value = json.loads(path.read_text())
                        if value['pid'] == process.pid:
                            return process, value
                    time.sleep(.02)
                process.terminate(); process.join()
                raise AssertionError('Service did not start')
            try:
                server, connection = start()
                with AuraClient(connection) as client:
                    sid = client.request('record', {'capture_location': 'client'})['id']
                    wait_state(client, sid, 'recording')
                    with (root / 'events.jsonl').open('w') as output:
                        native = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=output, stderr=subprocess.PIPE, text=True)
                        native.stdin.write(json.dumps(dict(version=1, connection=connection, session_id=sid,
                            directory=str(root / 'spool'), sources=[], input_pcm=str(root / 'input.pcm'))) + '\n')
                        native.stdin.flush()
                        deadline = time.monotonic() + 10
                        while client.request('get', {'session_id': sid})['samples'] < 480 * 8:
                            if native.poll() is not None or time.monotonic() >= deadline:
                                self.fail((root / 'events.jsonl').read_text())
                            time.sleep(.02)
                        server.terminate(); server.join(timeout=10)
                        self.assertFalse(server.is_alive())
                        time.sleep(.2)
                        server, connection = start()
                        native.stdin.write(json.dumps(connection) + '\n'); native.stdin.flush()
                        try:
                            status = native.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            self.fail((root / 'events.jsonl').read_text())
                        self.assertEqual(status, 0, (root / 'events.jsonl').read_text())
                with AuraClient(connection) as client:
                    result = wait_state(client, sid, 'ready')
                    self.assertEqual(result['samples'], 480 * 100)
                    self.assertTrue(result['transcript'])
                    self.assertTrue(result['delivery_committed'])
                    self.assertFalse((root / 'spool/frames.pcm').exists())
                    spans = [(x['start_ms'], x['end_ms']) for x in result['segments']]
                    self.assertEqual(len(spans), len(set(spans)))
            finally:
                if native:
                    if native.poll() is None:
                        native.kill(); native.wait()
                    native.stdin.close(); native.stderr.close()
                if server:
                    server.terminate(); server.join(timeout=10)
