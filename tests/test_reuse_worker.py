import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from aura.audio.reuse import ReuseWorker


class WorkerContractTests(unittest.TestCase):
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
