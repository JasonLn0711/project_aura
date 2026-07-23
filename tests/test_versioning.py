import re
import unittest
from pathlib import Path

from aura.metadata import __date__, __version__
from aura.ui.messages import UI_TEXT


REPO_ROOT = Path(__file__).resolve().parents[1]
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class VersioningTests(unittest.TestCase):
    def test_package_metadata_version_matches_runtime_metadata(self):
        pyproject_block = (
            (REPO_ROOT / "pyproject.toml")
            .read_text(encoding="utf-8")
            .split("[project]", 1)[1]
            .split("\n[", 1)[0]
        )
        project_version = re.search(r'(?m)^version = "([^"]+)"$', pyproject_block)
        package_blocks = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8").split(
            "[[package]]"
        )
        locked_block = next(
            block
            for block in package_blocks
            if re.search(r'(?m)^name = "project-aura-refactor"$', block)
        )
        locked_version = re.search(r'(?m)^version = "([^"]+)"$', locked_block)

        self.assertIsNotNone(project_version)
        self.assertIsNotNone(locked_version)
        self.assertEqual(project_version.group(1), __version__)
        self.assertEqual(locked_version.group(1), __version__)
        self.assertRegex(__version__, SEMVER_PATTERN)
        self.assertFalse(__version__.startswith("v"))

    def test_readme_refactor_version_matches_runtime_metadata(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        match = re.search(r"\| Refactor Version \| `([^`]+)` \|", readme)

        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)

    def test_readme_published_and_candidate_tags_are_explicit(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        published = re.search(
            r"\| Latest Published Tag \| `([^`]+)` \|",
            readme,
        )
        candidate = re.search(
            r"\| Next Release Candidate \| `([^`]+)` \|",
            readme,
        )

        self.assertIsNotNone(published)
        self.assertIsNotNone(candidate)
        self.assertRegex(
            published.group(1),
            rf"^v{SEMVER_PATTERN.pattern[1:-1]}$",
        )
        self.assertEqual(candidate.group(1), f"v{__version__}")

    def test_readme_latest_update_and_footer_match_runtime_metadata(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(f"## Latest Update — v{__version__} ({__date__})", readme)
        self.assertIn(f"v{__version__} ({__date__})", UI_TEXT.footer())


if __name__ == "__main__":
    unittest.main()
