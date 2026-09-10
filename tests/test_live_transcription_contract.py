import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from aura.asr.hotwords import normalize_hotwords, validate_context
from aura.asr.punctuation import restore_chinese_punctuation, insert_punctuation_by_offsets
from aura.audio.vad import SpeechIntervals, SileroStreamVAD
from aura.audio.fastenhancer import enhance


class LiveTranscriptionContractTests(unittest.TestCase):
    def test_adaptive_endpoints_and_continuous_audio(self):
        frame = np.ones(480, np.int16)
        # Short speech retains 800 ms; a longer phrase can end on a shorter pause.
        for strategy, speech_frames, silence_frames in (("adaptive", 100, 27),
                                                       ("adaptive", 500, 20),
                                                       ("fixed", 500, 27)):
            with self.subTest(strategy=strategy, speech_frames=speech_frames):
                intervals = SpeechIntervals(480, max_seconds=20, segmentation=strategy)
                for _ in range(speech_frames):
                    self.assertIsNone(intervals.push(frame, True))
                for _ in range(silence_frames - 1):
                    self.assertIsNone(intervals.push(frame, False))
                chunk = intervals.push(frame, False)
                self.assertIsNotNone(chunk)
                self.assertTrue(chunk.terminal)
                self.assertEqual(chunk.split_reason, "silence")
                for _ in range(800):
                    self.assertIsNone(intervals.push(frame, False))
                self.assertIsNone(intervals.finish())

        intervals = SpeechIntervals(480, max_seconds=20, segmentation="adaptive")
        chunks = []
        frames = [np.full(480, i, np.int16) for i in range(1400)]
        for frame in frames:
            chunk = intervals.push(frame, True)
            if chunk is not None:
                self.assertFalse(chunk.terminal)
                self.assertEqual(chunk.split_reason, "max_duration")
                self.assertEqual(len(chunk.samples), 667 * 480)  # 20 s rounded to a frame.
                chunks.append(chunk)
        chunks.append(intervals.finish("stop"))
        self.assertEqual(chunks[-1].split_reason, "stop")
        self.assertTrue(chunks[-1].terminal)
        for left, right in zip(chunks, chunks[1:]):
            self.assertEqual(left.end_sample, right.start_sample)
        np.testing.assert_array_equal(np.concatenate([c.samples for c in chunks]),
                                      np.concatenate(frames).astype(np.float32) / 32768)

    def test_intervals_preserve_pauses_and_source_time_across_forced_splits(self):
        intervals = SpeechIntervals(480, max_seconds=0.12, pre_roll_ms=60, silence_ms=90)
        chunks = []
        frames = [np.full(480, i, np.int16) for i in range(12)]
        for i, frame in enumerate(frames):
            chunk = intervals.push(frame, i in (4, 5, 7))
            if chunk is not None:
                chunks.append(chunk)
        tail = intervals.finish()
        if tail is not None:
            chunks.append(tail)
        self.assertEqual(chunks[0].start_sample, 2 * 480)
        self.assertFalse(chunks[0].terminal)
        for left, right in zip(chunks, chunks[1:]):
            self.assertEqual(left.end_sample, right.start_sample)
        actual = np.concatenate([c.samples for c in chunks])
        np.testing.assert_array_equal(actual, np.concatenate(frames[2:11]).astype(np.float32) / 32768)
        self.assertTrue(chunks[-1].terminal)

    def test_silero_retains_recurrent_state_and_resets_between_streams(self):
        seen = []
        class Session:
            def get_inputs(self):
                return [SimpleNamespace(name=n) for n in ('input', 'h', 'c')]
            def run(self, _, feed):
                seen.append(feed['h'].copy())
                return np.array([0.6]), feed['h'] + 1, feed['c'] + 1
        with patch('faster_whisper.vad.get_vad_model', return_value=SimpleNamespace(session=Session())):
            first = SileroStreamVAD()
            for _ in range(3):
                first.is_speech(np.zeros(480, np.int16).tobytes(), 16000)
            second = SileroStreamVAD()
            second.is_speech(np.zeros(512, np.int16).tobytes(), 16000)
        self.assertEqual([float(x.flat[0]) for x in seen], [0, 1, 0])
        self.assertEqual(len(first.pending), 416)

    def test_hotwords_handle_real_tokenizer_encoding_and_reject_overflow(self):
        self.assertEqual(normalize_hotwords(' namespace\n\ntoken\nnamespace\n'), ('namespace', 'token'))
        tokenizer = SimpleNamespace(encode=lambda text: SimpleNamespace(ids=list(text)))
        validate_context(tokenizer, '', 'namespace token')
        with self.assertRaises(ValueError):
            validate_context(tokenizer, 'a' * 150, 'b' * 60)

    def test_partial_punctuation_and_content_guard(self):
        text = '今天開會，討論 namespace token 版本3.14以及後續工作'
        called = []
        restorer = SimpleNamespace(restore=lambda value: called.append(value) or value + '。')
        result = restore_chinese_punctuation(text, 'zh', restorer=restorer)
        self.assertEqual(result.backend, 'model')
        self.assertEqual(called, [text])
        bad = SimpleNamespace(restore=lambda value: value.replace('token', '憑證'))
        result = restore_chinese_punctuation(text, 'zh', restorer=bad)
        self.assertEqual(result.backend, 'rule_fallback')
        self.assertIn('token', result.text)
        self.assertEqual(insert_punctuation_by_offsets('namespace', {4: '，'}), 'namespace')
        self.assertEqual(restore_chinese_punctuation('這是尚未結束的句子', 'zh', enable_model=False, terminal=False).text, '這是尚未結束的句子')

    def test_mixed_error_rate_counts_mandarin_characters_and_english_words(self):
        from scripts.evaluate_denoise_backends import mixed_error_rate
        self.assertEqual(mixed_error_rate("今天 namespace token", "今天，namespace token。"), 0.0)
        self.assertEqual(mixed_error_rate("今天 namespace token", "今天 namespace mistake"), 0.25)

    def test_fastenhancer_delay_and_per_utterance_state(self):
        class Session:
            def get_inputs(self):
                return [SimpleNamespace(name='wav_in', shape=[1, 256]), SimpleNamespace(name='cache_in_0', shape=[1, 256])]
            def run(self, _, feed):
                return feed['cache_in_0'], feed['wav_in'].copy()
        for length in (1, 255, 256, 257, 1000):
            source = np.linspace(-0.5, 0.5, length, dtype=np.float32)
            np.testing.assert_array_equal(enhance(source, session=Session()), source)


if __name__ == '__main__':
    unittest.main()
