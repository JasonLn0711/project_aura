import tempfile
import unittest
from pathlib import Path

from pydub import AudioSegment

from scripts.evaluate_denoise_backends import (
    BackendResult,
    character_error_rate,
    discover_eval_cases,
    ensure_supported_backends,
    evaluate_case_backend,
    meeting_distance_mode_for_backend,
    recommend_backends_by_category,
    render_markdown,
    transcribe_audio,
    word_error_rate,
    write_reports,
)


def export_silence(path: Path):
    with path.open("wb") as target:
        AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")


class EvaluateDenoiseBackendsTests(unittest.TestCase):
    def test_error_rate_helpers(self):
        self.assertEqual(character_error_rate("abc", "abc"), 0.0)
        self.assertAlmostEqual(character_error_rate("abc", "axc"), 1 / 3)
        self.assertEqual(word_error_rate("one two", "one two"), 0.0)
        self.assertAlmostEqual(word_error_rate("one two", "one three"), 0.5)

    def test_discover_eval_cases_reads_reference_and_rare_terms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            case_dir = Path(tmpdir) / "far_room"
            case_dir.mkdir()
            export_silence(case_dir / "input.wav")
            (case_dir / "reference.txt").write_text("hello domain term", encoding="utf-8")
            (case_dir / "rare_terms.txt").write_text("domain term\n# comment\n", encoding="utf-8")

            cases = discover_eval_cases(Path(tmpdir))

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].category, "far_room")
        self.assertEqual(cases[0].reference_text, "hello domain term")
        self.assertEqual(cases[0].rare_terms, ["domain term"])

    def test_ensure_supported_backends_rejects_unknown_backend(self):
        with self.assertRaisesRegex(ValueError, "Unsupported backends"):
            ensure_supported_backends(["off", "unknown"])

    def test_meeting_distance_mode_for_backend(self):
        self.assertEqual(meeting_distance_mode_for_backend("off"), "off")
        self.assertEqual(meeting_distance_mode_for_backend("noisereduce-light"), "normal")
        self.assertEqual(meeting_distance_mode_for_backend("deepfilternet3"), "far-speaker")
        self.assertEqual(meeting_distance_mode_for_backend("clearvoice"), "rescue-offline")

    def test_evaluate_off_backend_processes_without_transcription(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            case_dir = Path(tmpdir) / "quiet"
            case_dir.mkdir()
            export_silence(case_dir / "input.wav")
            case = discover_eval_cases(Path(tmpdir))[0]

            result = evaluate_case_backend(
                case=case,
                backend="off",
                output_dir=Path(tmpdir) / "out",
                model_id=None,
                device="cuda",
                compute_type="int8",
                language="zh",
            )

        self.assertEqual(result.status, "processed")
        self.assertEqual(result.meeting_distance_mode, "off")
        self.assertIn("transcription skipped", result.note)
        self.assertIsNotNone(result.processed_path)

    def test_transcription_rejects_cpu_before_loading_model(self):
        with self.assertRaisesRegex(ValueError, "requires --device cuda"):
            transcribe_audio(
                Path("unused.wav"),
                model_id="unused",
                device="cpu",
                compute_type="int8",
                language="zh",
            )

    def test_recommend_backends_by_category_prefers_transcript_quality(self):
        results = [
            BackendResult(
                category="far_room",
                backend="off",
                meeting_distance_mode="off",
                status="ok",
                input_path="input.wav",
                wer=0.42,
                cer=0.31,
                rare_term_hits=["DeepFilterNet"],
                rare_term_misses=["MossFormer"],
                runtime_seconds=1.0,
            ),
            BackendResult(
                category="far_room",
                backend="deepfilternet3",
                meeting_distance_mode="far-speaker",
                status="ok",
                input_path="input.wav",
                wer=0.25,
                cer=0.2,
                rare_term_hits=["DeepFilterNet", "MossFormer"],
                rare_term_misses=[],
                runtime_seconds=2.0,
            ),
            BackendResult(
                category="far_room",
                backend="clearvoice",
                meeting_distance_mode="rescue-offline",
                status="skipped",
                input_path="input.wav",
                note="missing dependency",
            ),
        ]

        recommendations = recommend_backends_by_category(results)

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].recommended_backend, "deepfilternet3")
        self.assertEqual(recommendations[0].recommended_mode, "far-speaker")
        self.assertEqual(recommendations[0].compared_backends, ["off", "deepfilternet3"])
        self.assertEqual(recommendations[0].skipped_backends, ["clearvoice"])
        self.assertIn("WER 0.2500", recommendations[0].reason)

    def test_recommend_backends_requires_reference_backed_metrics(self):
        results = [
            BackendResult(
                category="far_room",
                backend="off",
                meeting_distance_mode="off",
                status="processed",
                input_path="input.wav",
                runtime_seconds=1.0,
            )
        ]

        recommendations = recommend_backends_by_category(results)

        self.assertIsNone(recommendations[0].recommended_backend)
        self.assertIn("No recommendation", recommendations[0].reason)

    def test_render_and_write_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            case_dir = Path(tmpdir) / "quiet"
            case_dir.mkdir()
            export_silence(case_dir / "input.wav")
            case = discover_eval_cases(Path(tmpdir))[0]
            result = evaluate_case_backend(
                case=case,
                backend="off",
                output_dir=Path(tmpdir) / "out",
                model_id=None,
                device="cuda",
                compute_type="int8",
                language="zh",
            )
            report_path = Path(tmpdir) / "report.md"

            write_reports([result], report_path)
            markdown = render_markdown([result])
            self.assertTrue(report_path.exists())
            self.assertTrue(report_path.with_suffix(".json").exists())

        self.assertIn("| quiet | off | off | processed |", markdown)
        self.assertIn("## Recommendation by Category", markdown)
        self.assertIn("reference-backed ASR metrics are unavailable", markdown)


if __name__ == "__main__":
    unittest.main()
