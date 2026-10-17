"""Regression checks for transport loss and durable unqueued speech."""
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from websockets.exceptions import ConnectionClosedError

from aura.sdk import AuraClient
from reuse_fixtures import SessionCore
from test_shared_sessions import Speech, fake_inference


class StreamingReliabilityTests(unittest.TestCase):
    def test_closed_control_socket_is_discarded(self):
        dead = Mock()
        dead.recv.side_effect = ConnectionClosedError(None, None)
        client = AuraClient({'url': 'ws://127.0.0.1:1', 'token': 'test'})
        client.socket = dead
        with self.assertRaises(ConnectionClosedError):
            client.request('capabilities')
        self.assertIsNone(client.socket)

    def test_disconnect_during_stop_preserves_stop(self):
        with tempfile.TemporaryDirectory() as root:
            core = SessionCore(root, executor=fake_inference)
            try:
                with core.changed:
                    sid = core._new({'capture_location': 'client'}, 'recording')['id']
                    core.request('producer.open', {'session_id': sid})
                    core.request('stop', {'session_id': sid})
                    core.disconnected(sid)
                    self.assertEqual(core.sessions[sid]['state'], 'draining')
            finally:
                core.close()

    def test_restart_recovers_unqueued_speech(self):
        chunks = []
        def execute(kind, payload):
            if kind == 'chunk':
                chunks.append((payload['start'], payload['end']))
            return fake_inference(kind, payload)
        with tempfile.TemporaryDirectory() as root, patch('aura.audio.vad.SileroStreamVAD', return_value=Speech()):
            core = SessionCore(root, executor=execute)
            with core.changed:
                sid = core._new({'capture_location': 'client'}, 'recording')['id']
            for seq in range(3):
                core.ingest(sid, seq, b'\0\1' * 480, ['mixed'])
            core.close()
            core = SessionCore(root, executor=execute)
            try:
                core.request('recover', {'session_id': sid})
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    s = core.request('get', {'session_id': sid})
                    if s['state'] in ('ready', 'failed'):
                        break
                    time.sleep(.01)
                self.assertEqual(s['state'], 'ready', s.get('error'))
                self.assertEqual(chunks, [(0, 1440)])
            finally:
                core.close()
