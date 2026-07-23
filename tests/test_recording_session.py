import json
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from aura.audio.recording_session import (
    RecordingSession,
    discover_recoverable_sessions,
    recover_recording_session,
)
from aura.config import LIVE_CAPTURE_SYSTEM_MICROPHONE, SAMPLE_RATE


class RecordingSessionTests(unittest.TestCase):
    def test_system_and_microphone_recording_finalizes_three_durable_wavs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "meeting"
            session = RecordingSession.start(
                session_dir,
                recording_name="meeting",
                capture_mode=LIVE_CAPTURE_SYSTEM_MICROPHONE,
                sample_rate=SAMPLE_RATE,
                sample_width=2,
            )
            session.append_pcm(
                {
                    "mixed": b"\x01\x00\x02\x00",
                    "system": b"\x03\x00\x04\x00",
                    "microphone": b"\x05\x00\x06\x00",
                }
            )

            audio_tracks = session.finalize()

            manifest = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
            UUID(manifest["meeting_id"])
            self.assertEqual(manifest["status"], "ready")
            self.assertEqual(
                manifest["audio_tracks"],
                {
                    "microphone": "meeting_microphone.wav",
                    "mixed": "meeting.wav",
                    "system": "meeting_system.wav",
                },
            )
            self.assertEqual(audio_tracks, {name: session_dir / path for name, path in manifest["audio_tracks"].items()})
            for track, expected_pcm in {
                "mixed": b"\x01\x00\x02\x00",
                "system": b"\x03\x00\x04\x00",
                "microphone": b"\x05\x00\x06\x00",
            }.items():
                with wave.open(str(audio_tracks[track]), "rb") as recording:
                    self.assertEqual(recording.getnchannels(), 1)
                    self.assertEqual(recording.getsampwidth(), 2)
                    self.assertEqual(recording.getframerate(), SAMPLE_RATE)
                    self.assertEqual(recording.readframes(2), expected_pcm)

    def test_forced_interruption_is_discovered_read_only_and_explicitly_recovered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "interrupted"
            script = """
import os
import sys
from aura.audio.recording_session import RecordingSession
from aura.config import LIVE_CAPTURE_MICROPHONE, SAMPLE_RATE

session = RecordingSession.start(
    sys.argv[1],
    recording_name="interrupted",
    capture_mode=LIVE_CAPTURE_MICROPHONE,
    sample_rate=SAMPLE_RATE,
    sample_width=2,
)
session.append_pcm({"mixed": b"\\x11\\x00\\x22\\x00"})
session.checkpoint()
os._exit(23)
"""
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
            result = subprocess.run(
                [sys.executable, "-c", script, str(session_dir)],
                cwd=Path(__file__).parents[1],
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 23)

            manifest_path = session_dir / "session.json"
            before_discovery = manifest_path.read_bytes()
            candidates = discover_recoverable_sessions(tmpdir)

            self.assertEqual(candidates, [manifest_path])
            self.assertEqual(manifest_path.read_bytes(), before_discovery)
            original_meeting_id = json.loads(before_discovery)["meeting_id"]

            audio_tracks = recover_recording_session(manifest_path)

            recovered = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(recovered["meeting_id"], original_meeting_id)
            self.assertEqual(recovered["status"], "ready")
            self.assertEqual(recovered["recording_outcome"], "partial")
            self.assertEqual(recovered["recovery_original_status"], "recording")
            self.assertEqual(
                recovered["recovery_outcome"],
                "partial_audio_recovered",
            )
            self.assertNotEqual(recovered["recording_outcome"], "complete")
            self.assertTrue(recovered["recovery_acknowledged_at"])
            self.assertEqual(
                recovered["recovery_next_action"],
                "review_recovered_partial_audio",
            )
            self.assertEqual(discover_recoverable_sessions(tmpdir), [])
            with wave.open(str(audio_tracks["mixed"]), "rb") as recording:
                self.assertEqual(recording.readframes(2), b"\x11\x00\x22\x00")

    def test_ready_audio_without_transcript_artifacts_remains_discoverable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "ready-audio"
            session = RecordingSession.start(
                session_dir,
                recording_name="meeting",
                capture_mode=LIVE_CAPTURE_SYSTEM_MICROPHONE,
                sample_rate=SAMPLE_RATE,
                sample_width=2,
            )
            session.append_pcm({"mixed": b"\x01\x00"})
            session.finalize()
            manifest_path = session_dir / "session.json"

            self.assertEqual(discover_recoverable_sessions(tmpdir), [manifest_path])

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["prepared_transcript"] = "prepared_transcript.json"
            (session_dir / "prepared_transcript.json").write_text("{}\n", encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(discover_recoverable_sessions(tmpdir), [])

    def test_failed_session_with_partial_wav_and_no_journal_is_discoverable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "partial-audio"
            session_dir.mkdir()
            partial_wav = session_dir / "meeting.partial.wav"
            with wave.open(str(partial_wav), "wb") as recording:
                recording.setnchannels(1)
                recording.setsampwidth(2)
                recording.setframerate(SAMPLE_RATE)
                recording.writeframes(b"\x01\x00")
            manifest_path = session_dir / "session.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "meeting_id": "partial-meeting",
                        "status": "failed",
                        "pcm_journals": {},
                        "audio_tracks": {"mixed": partial_wav.name},
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(discover_recoverable_sessions(tmpdir), [manifest_path])

    def test_pcm_journal_flushes_each_second_and_fsyncs_each_five_seconds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("aura.audio.recording_session.time.monotonic", return_value=0.0):
                session = RecordingSession.start(
                    tmpdir,
                    recording_name="meeting",
                    capture_mode=LIVE_CAPTURE_SYSTEM_MICROPHONE,
                    sample_rate=SAMPLE_RATE,
                    sample_width=2,
                )
                session.append_pcm({"mixed": b"\x01\x00"})

            journal = Path(tmpdir) / ".capture" / "mixed.pcm"
            with (
                patch("aura.audio.recording_session.time.monotonic", return_value=1.0),
                patch("aura.audio.recording_session.os.fsync") as fsync,
            ):
                session.append_pcm({"mixed": b"\x02\x00"})
                self.assertEqual(journal.read_bytes(), b"\x01\x00\x02\x00")
                fsync.assert_not_called()

            with (
                patch("aura.audio.recording_session.time.monotonic", return_value=5.0),
                patch("aura.audio.recording_session.os.fsync") as fsync,
            ):
                session.append_pcm({"mixed": b"\x03\x00"})
                self.assertGreaterEqual(fsync.call_count, 1)

            session.finalize()

    def test_pcm_storage_error_marks_session_failed_and_preserves_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = RecordingSession.start(
                tmpdir,
                recording_name="meeting",
                capture_mode=LIVE_CAPTURE_SYSTEM_MICROPHONE,
                sample_rate=SAMPLE_RATE,
                sample_width=2,
            )
            original_open = Path.open

            def fail_pcm_open(path, *args, **kwargs):
                if path.name == "mixed.pcm":
                    raise OSError(28, "No space left on device")
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", fail_pcm_open):
                with self.assertRaisesRegex(OSError, "No space left"):
                    session.append_pcm({"mixed": b"\x01\x00"})

            manifest = json.loads((Path(tmpdir) / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["failure"]["error_class"], "OSError")
            self.assertIn("No space left", manifest["failure"]["message"])

    def test_recovery_discovery_skips_unrelated_session_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            unrelated = Path(tmpdir) / "other" / "session.json"
            unrelated.parent.mkdir()
            unrelated.write_text("[]\n", encoding="utf-8")

            self.assertEqual(discover_recoverable_sessions(tmpdir), [])

    def test_recovery_rejects_recording_name_that_escapes_session_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "meeting_session"
            journal = session_dir / ".capture" / "mixed.pcm"
            journal.parent.mkdir(parents=True)
            journal.write_bytes(b"\x01\x00")
            manifest_path = session_dir / "session.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "meeting_id": "meeting-id",
                        "status": "recoverable",
                        "recording_name": "../escaped",
                        "sample_rate": SAMPLE_RATE,
                        "sample_width": 2,
                        "pcm_journals": {"mixed": ".capture/mixed.pcm"},
                        "audio_tracks": {},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "recording_name"):
                recover_recording_session(manifest_path)

            self.assertFalse((Path(tmpdir) / "escaped.wav").exists())


if __name__ == "__main__":
    unittest.main()
