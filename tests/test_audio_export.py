import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydub import AudioSegment

from aura.audio.normalization import FfmpegUnavailable
from aura.audio.export import mp3_path_for_wav, normalize_wav_to_mp3


class AudioExportTests(unittest.TestCase):
    def test_mp3_path_for_wav_replaces_suffix(self):
        self.assertEqual(mp3_path_for_wav("/tmp/example.wav"), Path("/tmp/example.mp3"))

    def test_normalize_wav_to_mp3_exports_and_removes_wav(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            mp3_path = normalize_wav_to_mp3(wav_path, -20.0)

            self.assertEqual(mp3_path, Path(tmpdir) / "recording.mp3")
            self.assertTrue(mp3_path.exists())
            self.assertFalse(wav_path.exists())

    def test_normalize_wav_to_mp3_falls_back_when_ffmpeg_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            with patch("aura.audio.export.normalize_wav_to_mp3_with_ffmpeg", side_effect=FfmpegUnavailable):
                mp3_path = normalize_wav_to_mp3(wav_path, -20.0)

            self.assertEqual(mp3_path, Path(tmpdir) / "recording.mp3")
            self.assertTrue(mp3_path.exists())
            self.assertFalse(wav_path.exists())

    def test_normalize_wav_to_mp3_falls_back_when_ffmpeg_fast_path_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            with patch("aura.audio.export.normalize_wav_to_mp3_with_ffmpeg", side_effect=RuntimeError("ffmpeg failed")):
                mp3_path = normalize_wav_to_mp3(wav_path, -20.0)

            self.assertEqual(mp3_path, Path(tmpdir) / "recording.mp3")
            self.assertTrue(mp3_path.exists())
            self.assertFalse(wav_path.exists())


if __name__ == "__main__":
    unittest.main()
