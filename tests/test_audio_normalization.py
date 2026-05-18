import math
import unittest
from unittest.mock import patch

from aura.audio.normalization import (
    CpuDetectionResult,
    detect_cpu_count,
    ffmpeg_cpu_args,
    gain_for_target_dbfs,
    normalization_cpu_status,
    normalization_thread_count,
    parse_mean_volume,
)


class AudioNormalizationTests(unittest.TestCase):
    def test_parse_mean_volume_from_ffmpeg_output(self):
        output = "[Parsed_volumedetect_0 @ 0x1] mean_volume: -27.4 dB\n"

        self.assertEqual(parse_mean_volume(output), -27.4)

    def test_gain_for_target_dbfs(self):
        self.assertAlmostEqual(gain_for_target_dbfs(-32.5, -20.0), 12.5)

    def test_gain_for_silent_or_unknown_audio_is_noop(self):
        self.assertEqual(gain_for_target_dbfs(None, -20.0), 0.0)
        self.assertEqual(gain_for_target_dbfs(-math.inf, -20.0), 0.0)

    def test_normalization_thread_count_reserves_six_cpus(self):
        self.assertEqual(normalization_thread_count(cpu_count=16), 10)

    def test_normalization_thread_count_keeps_at_least_one_cpu(self):
        self.assertEqual(normalization_thread_count(cpu_count=4), 1)
        with patch("aura.audio.normalization.detect_cpu_count", return_value=CpuDetectionResult(None, "unavailable")):
            self.assertEqual(normalization_thread_count(), 1)

    def test_ffmpeg_cpu_args_use_normalization_budget(self):
        with patch("aura.audio.normalization.detect_cpu_count", return_value=CpuDetectionResult(12, "test")):
            self.assertEqual(ffmpeg_cpu_args(), ["-threads", "6", "-filter_threads", "6"])

    def test_detect_cpu_count_falls_back_to_affinity(self):
        with (
            patch("aura.audio.normalization.os.cpu_count", return_value=None),
            patch("aura.audio.normalization.os.sched_getaffinity", return_value={0, 1, 2, 3}),
        ):
            result = detect_cpu_count()

        self.assertEqual(result, CpuDetectionResult(4, "os.sched_getaffinity"))

    def test_detect_cpu_count_falls_back_to_nproc(self):
        fake_result = type("Result", (), {"returncode": 0, "stdout": "8\n"})()
        with (
            patch("aura.audio.normalization.os.cpu_count", return_value=None),
            patch("aura.audio.normalization.os.sched_getaffinity", side_effect=OSError),
            patch("aura.audio.normalization.shutil.which", return_value="/usr/bin/nproc"),
            patch("aura.audio.normalization.subprocess.run", return_value=fake_result),
            patch("aura.audio.normalization.Path.exists", return_value=False),
        ):
            result = detect_cpu_count()

        self.assertEqual(result, CpuDetectionResult(8, "nproc"))

    def test_normalization_cpu_status_reports_unavailable_count(self):
        with patch("aura.audio.normalization.detect_cpu_count", return_value=CpuDetectionResult(None, "unavailable")):
            self.assertEqual(normalization_cpu_status(), "CPU count unavailable; using 1 FFmpeg normalization thread.")


if __name__ == "__main__":
    unittest.main()
