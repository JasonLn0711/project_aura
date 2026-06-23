import unittest

import numpy as np

from aura.audio.denoise import DEFAULT_ACTIVE_DENOISE_PRESET, OFF_DENOISE_PRESET
from aura.audio.meeting_distance import (
    MEETING_DISTANCE_FAR_SPEAKER,
    MEETING_DISTANCE_NORMAL,
    MEETING_DISTANCE_OFF,
    MEETING_DISTANCE_RESCUE_OFFLINE,
    apply_live_segment_agc,
    effective_denoise_preset_for_mode,
    meeting_distance_policy_for,
    normalize_meeting_distance_mode,
)


class MeetingDistancePolicyTests(unittest.TestCase):
    def test_normalize_meeting_distance_mode_rejects_unknown_mode(self):
        with self.assertRaisesRegex(ValueError, "Unknown meeting distance mode"):
            normalize_meeting_distance_mode("conference-hall")

    def test_off_mode_respects_selected_denoise_preset(self):
        self.assertEqual(
            effective_denoise_preset_for_mode(MEETING_DISTANCE_OFF, DEFAULT_ACTIVE_DENOISE_PRESET),
            DEFAULT_ACTIVE_DENOISE_PRESET,
        )

    def test_normal_mode_requires_at_least_light_denoise(self):
        self.assertEqual(
            effective_denoise_preset_for_mode(MEETING_DISTANCE_NORMAL, OFF_DENOISE_PRESET),
            DEFAULT_ACTIVE_DENOISE_PRESET,
        )

    def test_far_speaker_requires_medium_denoise(self):
        self.assertEqual(
            effective_denoise_preset_for_mode(MEETING_DISTANCE_FAR_SPEAKER, DEFAULT_ACTIVE_DENOISE_PRESET),
            "medium",
        )

    def test_rescue_offline_is_import_supported_but_not_live_backend_supported(self):
        policy = meeting_distance_policy_for(MEETING_DISTANCE_RESCUE_OFFLINE)

        self.assertTrue(policy.import_supported)
        self.assertFalse(policy.live_supported)
        self.assertEqual(policy.enhancement_backend, "clearvoice-mossformer-candidate")

    def test_live_segment_agc_boosts_quiet_far_speaker_segment_with_limit(self):
        policy = meeting_distance_policy_for(MEETING_DISTANCE_FAR_SPEAKER)
        audio = np.full(1600, 0.01, dtype=np.float32)

        boosted = apply_live_segment_agc(audio, policy)

        self.assertGreater(float(np.sqrt(np.mean(boosted * boosted))), 0.01)
        self.assertLessEqual(float(np.max(np.abs(boosted))), 0.95)

    def test_live_segment_agc_preserves_off_mode_audio_object(self):
        policy = meeting_distance_policy_for(MEETING_DISTANCE_OFF)
        audio = np.full(1600, 0.01, dtype=np.float32)

        boosted = apply_live_segment_agc(audio, policy)

        self.assertIs(boosted, audio)


if __name__ == "__main__":
    unittest.main()
