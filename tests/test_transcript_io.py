import json
import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from aura.ui.transcript_io import (
    SUMMARY_MARKER,
    collision_safe_transcript_base_path,
    event_log_payload,
    ensure_transcript_session,
    final_transcript_text,
    prepare_transcript,
    split_transcript_sections,
    transcript_artifact_paths,
    transcript_text_for_save,
    write_event_log_file,
    write_transcript_artifacts,
    write_transcript_file,
)


class TranscriptIoTests(unittest.TestCase):
    def test_transcript_session_reuses_recording_manifest_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "recording_session"
            session_dir.mkdir()
            manifest_path = session_dir / "session.json"
            manifest_path.write_text(
                json.dumps({"meeting_id": "recording-meeting-id", "status": "ready"}),
                encoding="utf-8",
            )

            session = ensure_transcript_session(Path(tmpdir) / "recording", workflow="recording")

            self.assertEqual(session.directory, session_dir)
            self.assertEqual(session.meeting_id, "recording-meeting-id")
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["meeting_id"], session.meeting_id)

    def test_transcript_session_creates_and_reuses_import_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "transcript_interview"

            first = ensure_transcript_session(base, workflow="import", source_path="/tmp/interview.mp3")
            second = ensure_transcript_session(base, workflow="import", source_path="/tmp/interview.mp3")

            self.assertEqual(first, second)
            self.assertEqual(first.directory, Path(tmpdir) / "transcript_interview_session")
            UUID(first.meeting_id)
            manifest = json.loads((first.directory / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["meeting_id"], first.meeting_id)
            self.assertEqual(manifest["workflow"], "import")
            self.assertEqual(manifest["status"], "ready")

    def test_transcript_session_rejects_a_different_import_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "transcript_interview"
            ensure_transcript_session(base, workflow="import", source_path="/a/interview.mp3")

            with self.assertRaisesRegex(ValueError, "different source"):
                ensure_transcript_session(base, workflow="import", source_path="/b/interview.mp3")

    def test_collision_safe_base_adds_stable_source_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "transcript_meeting"
            ensure_transcript_session(base, workflow="import", source_path="/a/meeting.mp3")

            resolved = collision_safe_transcript_base_path(base, "/b/meeting.mp3")

            self.assertNotEqual(resolved, base)
            self.assertTrue(resolved.name.startswith("transcript_meeting_"))
            self.assertEqual(
                collision_safe_transcript_base_path(resolved, "/b/meeting.mp3"),
                resolved,
            )

    def test_dotted_base_name_keeps_one_session_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "transcript_client.v1"

            session = ensure_transcript_session(
                base,
                workflow="import",
                source_path="/tmp/client.v1.mp3",
            )
            paths = transcript_artifact_paths(base)

            self.assertEqual(session.directory, Path(tmpdir) / "transcript_client.v1_session")
            self.assertEqual(paths["final"], Path(tmpdir) / "transcript_client.v1_final.txt")

    def test_prepare_transcript_applies_punctuation_then_glossary_and_hashes_corrected_text(self):
        prepared = prepare_transcript(
            "[00:00:01] 志德灣和 iMBS 開會",
            language="zh",
            enable_punctuation=True,
            enable_punctuation_model=False,
        )

        self.assertEqual(prepared.raw_text, "[00:00:01] 志德灣和 iMBS 開會")
        self.assertEqual(prepared.punctuated_text, "[00:00:01] 志德灣和 iMBS 開會。")
        self.assertEqual(prepared.corrected_text, "[00:00:01] 智德萬和 iMVS 開會。")
        self.assertEqual(
            prepared.content_sha256,
            "2e9a924b3cc29dd440fbba12f15a48f9f4cd180bcf8270df0e552aed67cfdf50",
        )
        self.assertEqual(len(prepared.correction_log), 2)

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

    def test_transcript_artifact_paths_use_base_path(self):
        paths = transcript_artifact_paths("/tmp/meeting")

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

    def test_write_transcript_artifacts_persists_the_exact_prepared_transcript(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "meeting"
            prepared = prepare_transcript(
                "[00:00:01] 志德灣和 iMBS 開會",
                language="zh",
                enable_punctuation=True,
                enable_punctuation_model=False,
            )

            saved = write_transcript_artifacts(base, prepared, metrics={})

            self.assertEqual(saved["raw"].read_text(encoding="utf-8"), "[00:00:01] 志德灣和 iMBS 開會\n")
            self.assertEqual(
                saved["corrected"].read_text(encoding="utf-8"),
                "[00:00:01] 智德萬和 iMVS 開會。\n",
            )
            manifest = json.loads(saved["prepared"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["corrected_text"], prepared.corrected_text)
            self.assertEqual(manifest["content_sha256"], prepared.content_sha256)
            metrics = json.loads(saved["metrics"].read_text(encoding="utf-8"))
            self.assertEqual(metrics["prepared_transcript_sha256"], prepared.content_sha256)

    def test_prepared_transcript_is_bound_to_the_session_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "meeting"
            session = ensure_transcript_session(base, workflow="import")
            prepared = prepare_transcript("確認內容。", language="zh")

            saved = write_transcript_artifacts(base, prepared, session=session)

            self.assertEqual(saved["prepared"], session.directory / "prepared_transcript.json")
            manifest = json.loads((session.directory / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["transcript_sha256"], prepared.content_sha256)
            self.assertEqual(manifest["prepared_transcript"], "prepared_transcript.json")


if __name__ == "__main__":
    unittest.main()
