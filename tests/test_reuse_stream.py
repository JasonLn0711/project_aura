import unittest
import numpy as np
from aura.audio.reuse_stream import StreamingEnhancer


class StreamingTests(unittest.TestCase):
    def test_arbitrary_boundaries_preserve_waveform_and_length(self):
        for length in (0, 1, 17, 319, 320, 321, 480, 640, 641, 16017):
            audio = np.random.default_rng(7).normal(0, .1, length).astype(np.float32)
            for width in (1, 137, 480, 2048):
                with self.subTest(length=length, width=width):
                    stream = StreamingEnhancer(lambda spectrum: spectrum)
                    parts = [stream.push(audio[i:i + width]) for i in range(0, length, width)]
                    parts.append(stream.flush())
                    actual = np.concatenate(parts)
                    self.assertEqual(len(actual), length)
                    np.testing.assert_allclose(actual, audio, atol=1e-6)

    def test_output_arrives_before_close_and_memory_is_bounded(self):
        stream = StreamingEnhancer(lambda spectrum: spectrum)
        for _ in range(100):
            stream.push(np.zeros(480, np.float32))
            self.assertLess(len(stream.pending), 640)
            self.assertLessEqual(len(stream.tail), 640)
        self.assertGreater(stream.emitted, 0)
        stream.flush()
        with self.assertRaises(ValueError):
            stream.push(np.zeros(1))

    def test_invalid_model_output_fails(self):
        stream = StreamingEnhancer(lambda spectrum: spectrum * np.nan)
        with self.assertRaises(ValueError):
            stream.push(np.zeros(480))


class OfflineTests(unittest.TestCase):
    def test_overlap_add_preserves_long_and_short_inputs(self):
        import tempfile
        import wave
        from pathlib import Path
        from aura.audio.reuse_offline import enhance_wav
        for length in (1, 319, 16000, 80000, 80001, 120001, 200000):
            with self.subTest(length=length), tempfile.TemporaryDirectory() as tmp:
                source, target = Path(tmp) / 'source.wav', Path(tmp) / 'enhanced.wav'
                values = np.random.default_rng(9).integers(-16000, 16000, length, dtype='<i2')
                with wave.open(str(source), 'wb') as f:
                    f.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                    f.writeframes(values.tobytes())
                original = source.read_bytes()
                progress = []
                enhance_wav(source, target, lambda x: x, lambda n, total: progress.append((n, total)))
                with wave.open(str(target), 'rb') as f:
                    actual = np.frombuffer(f.readframes(length + 1), '<i2')
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(len(actual), length)
                np.testing.assert_allclose(actual, values, atol=1)
                self.assertEqual(progress[-1], (length, length))

    def test_failure_keeps_original_and_no_published_output(self):
        import tempfile
        import wave
        from pathlib import Path
        from aura.audio.reuse_offline import enhance_wav
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'source.wav', Path(tmp) / 'out.wav'
            with wave.open(str(source), 'wb') as f:
                f.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                f.writeframes(b'\0\0' * 1000)
            def fail(_):
                raise RuntimeError('GPU failure')
            with self.assertRaises(RuntimeError):
                enhance_wav(source, target, fail)
            self.assertTrue(source.exists())
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.wav.partial').exists())
