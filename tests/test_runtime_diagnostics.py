import unittest
from unittest.mock import patch

from aura.asr.threads import cuda_required_error
from aura.system.audio_diagnostics import AudioDiagnostics
from aura.system.gpu_diagnostics import CommandCheck, GpuDiagnostics, collect_gpu_diagnostics
from aura.system.platform import LINUX_NATIVE, RuntimePlatform, platform_cuda_guidance
from aura.system.runtime_report import RuntimeDiagnostics, format_runtime_report


class RuntimeDiagnosticsTests(unittest.TestCase):
    def test_cuda_required_error_uses_product_activation_language(self):
        message = cuda_required_error("missing cublas")

        self.assertIn("has not completed Project AURA RTX/CUDA activation", message)
        self.assertIn("CPU fallback is disabled", message)
        self.assertIn("Next check:", message)

    def test_collect_gpu_diagnostics_respects_preloaded_runtime_status(self):
        with (
            patch("aura.system.gpu_diagnostics.preload_cuda_runtime_libraries", return_value=(True, "bundled")),
            patch(
                "aura.system.gpu_diagnostics.collect_cuda_library_status",
                return_value=(("CUDA runtime", False, "not found"),),
            ),
            patch(
                "aura.system.gpu_diagnostics.run_nvidia_smi",
                return_value=CommandCheck("nvidia-smi", True, 0, "RTX, 1.0, 16 GiB", ""),
            ),
            patch("aura.system.gpu_diagnostics._module_importable", return_value=True),
            patch("aura.system.gpu_diagnostics._version", return_value="1.0"),
        ):
            diagnostics = collect_gpu_diagnostics()

        self.assertTrue(diagnostics.cuda_ready)
        self.assertEqual(diagnostics.cuda_libraries[0], ("CUDA runtime", True, "bundled"))

    def test_runtime_report_contains_developer_ready_sections(self):
        platform = RuntimePlatform(
            kind=LINUX_NATIVE,
            system="Linux",
            release="test",
            machine="x86_64",
            python_version="3.12",
            is_windows=False,
            is_wsl=False,
            is_docker=False,
        )
        gpu = GpuDiagnostics(
            nvidia_smi=CommandCheck("nvidia-smi", True, 0, "RTX, 1.0, 16 GiB", ""),
            faster_whisper_importable=True,
            faster_whisper_version="1.2.1",
            ctranslate2_importable=True,
            ctranslate2_version="4.7.1",
            cuda_runtime_ready=True,
            cuda_runtime_detail="bundled",
            cuda_libraries=(("CUDA runtime", True, "bundled"),),
            activation_guidance=platform_cuda_guidance(platform),
        )
        audio = AudioDiagnostics(
            ffmpeg_path="/usr/bin/ffmpeg",
            pyaudio_available=True,
            input_devices=("mic",),
            output_devices=("speaker",),
        )

        report = format_runtime_report(
            RuntimeDiagnostics(platform=platform, gpu=gpu, audio=audio, asr_model_status="loaded on cuda/int8")
        )

        self.assertIn("Project AURA Runtime Diagnostic Report", report)
        self.assertIn("GPU / CUDA", report)
        self.assertIn("Audio / FFmpeg", report)
        self.assertIn("ASR model load status: loaded on cuda/int8", report)
        self.assertIn(platform_cuda_guidance(platform), report)


if __name__ == "__main__":
    unittest.main()
