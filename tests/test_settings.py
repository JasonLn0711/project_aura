import unittest

from aura.config import (
    CHINESE_PUNCTUATION_MODEL_ID,
    COMPUTE_TYPE,
    DEFAULT_LIVE_PROMPT,
    DEFAULT_PROMPT,
    DEVICE,
    DIARIZATION_MODEL_ID,
    MODEL_ID,
    SUMMARY_MODEL_ID,
    SUPPORTED_IMPORT_EXTENSIONS,
)
from aura.settings import DEFAULT_SETTINGS, AppSettings
from aura.ui.messages import UIStrings


class SettingsTests(unittest.TestCase):
    def test_default_settings_preserve_runtime_constants(self):
        self.assertEqual(DEFAULT_SETTINGS.model_id, MODEL_ID)
        self.assertEqual(DEFAULT_SETTINGS.device, DEVICE)
        self.assertEqual(DEFAULT_SETTINGS.compute_type, COMPUTE_TYPE)
        self.assertEqual(DEFAULT_SETTINGS.device, "cuda")
        self.assertEqual(DEFAULT_SETTINGS.compute_type, "int8")
        self.assertEqual(DEFAULT_SETTINGS.file_initial_prompt, DEFAULT_PROMPT)
        self.assertEqual(DEFAULT_SETTINGS.live_initial_prompt, DEFAULT_LIVE_PROMPT)
        self.assertEqual(DEFAULT_SETTINGS.denoise_preset, "off")
        self.assertFalse(DEFAULT_SETTINGS.speaker_diarization_enabled)
        self.assertEqual(DEFAULT_SETTINGS.speaker_min_speakers, 2)
        self.assertEqual(DEFAULT_SETTINGS.speaker_max_speakers, 6)
        self.assertEqual(DEFAULT_SETTINGS.speaker_diarization_model, DIARIZATION_MODEL_ID)
        self.assertFalse(DEFAULT_SETTINGS.llm_summary_enabled)
        self.assertEqual(DEFAULT_SETTINGS.llm_summary_model, SUMMARY_MODEL_ID)
        self.assertIn("gemma-4-E4B-it-fp8", DEFAULT_SETTINGS.llm_summary_model)
        self.assertEqual(DEFAULT_SETTINGS.llm_summary_quantization, "nvfp8")
        self.assertTrue(DEFAULT_SETTINGS.chinese_punctuation_enabled)
        self.assertEqual(DEFAULT_SETTINGS.chinese_punctuation_model, CHINESE_PUNCTUATION_MODEL_ID)

    def test_custom_settings_can_override_runtime_defaults(self):
        settings = AppSettings(device="cpu", compute_type="int8", language=None, target_dbfs=-18.0)

        self.assertEqual(settings.device, "cpu")
        self.assertEqual(settings.compute_type, "int8")
        self.assertIsNone(settings.language)
        self.assertEqual(settings.target_dbfs, -18.0)

    def test_ui_strings_format_dynamic_status_messages(self):
        strings = UIStrings()

        self.assertEqual(strings.model_ready("cpu", "int8"), "✅ Model is ready (cpu/int8)")
        self.assertIn("v1.5.0", strings.update_found("1.5.0"))
        self.assertEqual(
            strings.splitter_status("meeting.wav", "/tmp/out"),
            "Source: meeting.wav | Output to: /tmp/out",
        )

    def test_import_media_filter_lists_common_audio_video_types_and_fallback(self):
        strings = UIStrings()

        for extension in SUPPORTED_IMPORT_EXTENSIONS:
            self.assertIn(f"*.{extension}", strings.media_files_filter)
        for required_extension in ("mp3", "mp4", "m4a", "wav"):
            self.assertIn(required_extension, SUPPORTED_IMPORT_EXTENSIONS)
        self.assertIn("All Files (*)", strings.media_files_filter)


if __name__ == "__main__":
    unittest.main()
