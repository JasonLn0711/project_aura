from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_summary_impact import build_report, discover_artifact_sets, load_domain_terms
from scripts.generate_paired_summary_artifacts import discover_candidates, generate_samples


class GeneratePairedSummaryArtifactsTests(unittest.TestCase):
    def make_log(self, log_dir: Path, name: str, entries: list[dict]) -> Path:
        path = log_dir / f"{name}_correction_log.json"
        path.write_text(
            json.dumps(
                {
                    "source_transcript": f"private/{name}.txt",
                    "correction_log": entries,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def sample_entries(self) -> list[dict]:
        return [
            {
                "accepted": True,
                "category": "organizations",
                "original": "志德灣",
                "corrected": "智德萬",
                "score": 100.0,
            },
            {
                "accepted": True,
                "category": "technical_terms",
                "original": "iMBS",
                "corrected": "iMVS",
                "score": 100.0,
            },
            {
                "accepted": False,
                "category": "technical_terms",
                "original": "detector",
                "corrected": "Detector+",
                "review_status": "denylist",
                "score": 94.12,
            },
            {
                "accepted": False,
                "category": "people",
                "original": "max",
                "corrected": "Max",
                "review_status": "manual_review_required",
                "score": 100.0,
            },
        ]

    def test_selects_logs_with_accepted_corrections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_dir = root / "logs"
            log_dir.mkdir()
            self.make_log(log_dir, "sample", self.sample_entries())
            self.make_log(
                log_dir,
                "rejected_only",
                [{"accepted": False, "category": "technical_terms", "original": "x", "corrected": "Y"}],
            )

            candidates = discover_candidates(log_dir, {"organizations", "technical_terms", "people"})

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].accepted_count, 2)
        self.assertEqual(candidates[0].category_count, 2)

    def test_generates_discoverable_paired_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_dir = root / "logs"
            output_dir = root / "artifacts"
            manifest_path = root / "manifest.json"
            log_dir.mkdir()
            self.make_log(log_dir, "sample", self.sample_entries())

            manifest = generate_samples(
                log_dir=log_dir,
                output_dir=output_dir,
                manifest_path=manifest_path,
                max_samples=1,
                min_samples=1,
            )
            artifact_sets = discover_artifact_sets([output_dir])

        self.assertEqual(manifest["selected_samples"], 1)
        self.assertEqual(len(artifact_sets), 1)
        self.assertIsNotNone(artifact_sets[0].raw_summary)
        self.assertIsNotNone(artifact_sets[0].corrected_summary)

    def test_manifest_and_reports_do_not_emit_raw_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_dir = root / "logs"
            output_dir = root / "artifacts"
            manifest_path = root / "manifest.json"
            log_dir.mkdir()
            self.make_log(log_dir, "sample", self.sample_entries())

            manifest = generate_samples(log_dir=log_dir, output_dir=output_dir, manifest_path=manifest_path, max_samples=1)
            report = build_report(discover_artifact_sets([output_dir]), load_domain_terms())
            serialized_manifest = json.dumps(manifest, ensure_ascii=False)
            serialized_report = json.dumps(report, ensure_ascii=False)

        self.assertNotIn("private meeting context", serialized_manifest)
        self.assertNotIn("private meeting context", serialized_report)
        self.assertFalse(manifest["raw_transcript_context_emitted"])
        self.assertFalse(report["scope"]["raw_transcript_context_emitted"])

    def test_rejected_and_manual_terms_are_excluded_from_corrected_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_dir = root / "logs"
            output_dir = root / "artifacts"
            log_dir.mkdir()
            self.make_log(log_dir, "sample", self.sample_entries())

            generate_samples(log_dir=log_dir, output_dir=output_dir, manifest_path=root / "manifest.json", max_samples=1)
            corrected_summary = next(output_dir.rglob("*_corrected_summary.txt")).read_text(encoding="utf-8")

        self.assertNotIn("Detector+", corrected_summary)
        self.assertNotIn("Max", corrected_summary)
        self.assertIn("智德萬", corrected_summary)
        self.assertIn("iMVS", corrected_summary)

    def test_generated_sample_allows_summary_impact_nonzero_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_dir = root / "logs"
            output_dir = root / "artifacts"
            log_dir.mkdir()
            self.make_log(log_dir, "sample", self.sample_entries())

            generate_samples(log_dir=log_dir, output_dir=output_dir, manifest_path=root / "manifest.json", max_samples=1)
            report = build_report(discover_artifact_sets([output_dir]), load_domain_terms())

        self.assertEqual(report["aggregate"]["evaluated_files"], 1)
        self.assertGreaterEqual(report["aggregate"]["corrected_canonical_terms_in_summary"], 2)
        self.assertEqual(report["aggregate"]["rejected_or_denied_term_leaks"], 0)
        self.assertEqual(report["aggregate"]["manual_review_term_leaks"], 0)


if __name__ == "__main__":
    unittest.main()
