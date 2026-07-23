import unittest
from unittest.mock import patch

import numpy as np

from aura.asr.file_pipeline import build_transcribe_kwargs, resolve_initial_prompt
from aura.asr.threads import (
    FileTranscriberThread,
    TranscriberThread,
    live_asr_telemetry_event,
    live_asr_telemetry_message,
)
from aura.audio.denoise import DEFAULT_ACTIVE_DENOISE_PRESET, OFF_DENOISE_PRESET
from aura.config import DEFAULT_LIVE_PROMPT, DEFAULT_PROMPT


class PromptDefaultTests(unittest.TestCase):
    def test_file_thread_uses_default_prompt_when_not_supplied(self):
        thread = FileTranscriberThread(model=object(), file_path="input.wav")

        self.assertEqual(thread.initial_prompt, DEFAULT_PROMPT)
        self.assertFalse(thread.enable_denoise)
        self.assertEqual(thread.settings.denoise_preset, OFF_DENOISE_PRESET)

    def test_file_thread_maps_legacy_denoise_flag_to_light_preset(self):
        thread = FileTranscriberThread(model=object(), file_path="input.wav", enable_denoise=True)

        self.assertTrue(thread.enable_denoise)
        self.assertEqual(thread.settings.denoise_preset, DEFAULT_ACTIVE_DENOISE_PRESET)

    def test_file_thread_captures_import_advanced_settings(self):
        thread = FileTranscriberThread(
            model=object(),
            file_path="input.mp4",
            target_dbfs=-18.0,
            beam_size=9,
            initial_prompt="domain words",
            language=None,
            enable_denoise=True,
            denoise_preset="medium",
            enable_speaker_diarization=True,
            min_speakers=3,
            max_speakers=5,
        )

        self.assertEqual(thread.settings.target_dbfs, -18.0)
        self.assertEqual(thread.settings.beam_size, 9)
        self.assertEqual(thread.settings.initial_prompt, "domain words")
        self.assertIsNone(thread.settings.language)
        self.assertTrue(thread.enable_denoise)
        self.assertEqual(thread.settings.denoise_preset, "medium")
        self.assertTrue(thread.settings.diarization.enabled)
        self.assertEqual(thread.settings.diarization.min_speakers, 3)
        self.assertEqual(thread.settings.diarization.max_speakers, 5)

    def test_live_thread_starts_with_live_default_prompt(self):
        thread = TranscriberThread()

        self.assertEqual(thread.live_initial_prompt, DEFAULT_LIVE_PROMPT)

    def test_live_update_without_prompt_keeps_live_default(self):
        thread = TranscriberThread()

        thread.update_live_settings()

        self.assertEqual(thread.live_initial_prompt, DEFAULT_LIVE_PROMPT)

    def test_live_asr_telemetry_reports_duration_speed_and_backlog(self):
        message = live_asr_telemetry_message(
            chunk_duration_seconds=16.48,
            queue_size=2,
            elapsed_seconds=8.24,
        )

        self.assertIn("chunk_duration=16.480s", message)
        self.assertIn("queue_size=2", message)
        self.assertIn("asr_elapsed=8.240s", message)
        self.assertIn("realtime_factor=0.50", message)
        self.assertIn("queue_backlog=yes", message)

    def test_live_asr_telemetry_event_keeps_structured_fields(self):
        event = live_asr_telemetry_event(
            chunk_duration_seconds=16.48,
            queue_size=0,
            elapsed_seconds=8.24,
        )

        self.assertEqual(event["category"], "live_asr_telemetry")
        self.assertEqual(event["chunk_duration_seconds"], 16.48)
        self.assertEqual(event["queue_size"], 0)
        self.assertEqual(event["asr_elapsed_seconds"], 8.24)
        self.assertEqual(event["realtime_factor"], 0.5)
        self.assertFalse(event["queue_backlog"])

    def test_live_transcript_timestamps_follow_stream_elapsed_time(self):
        thread = TranscriberThread()
        thread.live_chinese_punctuation_enabled = False
        emitted = []
        thread.text_updated.connect(emitted.append)

        class Model:
            calls = 0

            def transcribe(self, _audio, **_kwargs):
                self.calls += 1
                if self.calls == 2:
                    thread.running = False
                return [type("Segment", (), {"text": f" chunk-{self.calls}"})()], type(
                    "Info",
                    (),
                    {"language": "zh"},
                )()

        thread.model = Model()
        thread.add_audio(np.zeros(2 * 16_000, dtype=np.float32))
        thread.add_audio(np.zeros(3 * 16_000, dtype=np.float32))

        with patch("aura.asr.threads.append_transcript_backup"):
            thread.run()

        self.assertEqual(emitted, ["[00:00:00]  chunk-1", "[00:00:02]  chunk-2"])

    def test_explicit_empty_prompt_remains_empty(self):
        self.assertEqual(resolve_initial_prompt("", DEFAULT_PROMPT), "")

    def test_transcribe_kwargs_include_default_prompt(self):
        kwargs = build_transcribe_kwargs(
            beam_size=5,
            language="zh",
            initial_prompt=DEFAULT_PROMPT,
            condition_on_previous_text=True,
        )

        self.assertEqual(kwargs["initial_prompt"], DEFAULT_PROMPT)
        self.assertEqual(kwargs["language"], "zh")
        self.assertEqual(kwargs["beam_size"], 5)
        self.assertTrue(kwargs["condition_on_previous_text"])

    def test_transcribe_kwargs_omit_language_for_auto_detect(self):
        kwargs = build_transcribe_kwargs(
            beam_size=5,
            language=None,
            initial_prompt=DEFAULT_PROMPT,
            condition_on_previous_text=True,
        )

        self.assertNotIn("language", kwargs)
        self.assertEqual(kwargs["initial_prompt"], DEFAULT_PROMPT)


if __name__ == "__main__":
    unittest.main()
