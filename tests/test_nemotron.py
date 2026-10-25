import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from aura.diarization.nemotron import DiarizationSettings, merge_turns, validate_diarization_runtime, DiarizationDependencyError
from aura.diarization.live import label_segments, LiveDiarization
from aura.diarization.speaker_assignment import SpeakerTurn
from aura.session_core import SessionCore, options_for
from tests.fake_diarization import FakeDiarization


class NemotronTests(unittest.TestCase):
    def test_default_on_and_legacy_count_fields_are_retired(self):
        self.assertTrue(DiarizationSettings().enabled)
        self.assertTrue(options_for()['diarization'])
        self.assertNotIn('min_speakers', options_for({'min_speakers': 2, 'max_speakers': 6}))
        self.assertFalse(options_for({'diarization': False})['diarization'])
        with self.assertRaises(ValueError):
            DiarizationSettings(model_id='removed-model')

    def test_missing_runtime_does_not_block_explicit_disabled_mode(self):
        with patch('aura.diarization.nemotron.runtime_python', return_value=Path('/nonexistent/aura-python')):
            validate_diarization_runtime(DiarizationSettings(enabled=False))
            with self.assertRaises(DiarizationDependencyError):
                validate_diarization_runtime(DiarizationSettings())

    def test_preference_migration_runs_once_without_rewriting_sessions(self):
        with tempfile.TemporaryDirectory() as root:
            c = sqlite3.connect(Path(root) / 'sessions.sqlite3')
            c.execute('CREATE TABLE preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            c.execute("INSERT INTO preferences VALUES ('diarization','false')")
            c.commit(); c.close()
            core = SessionCore(root, executor=lambda *a: {}, diarization_factory=FakeDiarization)
            try:
                self.assertTrue(core.request('preferences.get')['diarization'])
                core.request('preferences.set', {'diarization': False})
            finally:
                core.close()
            core = SessionCore(root, executor=lambda *a: {}, diarization_factory=FakeDiarization)
            try:
                self.assertFalse(core.request('preferences.get')['diarization'])
            finally:
                core.close()

    def test_merge_preserves_overlap_and_silence(self):
        turns = [SpeakerTurn(0, 1, 'a'), SpeakerTurn(.5, 1.5, 'b'), SpeakerTurn(1, 2, 'a'), SpeakerTurn(3, 4, 'a')]
        self.assertEqual(merge_turns(turns), [SpeakerTurn(0, 2, 'a'), SpeakerTurn(.5, 1.5, 'b'), SpeakerTurn(3, 4, 'a')])

    def test_late_labels_wait_for_coverage_and_preserve_human_confirmation(self):
        segments = [dict(segment_id='s1', start_ms=0, end_ms=1000, text='hello', speaker='SPEAKER_UNKNOWN'),
                    dict(segment_id='s2', start_ms=0, end_ms=1000, text='edited', speaker='human', state='confirmed')]
        turns = [SpeakerTurn(0, 1, 'a'), SpeakerTurn(.5, .8, 'b')]
        final = set()
        self.assertFalse(label_segments(segments, turns, 15999, final))
        self.assertTrue(label_segments(segments, turns, 16000, final))
        self.assertEqual(segments[0]['speaker'], 'a')
        self.assertIn('speaker_overlap', segments[0]['review_flags'])
        self.assertEqual(segments[1]['speaker'], 'human')
        self.assertFalse(label_segments(segments, [], 32000, final))

    def test_live_results_persist_incrementally_and_recovery_preserves_prior_receipt(self):
        class Worker:
            receipt = {'model_id': 'test-double'}
            def __init__(self, directory): pass
            def request(self, command, **kwargs):
                if command == 'reset': return {}
                return dict(turns=[dict(start=0, end=.1, speaker='a')], active=['a'], processed_sample=1600, done=True)
            def close(self): pass
        with tempfile.TemporaryDirectory() as root:
            live = LiveDiarization(root, Path(root)/'audio.pcm', worker_factory=Worker)
            live.advance(1600, True); live.close()
            self.assertEqual(json.loads(live.output.read_text())['sequence'], 1)
            again = LiveDiarization(root, Path(root)/'audio.pcm', worker_factory=Worker)
            again.close()
            self.assertEqual(len(list(Path(root).glob('diarization-*.jsonl'))), 1)

class StreamingReaderTests(unittest.TestCase):
    def engine(self, path):
        from aura.diarization.worker import Engine
        from types import SimpleNamespace
        engine = Engine.__new__(Engine)
        engine.source = engine.decoder = None
        engine.processor = SimpleNamespace(num_samples_first_audio_chunk=16680,
            num_samples_per_audio_chunk=17040, audio_chunk_start=lambda frame: frame * 160 - 256)
        engine.reset(path)
        self.windows = []
        def predict(samples, final):
            self.windows.append((engine.frame, len(samples), final))
            engine.frame = (engine.read_samples + 159)//160 if final else engine.frame + 72
            return dict(done=final, turns=[], active=[], processed_sample=min(engine.frame*160, engine.read_samples))
        engine.predict = predict
        return engine

    def test_reader_waits_and_flushes_tail_with_bounded_buffer(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'input.pcm'
            path.write_bytes(bytes(16000*3*2+42))
            engine = self.engine(path)
            self.assertTrue(engine.advance(available=16000)['waiting'])
            result = None
            while not result or not result['done']:
                result = engine.advance(available=48021, final=True)
                self.assertLessEqual(len(engine.buffer), 17040*2)
            self.assertEqual(result['processed_sample'], 48021)
            self.assertEqual([x[0] for x in self.windows], [0,72,144,216])
            self.assertTrue(self.windows[-1][2])

    def test_reader_rejects_unpublished_or_incomplete_interval(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'input.pcm'; path.write_bytes(bytes(10))
            engine=self.engine(path)
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                engine.advance(available=20000)
            with self.assertRaises(ValueError):
                engine.advance(available=-1)

    def test_empty_stream_finishes_without_inference(self):
        with tempfile.TemporaryDirectory() as root:
            engine=self.engine(Path(root)/'absent.pcm')
            self.assertTrue(engine.advance(available=0, final=True)['done'])
            self.assertEqual(self.windows, [])


if __name__ == "__main__":
    unittest.main()
