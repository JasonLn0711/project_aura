import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.check_denoise_eval_workspace import check_workspace, render_markdown
from scripts.init_denoise_eval_workspace import DEFAULT_CATEGORIES, init_workspace


class DenoiseEvalWorkspaceTests(unittest.TestCase):
    def test_default_workspace_categories_cover_minimum_gate_cases(self):
        self.assertGreaterEqual(len(DEFAULT_CATEGORIES), 10)
        self.assertIn("far_speaker_reverb", DEFAULT_CATEGORIES)
        self.assertIn("rescue_offline", DEFAULT_CATEGORIES)

    def test_init_workspace_creates_case_templates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "eval"

            created = init_workspace(workspace, categories=("far_speaker_reverb", "rare_terms"))

            self.assertEqual(len(created), 2)
            self.assertTrue((workspace / "README.md").exists())
            self.assertTrue((workspace / "far_speaker_reverb" / "notes.md").exists())
            self.assertTrue((workspace / "rare_terms" / "reference.txt").exists())
            self.assertTrue((workspace / "rare_terms" / "rare_terms.txt").exists())

    def test_check_workspace_requires_ready_case_count_and_reference(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "eval"
            init_workspace(workspace, categories=("far_speaker_reverb",))
            (workspace / "far_speaker_reverb" / "input.wav").write_bytes(b"RIFF")

            with patch("scripts.check_denoise_eval_workspace.probe_duration_seconds", return_value=45.0):
                check = check_workspace(workspace, min_cases=1)

        self.assertFalse(check.ready)
        self.assertEqual(check.ready_case_count, 0)
        self.assertIn("missing trusted reference.txt", check.cases[0].errors[0])

    def test_check_workspace_ready_when_input_and_reference_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "eval"
            init_workspace(workspace, categories=("far_speaker_reverb",))
            case_dir = workspace / "far_speaker_reverb"
            (case_dir / "input.wav").write_bytes(b"RIFF")
            (case_dir / "reference.txt").write_text("trusted transcript", encoding="utf-8")
            (case_dir / "rare_terms.txt").write_text("DeepFilterNet\n", encoding="utf-8")

            with patch("scripts.check_denoise_eval_workspace.probe_duration_seconds", return_value=45.0):
                check = check_workspace(workspace, min_cases=1)
                markdown = render_markdown(check)

        self.assertTrue(check.ready)
        self.assertEqual(check.ready_case_count, 1)
        self.assertIn("| far_speaker_reverb | True | 45.0 |", markdown)

    def test_check_workspace_rejects_full_recording_reference_for_short_clip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "eval"
            init_workspace(workspace, categories=("far_speaker_reverb",))
            case_dir = workspace / "far_speaker_reverb"
            (case_dir / "input.wav").write_bytes(b"RIFF")
            (case_dir / "reference.txt").write_text("全段逐字稿" * 700, encoding="utf-8")
            (case_dir / "rare_terms.txt").write_text("DeepFilterNet\n", encoding="utf-8")

            with patch("scripts.check_denoise_eval_workspace.probe_duration_seconds", return_value=60.0):
                check = check_workspace(workspace, min_cases=1)

        self.assertFalse(check.ready)
        self.assertIn("clip-level trusted reference", check.cases[0].errors[0])


if __name__ == "__main__":
    unittest.main()
