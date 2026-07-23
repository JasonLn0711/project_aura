import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from aura.ui.transcription_tab import TranscriptionTab


class RecordingShutdownTests(unittest.TestCase):
    def test_app_shutdown_waits_for_recording_finalization_before_stopping_asr(self):
        events = []

        class Timer:
            def stop(self):
                pass

        class Recorder:
            running = True

            def wait(self, timeout):
                events.append(("recording_finalized", timeout))
                return True

        class Transcriber:
            def stop(self):
                events.append(("asr_stopped", None))

        tab = TranscriptionTab.__new__(TranscriptionTab)
        tab.close_recording_runtime_log = lambda: None
        tab.scheduled_start_timer = Timer()
        tab.scheduled_stop_timer = Timer()
        tab.recorder_thread = Recorder()
        tab.transcriber_thread = Transcriber()
        tab.file_thread = None
        tab.final_recording_thread = None
        tab.summary_thread = None
        tab.ollama_runtime_thread = None
        tab.ollama_pull_thread = None
        tab.ollama_server_started_by_aura = False
        tab.ollama_server_process = None

        tab.stop_threads()

        self.assertFalse(tab.recorder_thread.running)
        self.assertEqual(
            events,
            [
                ("recording_finalized", 5000),
                ("asr_stopped", None),
            ],
        )

    def test_recording_artifacts_wait_for_durable_audio_finalization(self):
        tab = TranscriptionTab.__new__(TranscriptionTab)
        tab.finalize_recording_pending = True
        tab.recorder_thread = object()
        tab.transcriber_thread = type("Transcriber", (), {"is_idle": lambda _self: True})()
        tab.current_recording_metrics = None
        tab.start_final_recording_pass = MagicMock(return_value=False)
        tab.check_llm_summary = type("Check", (), {"isChecked": lambda _self: False})()
        tab.save_and_clear_recording_transcript = MagicMock()

        with patch("aura.ui.transcription_tab.QTimer.singleShot") as reschedule:
            TranscriptionTab.finalize_recording_after_live_asr_idle(tab)

        tab.save_and_clear_recording_transcript.assert_not_called()
        reschedule.assert_called_once()

    def test_partial_capture_path_becomes_current_review_source_with_warning_provenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            partial = Path(tmpdir) / "meeting_partial.wav"
            partial.touch()
            recorder = SimpleNamespace(
                recording_session=SimpleNamespace(
                    manifest={"recording_outcome": "partial"}
                )
            )
            tab = TranscriptionTab.__new__(TranscriptionTab)
            tab.recorder_thread = recorder
            tab.finalize_recording_pending = True
            tab.current_recording_metrics = {}
            tab.set_review_audio_source = MagicMock()
            tab.process_audio = MagicMock()
            tab.append_recording_event = MagicMock()

            with patch("aura.ui.transcription_tab.QTimer.singleShot"):
                tab.on_recording_thread_finished(recorder, str(partial))

            tab.set_review_audio_source.assert_called_once_with(str(partial))
            tab.process_audio.assert_called_once_with(str(partial))
            self.assertEqual(
                tab.current_recording_metrics["recording_outcome"],
                "partial",
            )
            self.assertTrue(
                tab.current_recording_metrics["requires_human_confirmation"]
            )

    def test_complete_recording_name_ending_in_partial_is_not_misclassified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            complete = Path(tmpdir) / "meeting_partial.wav"
            complete.touch()
            recorder = SimpleNamespace(
                recording_session=SimpleNamespace(
                    manifest={"recording_outcome": "complete"}
                )
            )
            tab = TranscriptionTab.__new__(TranscriptionTab)
            tab.recorder_thread = recorder
            tab.finalize_recording_pending = True
            tab.current_recording_metrics = {}
            tab.set_review_audio_source = MagicMock()
            tab.process_audio = MagicMock()
            tab.append_recording_event = MagicMock()

            with patch("aura.ui.transcription_tab.QTimer.singleShot"):
                tab.on_recording_thread_finished(recorder, str(complete))

            self.assertNotIn("recording_outcome", tab.current_recording_metrics)
            self.assertNotIn(
                "requires_human_confirmation",
                tab.current_recording_metrics,
            )
            tab.append_recording_event.assert_not_called()

    def test_shutdown_copies_live_transcript_backup_into_recording_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backup = root / "temp_transcript.txt"
            backup.write_text("[00:00:01] 暫定逐字稿\n", encoding="utf-8")
            base = root / "meeting"
            tab = TranscriptionTab.__new__(TranscriptionTab)
            tab.current_recording_metrics = {
                "base_path": str(base),
                "source_path": str(base.with_suffix(".wav")),
            }

            with patch(
                "aura.ui.transcription_tab.transcript_backup_path",
                return_value=backup,
            ):
                preserved = tab.preserve_recording_shutdown_transcript()

            session_dir = root / "meeting_session"
            self.assertTrue(preserved)
            self.assertEqual(
                (session_dir / "provisional_transcript.txt").read_text(
                    encoding="utf-8"
                ),
                "[00:00:01] 暫定逐字稿\n",
            )

    def test_unowned_runtime_backup_is_retained_for_manual_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup = Path(tmpdir) / "temp_transcript.txt"
            backup.write_text("尚未歸檔", encoding="utf-8")
            tab = TranscriptionTab.__new__(TranscriptionTab)

            with patch(
                "aura.ui.transcription_tab.transcript_backup_path",
                return_value=backup,
            ):
                preserved = tab.preserve_recording_shutdown_transcript()

            self.assertFalse(preserved)
            self.assertTrue(backup.exists())


if __name__ == "__main__":
    unittest.main()
