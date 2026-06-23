import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.discover_denoise_eval_candidates import (
    best_transcript_for_audio,
    discover_candidates,
    render_markdown,
    shell_quote,
    suggest_category,
)


class DiscoverDenoiseEvalCandidatesTests(unittest.TestCase):
    def test_shell_quote_handles_spaces_and_quotes(self):
        self.assertEqual(shell_quote("/tmp/has space/it's.wav"), "'/tmp/has space/it'\"'\"'s.wav'")

    def test_best_transcript_prefers_same_stem_txt_over_longer_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            case_dir = Path(tmpdir)
            audio = case_dir / "meeting.wav"
            audio.write_bytes(b"audio")
            (case_dir / "meeting.txt").write_text("short trusted transcript", encoding="utf-8")
            (case_dir / "notes.md").write_text("long notes " * 100, encoding="utf-8")

            transcript, chars = best_transcript_for_audio(audio)

        self.assertEqual(transcript.name, "meeting.txt")
        self.assertEqual(chars, len("short trusted transcript"))

    def test_suggest_category_uses_path_hints(self):
        self.assertEqual(suggest_category(Path("/tmp/lab_sync/audio.mp3")), "lecture_or_meeting")
        self.assertEqual(suggest_category(Path("/tmp/seminar_speech/audio.mp3")), "far_speaker_reverb")
        self.assertEqual(suggest_category(Path("/tmp/chat/audio.mp3")), "far_speaker_overlap")

    def test_discover_candidates_builds_private_manifest_data_without_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "recordings"
            root.mkdir()
            audio = root / "far_meeting.mp3"
            audio.write_bytes(b"audio")
            transcript = root / "far_meeting.txt"
            transcript.write_text("trusted transcript content should not appear", encoding="utf-8")

            with patch("scripts.discover_denoise_eval_candidates.probe_duration_seconds", return_value=125.0):
                candidates = discover_candidates(
                    root=root,
                    eval_dir=Path("~/record_jn/aura_eval_audio").expanduser(),
                    min_duration=30.0,
                    clip_duration=60.0,
                    min_transcript_chars=10,
                    limit=10,
                    per_folder_limit=2,
                )
            markdown = render_markdown(candidates, root)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].transcript_path, str(transcript))
        self.assertEqual(candidates[0].transcript_chars, len("trusted transcript content should not appear"))
        self.assertNotIn("--reference-file", candidates[0].prepare_command)
        self.assertIn("--note", candidates[0].prepare_command)
        self.assertNotIn("trusted transcript content", markdown)
        self.assertIn("not as `--reference-file`", markdown)
        self.assertIn("Transcript contents are intentionally not included", markdown)

    def test_discover_candidates_can_opt_into_reference_file_for_clip_level_references(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "recordings"
            root.mkdir()
            audio = root / "clip.wav"
            audio.write_bytes(b"audio")
            transcript = root / "clip.txt"
            transcript.write_text("clip-level trusted reference", encoding="utf-8")

            with patch("scripts.discover_denoise_eval_candidates.probe_duration_seconds", return_value=60.0):
                candidates = discover_candidates(
                    root=root,
                    eval_dir=Path("~/record_jn/aura_eval_audio").expanduser(),
                    min_duration=30.0,
                    clip_duration=60.0,
                    min_transcript_chars=10,
                    limit=10,
                    per_folder_limit=2,
                    include_transcript_reference=True,
                )

        self.assertIn("--reference-file", candidates[0].prepare_command)


if __name__ == "__main__":
    unittest.main()
