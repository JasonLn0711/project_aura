import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from reuse_fixtures import SessionCore
from aura.streaming import open_stream, ingest_packet, finish
from test_shared_sessions import Speech, fake_inference


class StreamingProtocolTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch('aura.audio.vad.SileroStreamVAD', return_value=Speech()))
        self.core = SessionCore(self.root, executor=fake_inference)
        self.addCleanup(self.core.close)
        with self.core.changed:
            self.sid = self.core._new({'capture_location': 'client'}, 'recording')['id']
        self.producer = str(uuid.uuid4())
        self.generation = self.open()['stream']['generation']

    def open(self):
        return open_stream(self.core, self.sid, self.producer, ['mixed'])

    def send(self, seq, pcm, generation=None):
        return ingest_packet(self.core, self.sid, generation or self.generation, seq, pcm, ['mixed'])

    def test_lost_ack_replay_is_exactly_once_and_conflict_is_rejected(self):
        data = b'\x01\x02' * 480 * 4
        self.assertEqual(self.send(0, data)['durable_sequence'], 4)
        self.assertEqual(self.send(0, data)['durable_sequence'], 4)
        self.assertEqual((Path(self.root)/'sessions'/self.sid/'.capture/mixed.pcm').read_bytes(), data)
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            self.send(0, b'\x03\x04' * 480)
        with self.assertRaisesRegex(ValueError, 'sequence'):
            self.send(9, data)

    def test_old_connection_cannot_mutate_replacement(self):
        replacement = self.open()['stream']['generation']
        self.core.disconnected(self.sid, self.generation)
        self.assertTrue(self.core.request('get', {'session_id': self.sid})['producer_connected'])
        with self.assertRaisesRegex(ValueError, 'superseded'):
            self.send(0, b'\0' * 960)
        self.send(0, b'\0' * 960, replacement)

    def test_offline_stop_waits_for_local_tail(self):
        with self.core.changed:
            self.send(0, b'\x01\x02' * 480)
            self.core.disconnected(self.sid, self.generation)
            self.core.request('stop', {'session_id': self.sid})
            self.assertEqual(self.core.sessions[self.sid]['state'], 'stopping')
            self.generation = self.open()['stream']['generation']
            self.send(1, b'\x01\x02' * 480)
            with self.assertRaisesRegex(ValueError, 'final sequence'):
                finish(self.core, self.sid, self.generation, 1, 'stop')
            finish(self.core, self.sid, self.generation, 2, 'stop')
            self.assertEqual(self.core.sessions[self.sid]['state'], 'draining')

    def test_packet_limit(self):
        for data in (b'', b'\0' * 959, b'\0' * 960 * 5):
            with self.assertRaises(ValueError):
                self.send(0, data)

    def test_offline_pause_drains_capture_before_acknowledgement(self):
        with self.core.changed:
            self.core.disconnected(self.sid, self.generation)
            self.core.request('pause', {'session_id': self.sid})
            self.assertEqual(self.core.sessions[self.sid]['state'], 'pausing')
            self.generation = self.open()['stream']['generation']
            self.send(0, b'\x01\x02' * 480)
            finish(self.core, self.sid, self.generation, 1, 'pause')
        from test_asr_recovery import wait_for
        wait_for(self.core, self.sid, lambda item: item['state'] == 'paused')
