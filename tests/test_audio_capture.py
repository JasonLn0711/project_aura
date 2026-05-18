import unittest

import numpy as np

from aura.audio.capture import (
    MIX_MAX_GAIN,
    MIX_MIN_GAIN,
    frame_rms,
    gain_for_rms,
    mix_audio_frames,
    parse_pactl_sources,
    select_microphone_pulse_source,
    select_pulse_sources_for_mode,
    select_system_pulse_source,
)
from aura.config import LIVE_CAPTURE_MICROPHONE, LIVE_CAPTURE_SYSTEM, LIVE_CAPTURE_SYSTEM_MICROPHONE


PACTL_SOURCES = """\
50\talsa_output.usb-Speaker.analog-stereo.monitor\tPipeWire\ts16le 2ch 48000Hz\tRUNNING
51\talsa_input.usb-Headset.analog-stereo\tPipeWire\ts16le 2ch 48000Hz\tRUNNING
52\talsa_output.hdmi-stereo.monitor\tPipeWire\ts32le 2ch 48000Hz\tIDLE
"""


class AudioCaptureTests(unittest.TestCase):
    def test_parse_pactl_sources(self):
        sources = parse_pactl_sources(PACTL_SOURCES)

        self.assertEqual(len(sources), 3)
        self.assertEqual(sources[0].name, "alsa_output.usb-Speaker.analog-stereo.monitor")
        self.assertEqual(sources[1].state, "RUNNING")

    def test_select_system_source_prefers_default_sink_monitor(self):
        sources = parse_pactl_sources(PACTL_SOURCES)

        selected = select_system_pulse_source(sources, default_sink="alsa_output.hdmi-stereo")

        self.assertEqual(selected.name, "alsa_output.hdmi-stereo.monitor")

    def test_select_microphone_source_prefers_default_source(self):
        sources = parse_pactl_sources(PACTL_SOURCES)

        selected = select_microphone_pulse_source(sources, default_source="alsa_input.usb-Headset.analog-stereo")

        self.assertEqual(selected.name, "alsa_input.usb-Headset.analog-stereo")

    def test_select_mix_returns_system_and_microphone(self):
        sources = parse_pactl_sources(PACTL_SOURCES)

        selected = select_pulse_sources_for_mode(
            LIVE_CAPTURE_SYSTEM_MICROPHONE,
            sources,
            default_source="alsa_input.usb-Headset.analog-stereo",
            default_sink="alsa_output.usb-Speaker.analog-stereo",
        )

        self.assertEqual(
            [source.name for source in selected],
            [
                "alsa_output.usb-Speaker.analog-stereo.monitor",
                "alsa_input.usb-Headset.analog-stereo",
            ],
        )

    def test_select_single_source_modes(self):
        sources = parse_pactl_sources(PACTL_SOURCES)

        system = select_pulse_sources_for_mode(LIVE_CAPTURE_SYSTEM, sources)
        microphone = select_pulse_sources_for_mode(LIVE_CAPTURE_MICROPHONE, sources)

        self.assertEqual(len(system), 1)
        self.assertTrue(system[0].name.endswith(".monitor"))
        self.assertEqual(len(microphone), 1)
        self.assertFalse(microphone[0].name.endswith(".monitor"))

    def test_frame_rms_and_gain_limits(self):
        self.assertAlmostEqual(frame_rms(np.array([3, 4], dtype=np.int16)), 3.5355, places=3)
        self.assertEqual(gain_for_rms(100.0, 1_000.0), MIX_MAX_GAIN)
        self.assertEqual(gain_for_rms(1_000.0, 100.0), MIX_MIN_GAIN)
        self.assertEqual(gain_for_rms(10.0, 1_000.0), 1.0)

    def test_mix_audio_frames_ignores_silent_source(self):
        speech = np.array([1_000, -1_000] * 240, dtype=np.int16)
        silence = np.zeros_like(speech)

        mixed = mix_audio_frames([speech, silence])

        np.testing.assert_array_equal(mixed, speech)

    def test_mix_audio_frames_balances_loud_and_quiet_sources_with_headroom(self):
        loud = np.array([12_000, -12_000] * 240, dtype=np.int16)
        quiet = np.array([1_200, -1_200] * 240, dtype=np.int16)

        mixed = mix_audio_frames([loud, quiet])
        peak = int(np.abs(mixed).max())

        self.assertGreater(peak, int(np.abs(quiet).max()))
        self.assertLess(peak, int(np.abs(loud).max()))
        self.assertLess(peak, 32767)


if __name__ == "__main__":
    unittest.main()
