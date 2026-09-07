import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


class PackagedResourcesTests(unittest.TestCase):
    def test_wheel_excludes_summary_and_reads_glossary_outside_checkout(self) -> None:
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
            self.assertFalse(any(name.startswith(("summary/", "aura/llm/")) for name in names))
            self.assertIn("asr_postprocess/domain_glossary.yaml", names)
            self.assertIn("aura/audio/run_clearvoice_enhancement.py", names)

            run_dir = root / "isolated"
            run_dir.mkdir()
            code = """
import sys
sys.path.insert(0, sys.argv[1])
from importlib.resources import files
from aura.ui.transcript_io import prepare_transcript

assert "ClearVoice" in files("aura.audio").joinpath(
    "run_clearvoice_enhancement.py"
).read_text(encoding="utf-8")
prepared = prepare_transcript(
    "[00:00:01] 志德灣和 iMBS 開會",
    language="zh",
    enable_punctuation=False,
    enable_glossary_correction=True,
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
