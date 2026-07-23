import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydub import AudioSegment

from aura.audio.enhancement_backends import (
    CLEARVOICE_PYTHON_ENV,
    CLEARVOICE_BACKEND,
    DEEPFILTERNET3_BACKEND,
    enhance_import_audio_if_available,
    import_enhancement_backend_for_policy,
)
from aura.audio.meeting_distance import (
    MEETING_DISTANCE_FAR_SPEAKER,
    MEETING_DISTANCE_NORMAL,
    MEETING_DISTANCE_RESCUE_OFFLINE,
    meeting_distance_policy_for,
)


def export_silence(path: Path):
    with path.open("wb") as target:
        AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")


class EnhancementBackendTests(unittest.TestCase):
    def test_import_backend_selection_follows_meeting_distance_policy(self):
        self.assertIsNone(import_enhancement_backend_for_policy(meeting_distance_policy_for(MEETING_DISTANCE_NORMAL)))
        self.assertEqual(
            import_enhancement_backend_for_policy(meeting_distance_policy_for(MEETING_DISTANCE_FAR_SPEAKER)),
            DEEPFILTERNET3_BACKEND,
        )
        self.assertEqual(
            import_enhancement_backend_for_policy(meeting_distance_policy_for(MEETING_DISTANCE_RESCUE_OFFLINE)),
            CLEARVOICE_BACKEND,
        )

    def test_normal_mode_does_not_request_model_backend(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            output = Path(tmpdir) / "enhanced.wav"
            export_silence(source)

            result = enhance_import_audio_if_available(source, output, MEETING_DISTANCE_NORMAL)

        self.assertEqual(result.status, "not_requested")
        self.assertIsNone(result.output_path)

    def test_far_speaker_backend_skips_when_deep_filter_cli_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch("aura.audio.enhancement_backends.shutil.which", return_value=None):
            source = Path(tmpdir) / "input.wav"
            output = Path(tmpdir) / "enhanced.wav"
            export_silence(source)

            result = enhance_import_audio_if_available(source, output, MEETING_DISTANCE_FAR_SPEAKER)

        self.assertEqual(result.backend, DEEPFILTERNET3_BACKEND)
        self.assertEqual(result.status, "skipped")
        self.assertIn("deep-filter", result.note)

    def test_rescue_backend_skips_when_clearvoice_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict("sys.modules", {"clearvoice": None}):
            source = Path(tmpdir) / "input.wav"
            output = Path(tmpdir) / "enhanced.wav"
            export_silence(source)

            result = enhance_import_audio_if_available(source, output, MEETING_DISTANCE_RESCUE_OFFLINE)

        self.assertEqual(result.backend, CLEARVOICE_BACKEND)
        self.assertEqual(result.status, "skipped")
        self.assertIn("clearvoice", result.note)

    def test_rescue_backend_can_use_external_clearvoice_python(self):
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.dict("sys.modules", {"clearvoice": None}),
            patch.dict("os.environ", {CLEARVOICE_PYTHON_ENV: "/opt/clearvoice/bin/python"}),
            patch("aura.audio.enhancement_backends.subprocess.run") as run,
        ):
            source = Path(tmpdir) / "input.wav"
            output = Path(tmpdir) / "enhanced.wav"
            export_silence(source)

            result = enhance_import_audio_if_available(source, output, MEETING_DISTANCE_RESCUE_OFFLINE)

        self.assertEqual(result.backend, CLEARVOICE_BACKEND)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output_path, output)
        self.assertEqual(run.call_args.args[0][0], "/opt/clearvoice/bin/python")
        runner = Path(run.call_args.args[0][1])
        self.assertEqual(runner.name, "run_clearvoice_enhancement.py")
        self.assertTrue(runner.is_file())


if __name__ == "__main__":
    unittest.main()
