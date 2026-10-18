import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from aura.audio.reuse import ReuseWorker


class WorkerContractTests(unittest.TestCase):
    def test_guarded_protocol_aligns_source_evidence_and_resets_interval(self):
        import base64
        import io
        import json
        import numpy as np
        from aura.audio.reuse_worker import main
        protected = []
        class Model:
            def __init__(self, mode, root): self.receipt = {}
            def predict(self, spectrum, *, protect_speech):
                protected.append(protect_speech)
                return spectrum
            def reset_stream(self): pass
        def push(count, speech):
            return dict(action='push', source_speech=speech,
                pcm=base64.b64encode(np.full(count,1000,'<i2').tobytes()).decode())
        requests = [dict(action='load',mode='live',root='test',live_policy='speech-guard-v1'),
            push(480,True),push(6400,False),dict(action='flush'),
            dict(action='reset',new_interval=True),push(480,False),dict(action='flush')]
        replies = io.StringIO()
        with patch('aura.audio.reuse_model.ReuseModel',Model), \
                patch('sys.stdin',io.StringIO('\n'.join(map(json.dumps,requests)))), \
                patch('sys.stdout',replies):
            self.assertEqual(main(),0)
        values = [json.loads(line) for line in replies.getvalue().splitlines()]
        self.assertTrue(all(v['ok'] for v in values))
        self.assertTrue(protected[0])
        self.assertFalse(any(protected[-3:]))
        self.assertEqual(sum(len(base64.b64decode(v['result'].get('pcm',''))) // 2 for v in values),7360)

    def test_reset_protocol_preserves_live_sample_clock_and_opens_flushed_intervals(self):
        import base64
        import io
        import json
        import numpy as np
        from aura.audio.reuse_worker import main
        models = []

        class Model:
            def __init__(self, mode, root):
                self.mode = mode
                self.receipt = {'backend': 'model-test-double'}
                self.resets = 0
                models.append(self)
            def predict(self, spectrum):
                return spectrum
            def reset_stream(self):
                self.resets += 1

        def push(count):
            return dict(action='push', pcm=base64.b64encode(np.full(count, 1000, '<i2').tobytes()).decode())
        requests = [dict(action='load', mode='live', root='test'), push(640), dict(action='reset'),
                    push(640), dict(action='flush'), dict(action='reset', new_interval=True),
                    push(480), dict(action='flush')]
        replies = io.StringIO()
        with patch('aura.audio.reuse_model.ReuseModel', Model), \
                patch('sys.stdin', io.StringIO('\n'.join(json.dumps(r) for r in requests))), \
                patch('sys.stdout', replies):
            self.assertEqual(main(), 0)
        values = [json.loads(line) for line in replies.getvalue().splitlines()]
        self.assertTrue(all(v['ok'] for v in values))
        lengths = [len(base64.b64decode(v['result'].get('pcm', ''))) // 2 for v in values]
        self.assertEqual(sum(lengths[:5]), 1280)
        self.assertEqual(sum(lengths[5:]), 480)
        self.assertEqual(models[0].resets, 2)

    def test_cpu_client_import_does_not_import_torch(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, '-c',
            'import sys; import aura.audio.reuse; assert "torch" not in sys.modules'], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_missing_runtime_fails_with_no_fallback(self):
        with TemporaryDirectory() as temp, patch.dict('os.environ', {'AURA_REUSE_RUNTIME': temp}):
            with self.assertRaisesRegex(RuntimeError, 'runtime is unavailable'):
                ReuseWorker('live')
