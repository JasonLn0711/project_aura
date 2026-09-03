import subprocess
import sys
import unittest
from pathlib import Path


class RetiredAsrBenchmarkTests(unittest.TestCase):
    def test_entrypoint_exits_before_loading_models(self):
        script = Path(__file__).parents[1] / "scripts" / "benchmark_aura_meetily_asr.py"
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)

        self.assertEqual(result.returncode, 2)
        self.assertIn("benchmark is retired", result.stderr)
        self.assertNotIn("faster_whisper", result.stderr)


if __name__ == "__main__":
    unittest.main()
