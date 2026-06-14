import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aura.diarization.pyannote_pipeline import (
    AURA_HF_TOKEN_FILE_ENV,
    DiarizationDependencyError,
    DiarizationSettings,
    diarize_audio_file,
    huggingface_token,
    pipeline_kwargs,
    validate_diarization_runtime,
)
from aura.diarization.speaker_assignment import (
    UNKNOWN_SPEAKER,
    SpeakerTurn,
    TranscriptSegment,
    assign_speakers,
    speaker_for_segment,
)


class SpeakerAssignmentTests(unittest.TestCase):
    def test_assigns_speaker_with_largest_overlap(self):
        segment = TranscriptSegment(start=10.0, end=16.0, text="hello")
        turns = [
            SpeakerTurn(start=9.0, end=11.0, speaker="SPEAKER_00"),
            SpeakerTurn(start=11.0, end=17.0, speaker="SPEAKER_01"),
        ]

        self.assertEqual(speaker_for_segment(segment, turns), "SPEAKER_01")

    def test_assigns_unknown_when_no_turn_matches(self):
        segment = TranscriptSegment(start=30.0, end=32.0, text="hello")
        turns = [SpeakerTurn(start=9.0, end=11.0, speaker="SPEAKER_00")]

        self.assertEqual(speaker_for_segment(segment, turns), UNKNOWN_SPEAKER)

    def test_assign_speakers_preserves_transcript_order(self):
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="a"),
            TranscriptSegment(start=3.0, end=4.0, text="b"),
        ]
        turns = [
            SpeakerTurn(start=0.0, end=2.5, speaker="SPEAKER_00"),
            SpeakerTurn(start=2.5, end=5.0, speaker="SPEAKER_01"),
        ]

        labels = assign_speakers(segments, turns)

        self.assertEqual([item.speaker for item in labels], ["SPEAKER_00", "SPEAKER_01"])
        self.assertEqual([item.transcript.text for item in labels], ["a", "b"])

    def test_pipeline_kwargs_uses_exact_count_when_min_equals_max(self):
        settings = DiarizationSettings(enabled=True, min_speakers=3, max_speakers=3)

        self.assertEqual(pipeline_kwargs(settings), {"num_speakers": 3})

    def test_pipeline_kwargs_uses_range_when_bounds_differ(self):
        settings = DiarizationSettings(enabled=True, min_speakers=2, max_speakers=5)

        self.assertEqual(pipeline_kwargs(settings), {"min_speakers": 2, "max_speakers": 5})

    def test_rejects_invalid_speaker_range(self):
        with self.assertRaises(ValueError):
            DiarizationSettings(enabled=True, min_speakers=4, max_speakers=2)

    def test_validate_diarization_runtime_noops_when_disabled(self):
        validate_diarization_runtime(DiarizationSettings(enabled=False))

    def test_validate_diarization_runtime_reports_missing_pyannote_dependency(self):
        with (
            patch("aura.diarization.pyannote_pipeline.pyannote_audio_available", return_value=False),
            self.assertRaisesRegex(DiarizationDependencyError, r"pyannote\.audio"),
        ):
            validate_diarization_runtime(DiarizationSettings(enabled=True))

    def test_validate_diarization_runtime_reports_missing_hugging_face_token(self):
        with (
            patch("aura.diarization.pyannote_pipeline.pyannote_audio_available", return_value=True),
            patch("aura.diarization.pyannote_pipeline.local_hf_token_secret_paths", return_value=()),
            patch.dict("os.environ", {}, clear=True),
            self.assertRaisesRegex(DiarizationDependencyError, "Hugging Face access token"),
        ):
            validate_diarization_runtime(DiarizationSettings(enabled=True))

    def test_huggingface_token_loads_local_secret_file(self):
        with TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "hf.env"
            secret_path.write_text(
                "\n".join(
                    [
                        "# local secret",
                        "export HF_TOKEN=hf_from_file",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {AURA_HF_TOKEN_FILE_ENV: str(secret_path)}, clear=True):
                self.assertEqual(huggingface_token(), "hf_from_file")

    def test_huggingface_token_prefers_environment_over_local_secret_file(self):
        with TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "hf.env"
            secret_path.write_text("export HF_TOKEN=hf_from_file\n", encoding="utf-8")

            with patch.dict(
                "os.environ",
                {
                    AURA_HF_TOKEN_FILE_ENV: str(secret_path),
                    "HF_TOKEN": "hf_from_env",
                },
                clear=True,
            ):
                self.assertEqual(huggingface_token(), "hf_from_env")

    def test_diarize_audio_file_passes_preloaded_waveform_to_pipeline(self):
        class FakePipeline:
            def __init__(self):
                self.audio_input = None
                self.kwargs = None

            def __call__(self, audio_input, **kwargs):
                self.audio_input = audio_input
                self.kwargs = kwargs
                return [(type("Turn", (), {"start": 1.0, "end": 2.0})(), "SPEAKER_00")]

        fake_pipeline = FakePipeline()
        fake_audio_input = {"waveform": object(), "sample_rate": 16000}

        with (
            patch("aura.diarization.pyannote_pipeline._load_pyannote_pipeline", return_value=fake_pipeline),
            patch("aura.diarization.pyannote_pipeline.pipeline_audio_input", return_value=fake_audio_input),
        ):
            turns = diarize_audio_file(
                "meeting.wav",
                DiarizationSettings(enabled=True, min_speakers=2, max_speakers=2, device="cuda"),
            )

        self.assertIs(fake_pipeline.audio_input, fake_audio_input)
        self.assertEqual(fake_pipeline.kwargs, {"num_speakers": 2})
        self.assertEqual(turns, [SpeakerTurn(start=1.0, end=2.0, speaker="SPEAKER_00")])


if __name__ == "__main__":
    unittest.main()
