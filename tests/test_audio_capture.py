import json
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from aura.audio.capture import (
    AudioRecorderThread,
    ENERGY_BRIDGE_MS,
    MIX_MAX_GAIN,
    MIX_MIN_GAIN,
    NO_VOICE_AUTO_STOP_MINUTES,
    frames_for_duration_seconds,
    frame_rms,
    gain_for_rms,
    mix_audio_frames,
    parse_pactl_sources,
    select_microphone_pulse_source,
    select_pulse_sources_for_mode,
    select_system_pulse_source,
    should_auto_stop_for_no_voice,
    should_treat_frame_as_speech,
    track_audio_frames,
    trim_trailing_unvoiced_frames,
)
from aura.audio.meeting_distance import MEETING_DISTANCE_FAR_SPEAKER
from aura.config import CHUNK_MS, LIVE_CAPTURE_MICROPHONE, LIVE_CAPTURE_SYSTEM, LIVE_CAPTURE_SYSTEM_MICROPHONE


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

    def test_system_and_microphone_frames_remain_separate_before_mixing(self):
        sources = parse_pactl_sources(PACTL_SOURCES)[:2]
        system = np.array([1_000, -1_000], dtype=np.int16)
        microphone = np.array([1_000, -1_000], dtype=np.int16)

        tracks = track_audio_frames(
            LIVE_CAPTURE_SYSTEM_MICROPHONE,
            sources,
            [system, microphone],
        )

        self.assertEqual(set(tracks), {"mixed", "system", "microphone"})
        np.testing.assert_array_equal(tracks["system"], system)
        np.testing.assert_array_equal(tracks["microphone"], microphone)
        np.testing.assert_array_equal(tracks["mixed"], np.array([800, -800], dtype=np.int16))

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

    def test_frames_for_duration_seconds_rounds_up_to_capture_chunks(self):
        self.assertEqual(frames_for_duration_seconds(CHUNK_MS / 1000), 1)
        self.assertEqual(
            frames_for_duration_seconds(NO_VOICE_AUTO_STOP_MINUTES * 60),
            int(np.ceil(NO_VOICE_AUTO_STOP_MINUTES * 60 * 1000 / CHUNK_MS)),
        )

    def test_should_auto_stop_for_no_voice_only_after_limit(self):
        self.assertFalse(should_auto_stop_for_no_voice(9, 10))
        self.assertTrue(should_auto_stop_for_no_voice(10, 10))
        self.assertFalse(should_auto_stop_for_no_voice(10, 0))

    def test_energy_gate_does_not_start_speech_without_vad(self):
        self.assertFalse(
            should_treat_frame_as_speech(
                vad_is_speech=False,
                frame_rms_value=5000.0,
                has_active_segment=False,
                consecutive_vad_miss_frames=1,
                energy_gate_rms=1000.0,
                max_energy_bridge_frames=frames_for_duration_seconds(ENERGY_BRIDGE_MS / 1000),
            )
        )

    def test_energy_gate_bridges_short_vad_miss_inside_active_segment(self):
        self.assertTrue(
            should_treat_frame_as_speech(
                vad_is_speech=False,
                frame_rms_value=5000.0,
                has_active_segment=True,
                consecutive_vad_miss_frames=1,
                energy_gate_rms=1000.0,
                max_energy_bridge_frames=frames_for_duration_seconds(ENERGY_BRIDGE_MS / 1000),
            )
        )

    def test_energy_gate_stops_bridging_after_short_vad_miss_window(self):
        max_bridge_frames = frames_for_duration_seconds(ENERGY_BRIDGE_MS / 1000)

        self.assertFalse(
            should_treat_frame_as_speech(
                vad_is_speech=False,
                frame_rms_value=5000.0,
                has_active_segment=True,
                consecutive_vad_miss_frames=max_bridge_frames + 1,
                energy_gate_rms=1000.0,
                max_energy_bridge_frames=max_bridge_frames,
            )
        )

    def test_trim_trailing_unvoiced_frames_removes_only_tail(self):
        frames = [b"voice-1", b"quiet-1", b"voice-2", b"quiet-2", b"quiet-3"]
        trimmed, count = trim_trailing_unvoiced_frames(frames, [True, False, True, False, False])

        self.assertEqual(trimmed, [b"voice-1", b"quiet-1", b"voice-2"])
        self.assertEqual(count, 2)

    def test_trim_trailing_unvoiced_frames_drops_all_when_no_voice_exists(self):
        trimmed, count = trim_trailing_unvoiced_frames([b"quiet-1", b"quiet-2"], [False, False])

        self.assertEqual(trimmed, [])
        self.assertEqual(count, 2)

    def test_trim_trailing_unvoiced_frames_requires_matching_lengths(self):
        with self.assertRaises(ValueError):
            trim_trailing_unvoiced_frames([b"frame"], [])

    def test_recorder_uses_live_segment_and_energy_gate_defaults(self):
        recorder = AudioRecorderThread("recording", transcriber_thread=object())

        self.assertEqual(recorder.max_segment_len_sec, 16.0)
        self.assertEqual(recorder.energy_gate_rms, 1000.0)

    def test_recorder_allows_live_segment_and_energy_gate_overrides(self):
        recorder = AudioRecorderThread(
            "recording",
            transcriber_thread=object(),
            max_segment_len_sec=12.5,
            energy_gate_rms=1200.0,
        )

        self.assertEqual(recorder.max_segment_len_sec, 12.5)
        self.assertEqual(recorder.energy_gate_rms, 1200.0)

    def test_far_speaker_mode_overrides_live_gate_bridge_and_denoise(self):
        recorder = AudioRecorderThread(
            "recording",
            transcriber_thread=object(),
            denoise_preset="off",
            meeting_distance_mode=MEETING_DISTANCE_FAR_SPEAKER,
            energy_gate_rms=1200.0,
        )

        self.assertEqual(recorder.energy_gate_rms, 650.0)
        self.assertEqual(recorder.energy_bridge_ms, 240)
        self.assertEqual(recorder.denoise_preset, "medium")

    def test_recorder_journals_and_finalizes_all_live_capture_tracks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AudioRecorderThread(
                str(Path(tmpdir) / "meeting" / "meeting"),
                transcriber_thread=type("Transcriber", (), {"add_audio": lambda _self, _audio: None})(),
                capture_mode=LIVE_CAPTURE_SYSTEM_MICROPHONE,
            )

            class Reader:
                sample_width = 2
                description = "test reader"

                def read_tracks(self):
                    recorder.running = False
                    system = np.full(480, 1_000, dtype=np.int16)
                    microphone = np.full(480, 2_000, dtype=np.int16)
                    return {
                        "mixed": np.full(480, 1_200, dtype=np.int16),
                        "system": system,
                        "microphone": microphone,
                    }

                def close(self):
                    pass

            recorder._open_reader = lambda: Reader()
            finished = []
            statuses = []
            recorder.finished_signal.connect(finished.append)
            recorder.status_signal.connect(statuses.append)

            recorder.run()

            session_dir = Path(tmpdir) / "meeting" / "meeting_session"
            manifest_path = session_dir / "session.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "ready")
            self.assertEqual(set(manifest["audio_tracks"]), {"mixed", "system", "microphone"})
            self.assertEqual(finished, [str(session_dir / "meeting.wav")])
            self.assertTrue(
                any("持續保存" in status for status in statuses),
                statuses,
            )

    def test_midstream_capture_error_preserves_partial_wav_and_failed_provenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AudioRecorderThread(
                str(Path(tmpdir) / "meeting" / "meeting"),
                transcriber_thread=type("Transcriber", (), {"add_audio": lambda _self, _audio: None})(),
            )

            class Reader:
                sample_width = 2
                description = "test reader"
                reads = 0

                def read_tracks(self):
                    self.reads += 1
                    if self.reads > 1:
                        raise RuntimeError("device disconnected")
                    return {"mixed": np.full(480, 1_200, dtype=np.int16)}

                def close(self):
                    pass

            recorder._open_reader = lambda: Reader()
            finished = []
            statuses = []
            recorder.finished_signal.connect(finished.append)
            recorder.status_signal.connect(statuses.append)

            recorder.run()

            session_dir = Path(tmpdir) / "meeting" / "meeting_session"
            manifest = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
            partial_wav = session_dir / "meeting_partial.wav"
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["recording_outcome"], "partial")
            self.assertEqual(manifest["failure"]["phase"], "capture")
            self.assertIn("device disconnected", manifest["failure"]["message"])
            self.assertTrue(partial_wav.is_file())
            with wave.open(str(partial_wav), "rb") as recording:
                self.assertEqual(recording.getnframes(), 480)
            self.assertEqual(finished, [str(partial_wav)])
            self.assertTrue(any("Partial recording preserved" in status for status in statuses))


if __name__ == "__main__":
    unittest.main()
