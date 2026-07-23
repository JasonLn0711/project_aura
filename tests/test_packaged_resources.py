import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


class PackagedResourcesTests(unittest.TestCase):
    def test_wheel_reads_prompts_and_default_glossary_outside_checkout(self) -> None:
        uv = shutil.which("uv")
        if not uv:
            self.skipTest("uv is required to build the release wheel")

        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            source.mkdir()
            for name in ("pyproject.toml", "README.md", "LICENSE"):
                shutil.copy2(repo / name, source / name)
            shutil.copytree(
                repo / "src",
                source / "src",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
            )

            dist = root / "dist"
            subprocess.run(
                [
                    uv,
                    "build",
                    "--wheel",
                    "--out-dir",
                    str(dist),
                    "--no-build-logs",
                    "--no-create-gitignore",
                    str(source),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            wheel = next(dist.glob("*.whl"))
            expected_prompts = {
                "action_items.system.txt",
                "decisions.system.txt",
                "executive_summary.system.txt",
                "format_repair.system.txt",
                "key_points.system.txt",
                "meeting_topic.system.txt",
                "next_steps.system.txt",
                "open_questions.system.txt",
                "participants.system.txt",
                "risks.system.txt",
            }
            for name in expected_prompts:
                self.assertEqual(
                    (
                        repo / "prompts" / "meeting_summary_layers" / name
                    ).read_bytes(),
                    (
                        repo
                        / "src"
                        / "summary"
                        / "meeting_summary_layers"
                        / name
                    ).read_bytes(),
                )
            self.assertEqual(
                (repo / "config" / "domain_glossary.yaml").read_bytes(),
                (
                    repo
                    / "src"
                    / "asr_postprocess"
                    / "domain_glossary.yaml"
                ).read_bytes(),
            )
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())
            self.assertTrue(
                {
                    f"summary/meeting_summary_layers/{name}"
                    for name in expected_prompts
                }.issubset(names)
            )
            self.assertIn("asr_postprocess/domain_glossary.yaml", names)
            self.assertIn("aura/audio/run_clearvoice_enhancement.py", names)

            run_dir = root / "isolated"
            run_dir.mkdir()
            code = """
import sys
sys.path.insert(0, sys.argv[1])
from importlib.resources import files
from summary.layered_summary_pipeline import read_extractor_prompt
from aura.ui.transcript_io import prepare_transcript

assert "Minimal valid output example" in read_extractor_prompt("meeting_topic")
assert "ClearVoice" in files("aura.audio").joinpath(
    "run_clearvoice_enhancement.py"
).read_text(encoding="utf-8")
prepared = prepare_transcript(
    "[00:00:01] 志德灣和 iMBS 開會",
    language="zh",
    enable_punctuation=False,
)
assert prepared.corrected_text == "[00:00:01] 智德萬和 iMVS 開會"
"""
            subprocess.run(
                [sys.executable, "-I", "-c", code, str(wheel)],
                cwd=run_dir,
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
