"""Transcript output stays incremental when diarization revises old labels."""
import unittest
from aura.cli import transcript_delta


class TranscriptDeltaTests(unittest.TestCase):
    def test_relabel_and_append(self):
        old = "[00:00:00] First.\n"
        new = "[00:00:00] SPEAKER_00: First.\n[00:00:02] Second.\n"
        self.assertEqual(transcript_delta(old, new), "[00:00:02] Second.\n")

    def test_relabel_only(self):
        self.assertEqual(transcript_delta(
            "[00:00:00] SPEAKER_00: First.\n",
            "[00:00:00] SPEAKER_01: First.\n"), "")

    def test_actual_correction(self):
        old = "[00:00:00] First.\n[00:00:02] Wrong.\n"
        new = "[00:00:00] First.\n[00:00:02] Correct.\n"
        self.assertEqual(transcript_delta(old, new), "[00:00:02] Correct.\n")

    def test_initial_and_unchanged(self):
        text = "[00:00:00] First.\n"
        self.assertEqual(transcript_delta("", text), text)
        self.assertEqual(transcript_delta(text, text), "")
