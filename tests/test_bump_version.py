import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/bump_version.py"

spec = importlib.util.spec_from_file_location("bump_version", SCRIPT_PATH)
bump_version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump_version)


class BumpVersionTests(unittest.TestCase):
    def test_normalize_version_accepts_tag_form_without_storing_v_prefix(self):
        self.assertEqual(bump_version.normalize_version("v1.6.0"), "1.6.0")

    def test_normalize_release_date_requires_iso_date(self):
        self.assertEqual(bump_version.normalize_release_date("2026-05-29"), "2026-05-29")
        with self.assertRaises(ValueError):
            bump_version.normalize_release_date("2026/05/29")

    def test_update_files_synchronizes_release_surfaces(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metadata_dir = root / "src/aura"
            metadata_dir.mkdir(parents=True)
            (root / "pyproject.toml").write_text('version = "1.5.1"\n', encoding="utf-8")
            (metadata_dir / "metadata.py").write_text(
                '__version__ = "1.5.1"\n__date__ = "2026-05-25"\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "| Refactor Version | `1.5.1` |\n"
                "| Current Release Tag | `v1.5.1` |\n",
                encoding="utf-8",
            )

            changed = bump_version.update_files("1.6.0", repo_root=root, release_date="2026-05-29")

            self.assertEqual(len(changed), 3)
            self.assertIn('version = "1.6.0"', (root / "pyproject.toml").read_text(encoding="utf-8"))
            self.assertIn('__version__ = "1.6.0"', (metadata_dir / "metadata.py").read_text(encoding="utf-8"))
            self.assertIn('__date__ = "2026-05-29"', (metadata_dir / "metadata.py").read_text(encoding="utf-8"))
            self.assertIn(
                "| Refactor Version | `1.6.0` |",
                (root / "README.md").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "| Current Release Tag | `v1.6.0` |",
                (root / "README.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
