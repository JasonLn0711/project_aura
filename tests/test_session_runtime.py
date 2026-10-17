import unittest
from unittest.mock import patch

from aura.session_runtime import execute


class RuntimeDependencyTests(unittest.TestCase):
    def test_missing_server_dependency_has_recovery_commands(self):
        for module in ("pydub", "numpy", "faster_whisper"):
            error = ModuleNotFoundError(f"No module named '{module}'", name=module)
            with self.subTest(module=module), patch("builtins.__import__", side_effect=error):
                with self.assertRaises(RuntimeError) as caught:
                    execute("load", {"options": {"asr_model": "breeze"}})
            self.assertIn(str(error), str(caught.exception))
            self.assertIn("uv sync --locked --extra server --inexact", str(caught.exception))
            self.assertIn("uv run --no-sync aura", str(caught.exception))
            self.assertIs(caught.exception.__cause__, error)

    def test_unrecognized_import_failure_is_preserved(self):
        error = ModuleNotFoundError("No module named 'unexpected_plugin'", name="unexpected_plugin")
        with patch("builtins.__import__", side_effect=error):
            with self.assertRaises(ModuleNotFoundError) as caught:
                execute("load", {"options": {}})
        self.assertIs(caught.exception, error)
