import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydub import AudioSegment

from aura.asr.file_pipeline import (
    CancellationToken,
    FileTranscriptionCancelled,
    FileTranscriptionSettings,
    build_transcribe_kwargs,
    format_segment,
    normalize_file_transcription_error,
    prepare_import_audio,
    transcribe_file,
)
from aura.config import DEFAULT_PROMPT
from aura.diarization.pyannote_pipeline import DiarizationSettings
from aura.diarization.speaker_assignment import SpeakerTurn
from aura.system import runtime_paths


def export_silence(path: Path):
    with path.open("wb") as target:
        AudioSegment.silent(duration=100, frame_rate=16000).export(target, format="wav")


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return [SimpleNamespace(start=1.2, end=2.5, text=" hello")], SimpleNamespace()


class FilePipelineTests(unittest.TestCase):
    def test_format_segment_uses_hms_timestamp(self):
        segment = SimpleNamespace(start=3661.7, text=" hello")

        self.assertEqual(format_segment(segment), "[01:01:01]  hello")

    def test_build_transcribe_kwargs_omits_auto_language(self):
        kwargs = build_transcribe_kwargs(
            beam_size=3,
            language=None,
            initial_prompt=DEFAULT_PROMPT,
            condition_on_previous_text=True,
        )

        self.assertEqual(kwargs["beam_size"], 3)
        self.assertNotIn("language", kwargs)
        self.assertEqual(kwargs["initial_prompt"], DEFAULT_PROMPT)

    def test_normalize_file_transcription_error_adds_ffmpeg_guidance(self):
        message = normalize_file_transcription_error(RuntimeError("ffprobe not found"))

        self.assertIn("ffmpeg/ffprobe", message)

    def test_normalize_file_transcription_error_keeps_gpu_only_policy(self):
        message = normalize_file_transcription_error(RuntimeError("libcublas.so.12 not found"))

        self.assertIn("RTX/CUDA GPU", message)
        self.assertIn("CPU fallback is disabled", message)

    def test_prepare_import_audio_writes_temp_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "prepared.wav"
            export_silence(source)

            result = prepare_import_audio(
                file_path=str(source),
                settings=FileTranscriptionSettings(target_dbfs=-20.0),
                temp_path=target,
            )

            self.assertEqual(result, target)
            self.assertTrue(target.exists())

    def test_prepare_import_audio_surfaces_ffmpeg_progress(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            target = Path(tmpdir) / "prepared.wav"
            export_silence(source)
            statuses = []

            def fake_normalize_media_to_wav(file_path, temp_path, target_dbfs, progress_callback=None):
                self.assertEqual(file_path, str(source))
                self.assertEqual(temp_path, target)
                self.assertEqual(target_dbfs, -20.0)
                progress_callback("🔉 Volume normalization pass 2/2: 50%")
                target.write_bytes(b"RIFF")
                return target

            with (
                patch("aura.asr.file_pipeline.normalization_cpu_status", return_value="CPU count detected via test: 12; using 6 FFmpeg normalization threads (reserved 6)."),
                patch("aura.asr.file_pipeline.normalize_media_to_wav", side_effect=fake_normalize_media_to_wav),
            ):
                result = prepare_import_audio(
                    file_path=str(source),
                    settings=FileTranscriptionSettings(target_dbfs=-20.0),
                    temp_path=target,
                    status_callback=statuses.append,
                )

            self.assertEqual(result, target)
            self.assertIn("🧮 CPU count detected via test: 12; using 6 FFmpeg normalization threads (reserved 6).", statuses)
            self.assertIn("🔉 Volume normalization pass 2/2: 50%", statuses)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required for imported media containers")
    def test_prepare_import_audio_accepts_common_audio_video_containers(self):
        container_codecs = {
            "wav": ["-c:a", "pcm_s16le"],
            "mp3": ["-c:a", "libmp3lame"],
            "m4a": ["-c:a", "aac"],
            "mp4": ["-c:a", "aac"],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            for extension, codec_args in container_codecs.items():
                source = tmp_path / f"input.{extension}"
                target = tmp_path / f"prepared_{extension}.wav"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "sine=frequency=440:duration=0.1",
                        "-vn",
                        *codec_args,
                        str(source),
                    ],
                    check=True,
                )

                result = prepare_import_audio(
                    file_path=str(source),
                    settings=FileTranscriptionSettings(target_dbfs=-20.0),
                    temp_path=target,
                )

                self.assertEqual(result, target)
                self.assertTrue(target.exists(), extension)

    def test_prepare_import_audio_honors_pre_cancelled_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            export_silence(source)
            token = CancellationToken(cancelled=True)

            with self.assertRaises(FileTranscriptionCancelled):
                prepare_import_audio(
                    file_path=str(source),
                    settings=FileTranscriptionSettings(),
                    temp_path=Path(tmpdir) / "prepared.wav",
                    cancellation=token,
                )

    def test_transcribe_file_cleans_temp_and_writes_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            export_silence(source)
            model = FakeModel()
            statuses = []
            lines = []

            with patch.dict(os.environ, {runtime_paths.RUNTIME_DIR_ENV: tmpdir}):
                result = transcribe_file(
                    model=model,
                    file_path=str(source),
                    settings=FileTranscriptionSettings(beam_size=7, language="zh"),
                    worker_id="unit",
                    status_callback=statuses.append,
                    line_callback=lines.append,
                )

                self.assertEqual(result.lines, ["[00:00:01]  hello"])
                self.assertEqual(lines, ["[00:00:01]  hello"])
                self.assertIn("✅ Finished transcribing input.wav", statuses)
                self.assertFalse(runtime_paths.temp_normalized_path("unit").exists())
                self.assertEqual(
                    runtime_paths.transcript_backup_path().read_text(encoding="utf-8"),
                    "[00:00:01]  hello\n",
                )

            self.assertEqual(model.calls[0][1]["beam_size"], 7)
            self.assertEqual(model.calls[0][1]["language"], "zh")

    def test_transcribe_file_can_label_speakers_with_diarization_runner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "input.wav"
            export_silence(source)
            model = FakeModel()
            lines = []

            def fake_diarization_runner(path, settings):
                self.assertTrue(Path(path).exists())
                self.assertEqual(settings.min_speakers, 2)
                self.assertEqual(settings.max_speakers, 4)
                return [SpeakerTurn(start=1.0, end=3.0, speaker="SPEAKER_01")]

            with patch.dict(os.environ, {runtime_paths.RUNTIME_DIR_ENV: tmpdir}):
                result = transcribe_file(
                    model=model,
                    file_path=str(source),
                    settings=FileTranscriptionSettings(
                        diarization=DiarizationSettings(enabled=True, min_speakers=2, max_speakers=4)
                    ),
                    worker_id="unit-diar",
                    line_callback=lines.append,
                    diarization_runner=fake_diarization_runner,
                )

            self.assertEqual(result.lines, ["[00:00:01] SPEAKER_01:  hello"])
            self.assertEqual(lines, ["[00:00:01] SPEAKER_01:  hello"])


if __name__ == "__main__":
    unittest.main()
