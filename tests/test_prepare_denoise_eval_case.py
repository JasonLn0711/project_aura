import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.prepare_denoise_eval_case import (
    prepare_eval_case,
    read_reference_text,
)


class PrepareDenoiseEvalCaseTests(unittest.TestCase):
    def test_read_reference_text_rejects_ambiguous_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reference_file = Path(tmpdir) / "reference.txt"
            reference_file.write_text("hello", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "either --reference-text or --reference-file"):
                read_reference_text("hello", reference_file)

    def test_prepare_eval_case_runs_ffmpeg_and_fills_empty_templates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source.wav"
            source.write_bytes(b"audio")
            case_dir = Path(tmpdir) / "far_speaker_reverb"
            case_dir.mkdir()
            (case_dir / "reference.txt").write_text("", encoding="utf-8")
            (case_dir / "rare_terms.txt").write_text("", encoding="utf-8")
            (case_dir / "notes.md").write_text("# Notes\n", encoding="utf-8")

            with patch("scripts.prepare_denoise_eval_case.shutil.which", return_value="/usr/bin/ffmpeg"):
                with patch("scripts.prepare_denoise_eval_case.subprocess.run") as run:
                    output_path = prepare_eval_case(
                        source=source,
                        case_dir=case_dir,
                        start=3.5,
                        duration=45.0,
                        sample_rate=48000,
                        channels=1,
                        reference_text="trusted transcript",
                        rare_terms=["DeepFilterNet", "MossFormer"],
                        notes=["far table end"],
                    )

            self.assertEqual(output_path.name, "input.wav")
            command = run.call_args.args[0]
            self.assertIn("-ss", command)
            self.assertIn("3.5", command)
            self.assertIn("-t", command)
            self.assertIn("45.0", command)
            self.assertIn("-ar", command)
            self.assertIn("48000", command)
            self.assertEqual((case_dir / "reference.txt").read_text(encoding="utf-8").strip(), "trusted transcript")
            self.assertEqual(
                (case_dir / "rare_terms.txt").read_text(encoding="utf-8").splitlines(),
                ["DeepFilterNet", "MossFormer"],
            )
            self.assertIn("far table end", (case_dir / "notes.md").read_text(encoding="utf-8"))

    def test_prepare_eval_case_protects_existing_reference(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source.wav"
            source.write_bytes(b"audio")
            case_dir = Path(tmpdir) / "case"
            case_dir.mkdir()
            (case_dir / "reference.txt").write_text("existing", encoding="utf-8")

            with patch("scripts.prepare_denoise_eval_case.shutil.which", return_value="/usr/bin/ffmpeg"):
                with patch("scripts.prepare_denoise_eval_case.subprocess.run"):
                    with self.assertRaises(FileExistsError):
                        prepare_eval_case(
                            source=source,
                            case_dir=case_dir,
                            start=0,
                            duration=30,
                            sample_rate=48000,
                            channels=1,
                            reference_text="replacement",
                        )


if __name__ == "__main__":
    unittest.main()
