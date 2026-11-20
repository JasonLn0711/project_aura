import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aura.audio.enhanced_journal import EnhancedJournal
from aura.streaming_metrics import streaming_status


class StreamingContractTests(unittest.TestCase):
    def test_output_is_readable_before_checkpoint_but_not_durable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'enhanced.pcm'
            with path.open('wb') as output:
                journal = EnhancedJournal(output, grouped=True)
                journal.write(b'\x01\x00' * 480)
                self.assertEqual(len(path.read_bytes()), 960)
                self.assertEqual(journal.durable_samples, 0)
                with patch('aura.audio.enhanced_journal.os.fsync', side_effect=OSError('disk failure')):
                    with self.assertRaises(OSError): journal.checkpoint()
                self.assertEqual(journal.durable_samples, 0)
                self.assertEqual(journal.checkpoint(), 480)

    def test_ready_audio_does_not_hide_pending_transcript(self):
        status = streaming_status(dict(state='ready', samples=32000, input_sequence=0,
            artifacts={'m4a': 'delivered.m4a'}, enhancement=dict(processed_samples=16000,
            gaps=[{'status': 'pending'}])))
        self.assertTrue(status['audio_ready'])
        self.assertEqual(status['transcript_status'], 'pending_review')
        self.assertEqual(status['enhancement_lag_seconds'], 1)
        self.assertEqual(status['waiting_reason'], 'stopped_with_pending_gaps')
        self.assertIsNone(streaming_status({})['enhancement_lag_seconds'])

    def test_checkpoint_interval_bounds_advancing_output(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('aura.audio.enhanced_journal.time.monotonic', return_value=10) as clock:
            with (Path(directory) / 'enhanced.pcm').open('wb') as output:
                journal = EnhancedJournal(output, grouped=True)
                journal.write(bytes(960))
                clock.return_value = 10.99
                journal.write(bytes(960))
                self.assertEqual(journal.durable_samples, 0)
                clock.return_value = 11
                journal.write(bytes(960))
                self.assertEqual(journal.durable_samples, 1440)
