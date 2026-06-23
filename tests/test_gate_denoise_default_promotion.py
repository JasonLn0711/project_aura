import tempfile
import unittest
from pathlib import Path

from scripts.gate_denoise_default_promotion import (
    evaluate_promotion_gate,
    load_results,
    render_markdown,
)


def result(category, backend, status="ok", wer=None, cer=None, hits=None, misses=None):
    return {
        "category": category,
        "backend": backend,
        "meeting_distance_mode": "off" if backend == "off" else "far-speaker",
        "status": status,
        "input_path": "input.wav",
        "wer": wer,
        "cer": cer,
        "rare_term_hits": hits or [],
        "rare_term_misses": misses or [],
    }


class GateDenoiseDefaultPromotionTests(unittest.TestCase):
    def test_gate_passes_when_candidate_improves_reference_backed_metrics(self):
        results = [
            result("far_room_1", "off", wer=0.4, cer=0.3, hits=["A"], misses=["B"]),
            result("far_room_1", "deepfilternet3", wer=0.2, cer=0.15, hits=["A", "B"], misses=[]),
            result("far_room_2", "off", wer=0.5, cer=0.35, hits=["A"], misses=["B"]),
            result("far_room_2", "deepfilternet3", wer=0.3, cer=0.2, hits=["A", "B"], misses=[]),
        ]

        gate = evaluate_promotion_gate(
            results=results,
            report_path=Path("report.json"),
            baseline_backend="off",
            candidate_backend="deepfilternet3",
            min_cases=2,
            max_average_wer_delta=0.0,
            max_average_cer_delta=0.0,
            min_average_rare_hit_rate_delta=0.0,
        )

        self.assertTrue(gate.ready)
        self.assertEqual(gate.comparable_case_count, 2)
        self.assertLess(gate.average_wer_delta, 0)
        self.assertLess(gate.average_cer_delta, 0)
        self.assertGreater(gate.average_rare_hit_rate_delta, 0)

    def test_gate_blocks_when_reference_backed_metrics_are_missing(self):
        results = [
            result("far_room_1", "off", status="processed"),
            result("far_room_1", "deepfilternet3", status="processed"),
        ]

        gate = evaluate_promotion_gate(
            results=results,
            report_path=Path("report.json"),
            baseline_backend="off",
            candidate_backend="deepfilternet3",
            min_cases=1,
            max_average_wer_delta=0.0,
            max_average_cer_delta=0.0,
            min_average_rare_hit_rate_delta=0.0,
        )

        self.assertFalse(gate.ready)
        self.assertEqual(gate.comparable_case_count, 0)
        self.assertIn("comparable case count 0", gate.errors[0])
        self.assertIn("missing reference-backed ASR metrics", gate.cases[0].reason)

    def test_gate_blocks_rare_term_regression(self):
        results = [
            result("far_room_1", "off", wer=0.2, cer=0.1, hits=["A", "B"], misses=[]),
            result("far_room_1", "deepfilternet3", wer=0.2, cer=0.1, hits=["A"], misses=["B"]),
        ]

        gate = evaluate_promotion_gate(
            results=results,
            report_path=Path("report.json"),
            baseline_backend="off",
            candidate_backend="deepfilternet3",
            min_cases=1,
            max_average_wer_delta=0.0,
            max_average_cer_delta=0.0,
            min_average_rare_hit_rate_delta=0.0,
        )

        self.assertFalse(gate.ready)
        self.assertIn("rare-term", "\n".join(gate.errors))

    def test_load_results_and_render_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"
            report_path.write_text(
                '[{"category":"far_room","backend":"off","status":"ok","wer":0.1,"cer":0.1}]',
                encoding="utf-8",
            )

            results = load_results(report_path)
            gate = evaluate_promotion_gate(
                results=results,
                report_path=report_path,
                baseline_backend="off",
                candidate_backend="deepfilternet3",
                min_cases=1,
                max_average_wer_delta=0.0,
                max_average_cer_delta=0.0,
                min_average_rare_hit_rate_delta=0.0,
            )
            markdown = render_markdown(gate)

        self.assertEqual(results[0]["category"], "far_room")
        self.assertIn("# Denoise Default Promotion Gate", markdown)
        self.assertIn("missing deepfilternet3 result", markdown)


if __name__ == "__main__":
    unittest.main()
