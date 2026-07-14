import re
import tomllib
import unittest
from pathlib import Path

from aura.metadata import __date__, __version__
from aura.ui.messages import UI_TEXT


REPO_ROOT = Path(__file__).resolve().parents[1]
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class VersioningTests(unittest.TestCase):
    def test_package_metadata_version_matches_runtime_metadata(self):
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        uv_lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
        locked_project = next(
            package for package in uv_lock["package"] if package["name"] == "project-aura-refactor"
        )

        self.assertEqual(pyproject["project"]["version"], __version__)
        self.assertEqual(locked_project["version"], __version__)
        self.assertRegex(__version__, SEMVER_PATTERN)
        self.assertFalse(__version__.startswith("v"))

    def test_readme_refactor_version_matches_runtime_metadata(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        match = re.search(r"\| Refactor Version \| `([^`]+)` \|", readme)

        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)

    def test_readme_release_tag_matches_runtime_metadata(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        match = re.search(r"\| Current Release Tag \| `([^`]+)` \|", readme)

        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), f"v{__version__}")

    def test_readme_latest_update_and_footer_match_runtime_metadata(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(f"## Latest Update — v{__version__} ({__date__})", readme)
        self.assertIn(f"v{__version__} ({__date__})", UI_TEXT.footer())


if __name__ == "__main__":
    unittest.main()
