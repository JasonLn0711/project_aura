import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aura.audio.enhancement_backends import enhance_import_audio_if_available


class EnhancementBackendTests(unittest.TestCase):
    def test_import_uses_offline_model_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, output = Path(tmp) / 'input.wav', Path(tmp) / 'enhanced.wav'
            original.write_bytes(b'original')
            with patch('aura.audio.enhancement_backends.subprocess.run') as decode, patch('aura.audio.reuse.ReuseWorker') as worker:
                result = enhance_import_audio_if_available(original, output)
            self.assertEqual(result.backend, 'nvidia/RE-USE')
            self.assertEqual(worker.call_args.args, ('offline',))
            self.assertEqual(original.read_bytes(), b'original')
            worker.return_value.__enter__.return_value.enhance_file.assert_called_once()
            self.assertIn('16000', decode.call_args.args[0])

    def test_failure_propagates_without_raw_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, output = Path(tmp) / 'input.wav', Path(tmp) / 'enhanced.wav'
            original.write_bytes(b'original')
            with patch('aura.audio.enhancement_backends.subprocess.run'), patch('aura.audio.reuse.ReuseWorker', side_effect=RuntimeError('CUDA failed')):
                with self.assertRaisesRegex(RuntimeError, 'CUDA failed'):
                    enhance_import_audio_if_available(original, output)
            self.assertEqual(original.read_bytes(), b'original')
            self.assertFalse(output.exists())

    def test_rejects_source_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'audio.wav'
            with self.assertRaises(ValueError):
                enhance_import_audio_if_available(source, source)
