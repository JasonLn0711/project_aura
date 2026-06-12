import tempfile
import unittest
from pathlib import Path

from aura.ui.transcript_io import (
    SUMMARY_MARKER,
    event_log_payload,
    final_transcript_text,
    split_transcript_sections,
    transcript_artifact_paths,
    transcript_text_for_save,
    write_event_log_file,
    write_transcript_artifacts,
    write_transcript_file,
)


class TranscriptIoTests(unittest.TestCase):
    def test_transcript_text_for_save_strips_and_adds_newline(self):
        self.assertEqual(transcript_text_for_save("  hello\n"), "hello\n")

    def test_transcript_text_for_save_keeps_empty_content_empty(self):
        self.assertEqual(transcript_text_for_save(" \n "), "")

    def test_write_transcript_file_creates_parent_and_writes_clean_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "transcript.txt"

            saved = write_transcript_file(path, "  [00:00:01] hello\n\n")

            self.assertTrue(saved)
            self.assertEqual(path.read_text(encoding="utf-8"), "[00:00:01] hello\n")

    def test_write_transcript_file_skips_empty_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "transcript.txt"

            saved = write_transcript_file(path, " \n ")

            self.assertFalse(saved)
            self.assertFalse(path.exists())

    def test_split_transcript_sections_extracts_raw_and_summary(self):
        raw, summary = split_transcript_sections(f"[00:00:01] hello\n\n{SUMMARY_MARKER}\n重點摘要")

        self.assertEqual(raw, "[00:00:01] hello")
        self.assertEqual(summary, "重點摘要")

    def test_final_transcript_text_combines_raw_and_summary(self):
        text = final_transcript_text("[00:00:01] hello", f"\n\n{SUMMARY_MARKER}\n重點摘要")

        self.assertEqual(text, f"[00:00:01] hello\n\n{SUMMARY_MARKER}\n重點摘要")

    def test_transcript_artifact_paths_use_base_stem(self):
        paths = transcript_artifact_paths("/tmp/meeting.txt")

        self.assertEqual(paths["raw"], Path("/tmp/meeting_raw.txt"))
        self.assertEqual(paths["corrected"], Path("/tmp/meeting_corrected.txt"))
        self.assertEqual(paths["final"], Path("/tmp/meeting_final.txt"))
        self.assertEqual(paths["summary"], Path("/tmp/meeting_summary.txt"))
        self.assertEqual(paths["correction_log"], Path("/tmp/meeting_correction_log.json"))
        self.assertEqual(paths["metrics"], Path("/tmp/meeting_processing_metrics.json"))
        self.assertEqual(paths["event_log"], Path("/tmp/meeting_event_log.json"))
        self.assertEqual(paths["runtime_log"], Path("/tmp/meeting_runtime.log"))

    def test_write_transcript_artifacts_writes_raw_corrected_final_summary_log_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "meeting"

            saved = write_transcript_artifacts(
                base,
                "[00:00:01] 志德灣和 iMBS 開會",
                f"\n\n{SUMMARY_MARKER}\n重點摘要",
                metrics={
                    "workflow": "unit",
                    "outputs": {"ignored": Path("/tmp/old")},
                    "status_events": [{"timestamp": "2026-06-11T17:00:00+08:00", "message": "started"}],
                },
            )

            self.assertEqual(
                set(saved),
                {"raw", "corrected", "final", "summary", "correction_log", "metrics", "event_log"},
            )
            self.assertEqual(saved["raw"].read_text(encoding="utf-8"), "[00:00:01] 志德灣和 iMBS 開會\n")
            self.assertEqual(saved["corrected"].read_text(encoding="utf-8"), "[00:00:01] 智德萬和 iMVS 開會\n")
            self.assertEqual(saved["summary"].read_text(encoding="utf-8"), "重點摘要\n")
            self.assertEqual(
                saved["final"].read_text(encoding="utf-8"),
                f"[00:00:01] 智德萬和 iMVS 開會\n\n{SUMMARY_MARKER}\n重點摘要\n",
            )
            correction_log_text = saved["correction_log"].read_text(encoding="utf-8")
            self.assertIn('"original": "志德灣"', correction_log_text)
            self.assertIn('"corrected": "iMVS"', correction_log_text)
            metrics_text = saved["metrics"].read_text(encoding="utf-8")
            self.assertIn('"workflow": "unit"', metrics_text)
            self.assertIn('"glossary_correction"', metrics_text)
            self.assertIn('"correction_count": 2', metrics_text)
            self.assertIn("meeting_final.txt", metrics_text)
            event_log_text = saved["event_log"].read_text(encoding="utf-8")
            self.assertIn('"events"', event_log_text)
            self.assertIn('"message": "started"', event_log_text)

    def test_write_event_log_file_writes_recording_events_and_runtime_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "recording"
            metrics = {
                "workflow": "recording",
                "source_path": str(base.with_suffix(".wav")),
                "base_path": str(base),
                "started_at": "2026-06-11T17:00:00+08:00",
                "recording_runtime_config": {"live_max_segment_len_sec": 16.0, "live_energy_gate_rms": 1000.0},
                "status_events": [
                    {
                        "timestamp": "2026-06-11T17:00:01+08:00",
                        "category": "live_asr_telemetry",
                        "queue_backlog": False,
                    }
                ],
            }

            path = write_event_log_file(base, metrics)

            self.assertEqual(path, Path(tmpdir) / "recording_event_log.json")
            payload = event_log_payload(metrics)
            self.assertEqual(payload["runtime_config"]["live_energy_gate_rms"], 1000.0)
            text = path.read_text(encoding="utf-8")
            self.assertIn('"workflow": "recording"', text)
            self.assertIn('"category": "live_asr_telemetry"', text)


if __name__ == "__main__":
    unittest.main()
