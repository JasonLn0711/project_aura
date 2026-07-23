import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydub import AudioSegment

from aura.audio.normalization import FfmpegUnavailable, MP3_EXPORT_ARGS
from aura.audio.export import (
    M4A_EXPORT_ARGS,
    audio_path_for_wav,
    mp3_path_for_wav,
    normalize_wav_to_mp3,
    normalize_wav_to_recording_audio,
    recording_audio_format_spec,
)


class AudioExportTests(unittest.TestCase):
    def test_default_audio_path_for_wav_replaces_suffix_with_m4a(self):
        self.assertEqual(audio_path_for_wav("/tmp/example.wav"), Path("/tmp/example.m4a"))

    def test_mp3_path_for_wav_replaces_suffix(self):
        self.assertEqual(mp3_path_for_wav("/tmp/example.wav"), Path("/tmp/example.mp3"))

    def test_recording_audio_format_spec_rejects_unsupported_format(self):
        with self.assertRaises(ValueError):
            recording_audio_format_spec("flac")

    def test_normalize_wav_to_recording_audio_exports_m4a_and_removes_wav(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            audio_path = normalize_wav_to_recording_audio(wav_path, -20.0)

            self.assertEqual(audio_path, Path(tmpdir) / "recording.m4a")
            self.assertTrue(audio_path.exists())
            self.assertFalse(wav_path.exists())

    def test_normalize_wav_to_recording_audio_can_preserve_durable_mixed_track(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            audio_path = normalize_wav_to_recording_audio(
                wav_path,
                -20.0,
                remove_source=False,
            )

            self.assertTrue(audio_path.exists())
            self.assertTrue(wav_path.exists())

    def test_recording_export_can_retain_the_durable_wav(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            audio_path = normalize_wav_to_recording_audio(
                wav_path,
                -20.0,
                remove_source=False,
            )

            self.assertTrue(audio_path.exists())
            self.assertTrue(wav_path.exists())

    def test_normalize_wav_to_mp3_exports_and_removes_wav(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            mp3_path = normalize_wav_to_mp3(wav_path, -20.0)

            self.assertEqual(mp3_path, Path(tmpdir) / "recording.mp3")
            self.assertTrue(mp3_path.exists())
            self.assertFalse(wav_path.exists())

    def test_normalize_wav_to_recording_audio_falls_back_when_ffmpeg_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            with patch("aura.audio.export.normalize_media_with_ffmpeg", side_effect=FfmpegUnavailable):
                audio_path = normalize_wav_to_recording_audio(wav_path, -20.0)

            self.assertEqual(audio_path, Path(tmpdir) / "recording.m4a")
            self.assertTrue(audio_path.exists())
            self.assertFalse(wav_path.exists())

    def test_normalize_wav_to_recording_audio_falls_back_when_ffmpeg_fast_path_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            with patch("aura.audio.export.normalize_media_with_ffmpeg", side_effect=RuntimeError("ffmpeg failed")):
                audio_path = normalize_wav_to_recording_audio(wav_path, -20.0)

            self.assertEqual(audio_path, Path(tmpdir) / "recording.m4a")
            self.assertTrue(audio_path.exists())
            self.assertFalse(wav_path.exists())

    def test_normalize_wav_to_mp3_fallback_uses_high_quality_mp3_args(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            export_calls = []

            def fake_export(_segment, out_f, *args, **kwargs):
                export_calls.append(kwargs)
                out_f.write(b"ID3")

            with (
                patch("aura.audio.export.normalize_media_with_ffmpeg", side_effect=FfmpegUnavailable),
                patch.object(AudioSegment, "export", autospec=True, side_effect=fake_export),
            ):
                normalize_wav_to_mp3(wav_path, -20.0)

            self.assertEqual(export_calls[0]["parameters"], MP3_EXPORT_ARGS)

    def test_normalize_wav_to_recording_audio_fallback_uses_m4a_aac_args(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "recording.wav"
            with wav_path.open("wb") as target:
                AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")

            export_calls = []

            def fake_export(_segment, out_f, *args, **kwargs):
                export_calls.append(kwargs)
                out_f.write(b"M4A")

            with (
                patch("aura.audio.export.normalize_media_with_ffmpeg", side_effect=FfmpegUnavailable),
                patch.object(AudioSegment, "export", autospec=True, side_effect=fake_export),
            ):
                normalize_wav_to_recording_audio(wav_path, -20.0)

            self.assertEqual(export_calls[0]["format"], "ipod")
            self.assertEqual(export_calls[0]["parameters"], M4A_EXPORT_ARGS)


if __name__ == "__main__":
    unittest.main()
