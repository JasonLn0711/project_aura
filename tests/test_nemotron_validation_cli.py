"""CLI acceptance status using synthetic reports; never starts a model."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "validate_nemotron", Path(__file__).resolve().parents[1] / "scripts/validate_nemotron.py"
)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ValidationCliTests(unittest.TestCase):
    def test_exit_status_matches_completed_report_gate(self):
        for mode, report, expected in (
            ("stream", {"gate_outcome": "fail"}, 1),
            ("stream", {"gate_outcome": "pass"}, 0),
            ("file", {"status": "LIVE_FULL_COMPLETED"}, 0),
        ):
            with self.subTest(mode=mode, report=report), patch.object(
                validator, "run", return_value=report
            ) as run, patch("sys.argv", ["validate_nemotron", "synthetic.wav", "synthetic-output", "--mode", mode]):
                self.assertEqual(validator.main(), expected)
                run.assert_called_once_with(Path("synthetic.wav").resolve(), Path("synthetic-output").resolve(), mode)

    def test_runtime_failure_is_not_converted_to_success(self):
        with patch.object(validator, "run", side_effect=RuntimeError("synthetic failure")), patch(
            "sys.argv", ["validate_nemotron", "synthetic.wav", "synthetic-output", "--mode", "stream"]
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                validator.main()


if __name__ == "__main__":
    unittest.main()
