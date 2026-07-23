import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from aura.asr.threads import cuda_required_error
from aura.llm.ollama_runtime import DEFAULT_OLLAMA_HOST
from aura.system.audio_diagnostics import AudioDiagnostics
from aura.system.gpu_diagnostics import CommandCheck, GpuDiagnostics, collect_gpu_diagnostics
from aura.system.platform import LINUX_NATIVE, RuntimePlatform, platform_cuda_guidance
from aura.system.runtime_report import (
    DiarizationDiagnostics,
    PunctuationDiagnostics,
    RuntimeDiagnostics,
    collect_ollama_diagnostics,
    collect_runtime_diagnostics,
    first_launch_checks,
    format_runtime_report,
)


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
        self.assertIn("Traditional Chinese Punctuation", report)
        self.assertIn("Optional Speaker Diarization", report)
        self.assertIn("ASR model load status: loaded on cuda/int8", report)
        self.assertIn("First Launch Check", report)
        self.assertIn("- CUDA runtime preload: complete", report)
        self.assertNotIn("- Activation guidance:", report)

    def test_runtime_report_surfaces_diarization_setup_status(self):
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
            RuntimeDiagnostics(
                platform=platform,
                gpu=gpu,
                audio=audio,
                diarization=DiarizationDiagnostics(
                    pyannote_available=False,
                    torch_available=False,
                    torch_cuda_available=False,
                    token_available=False,
                ),
                asr_model_status="loaded on cuda/int8",
            )
        )

        self.assertIn("- pyannote.audio import: missing", report)
        self.assertIn("- torch import: missing", report)
        self.assertIn("- Hugging Face token: missing", report)
        self.assertIn("Diarization status: needs setup: pyannote.audio, torch", report)

    def test_runtime_report_surfaces_punctuation_setup_status(self):
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
        report = format_runtime_report(
            RuntimeDiagnostics(
                platform=platform,
                gpu=GpuDiagnostics(
                    nvidia_smi=CommandCheck("nvidia-smi", False, 1, "", "not found"),
                    faster_whisper_importable=False,
                    faster_whisper_version="",
                    ctranslate2_importable=False,
                    ctranslate2_version="",
                    cuda_runtime_ready=False,
                    cuda_runtime_detail="not ready",
                    cuda_libraries=(),
                    activation_guidance="Complete GPU setup.",
                ),
                audio=AudioDiagnostics(
                    ffmpeg_path="",
                    pyaudio_available=False,
                    input_devices=(),
                    output_devices=(),
                ),
                punctuation=PunctuationDiagnostics(torch_available=True, transformers_available=False),
            )
        )

        self.assertIn("- transformers import: missing", report)
        self.assertIn("rule fallback ready; missing transformers", report)
        self.assertIn("make setup-app", report)

    def test_runtime_report_keeps_activation_guidance_when_cuda_incomplete(self):
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
            cuda_runtime_ready=False,
            cuda_runtime_detail="missing cudnn",
            cuda_libraries=(("cuDNN", False, "not found"),),
            activation_guidance=platform_cuda_guidance(platform),
        )
        audio = AudioDiagnostics(
            ffmpeg_path="/usr/bin/ffmpeg",
            pyaudio_available=True,
            input_devices=("mic",),
            output_devices=("speaker",),
        )

        report = format_runtime_report(
            RuntimeDiagnostics(platform=platform, gpu=gpu, audio=audio, asr_model_status="not loaded")
        )

        self.assertIn(f"- Activation guidance: {platform_cuda_guidance(platform)}", report)

    def test_first_launch_checks_cover_user_onboarding_gates(self):
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
        diagnostics = RuntimeDiagnostics(
            platform=platform,
            gpu=GpuDiagnostics(
                nvidia_smi=CommandCheck("nvidia-smi", True, 0, "RTX", ""),
                faster_whisper_importable=True,
                faster_whisper_version="1.2.1",
                ctranslate2_importable=True,
                ctranslate2_version="4.7.1",
                cuda_runtime_ready=True,
                cuda_runtime_detail="ready",
                cuda_libraries=(("CUDA runtime", True, "ready"),),
                activation_guidance=platform_cuda_guidance(platform),
            ),
            audio=AudioDiagnostics(
                ffmpeg_path="/usr/bin/ffmpeg",
                pyaudio_available=True,
                input_devices=("mic",),
                output_devices=("speaker",),
            ),
            asr_model_status="loaded (cuda/int8)",
            output_folder_writable=True,
            output_folder_free_bytes=2 << 30,
        )

        checks = {check.key: check for check in first_launch_checks(diagnostics)}

        self.assertEqual(
            set(checks),
            {"gpu", "cuda", "ffmpeg", "microphone", "output", "disk_space", "asr_model"},
        )
        self.assertTrue(all(check.ready for check in checks.values()))

    def test_collect_runtime_diagnostics_checks_selected_output_folder_and_free_space(self):
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
            nvidia_smi=CommandCheck("nvidia-smi", True, 0, "RTX", ""),
            faster_whisper_importable=True,
            faster_whisper_version="1.2.1",
            ctranslate2_importable=True,
            ctranslate2_version="4.7.1",
            cuda_runtime_ready=True,
            cuda_runtime_detail="ready",
            cuda_libraries=(),
            activation_guidance="ready",
        )
        audio = AudioDiagnostics(
            ffmpeg_path="/usr/bin/ffmpeg",
            pyaudio_available=True,
            input_devices=("mic",),
            output_devices=("speaker",),
        )
        with TemporaryDirectory() as tmpdir:
            output_folder = Path(tmpdir) / "new-session-output"
            with (
                patch("aura.system.runtime_report.detect_runtime_platform", return_value=platform),
                patch("aura.system.runtime_report.collect_gpu_diagnostics", return_value=gpu),
                patch("aura.system.runtime_report.collect_audio_diagnostics", return_value=audio),
                patch(
                    "aura.system.runtime_report.shutil.disk_usage",
                    return_value=SimpleNamespace(total=8_192, used=4_096, free=4_096),
                ),
            ):
                diagnostics = collect_runtime_diagnostics(
                    output_folder=output_folder,
                    minimum_free_bytes=2_048,
                    ollama_host=None,
                    ollama_model_tag=None,
                )

        self.assertEqual(diagnostics.output_folder, str(output_folder.resolve()))
        self.assertTrue(diagnostics.output_folder_writable)
        self.assertEqual(diagnostics.output_folder_free_bytes, 4_096)
        self.assertTrue(diagnostics.output_folder_space_ready)
        checks = {check.key: check for check in first_launch_checks(diagnostics)}
        self.assertTrue(checks["output"].ready)
        self.assertTrue(checks["disk_space"].ready)

    def test_collect_runtime_diagnostics_checks_configured_ollama_endpoint_and_model_tag(self):
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
            nvidia_smi=CommandCheck("nvidia-smi", True, 0, "RTX", ""),
            faster_whisper_importable=True,
            faster_whisper_version="1.2.1",
            ctranslate2_importable=True,
            ctranslate2_version="4.7.1",
            cuda_runtime_ready=True,
            cuda_runtime_detail="ready",
            cuda_libraries=(),
            activation_guidance="ready",
        )
        audio = AudioDiagnostics(
            ffmpeg_path="/usr/bin/ffmpeg",
            pyaudio_available=True,
            input_devices=("mic",),
            output_devices=("speaker",),
        )
        model_tag = "gemma4:e4b-it-qat"
        with TemporaryDirectory() as tmpdir:
            with (
                patch("aura.system.runtime_report.detect_runtime_platform", return_value=platform),
                patch("aura.system.runtime_report.collect_gpu_diagnostics", return_value=gpu),
                patch("aura.system.runtime_report.collect_audio_diagnostics", return_value=audio),
                patch("aura.system.runtime_report.check_ollama_command", return_value=True),
                patch(
                    "aura.system.runtime_report.ollama_tags",
                    return_value={"models": [{"name": model_tag}]},
                ),
            ):
                diagnostics = collect_runtime_diagnostics(
                    output_folder=tmpdir,
                    minimum_free_bytes=1,
                    ollama_host=DEFAULT_OLLAMA_HOST,
                    ollama_model_tag=model_tag,
                )

        self.assertTrue(diagnostics.ollama.configured)
        self.assertTrue(diagnostics.ollama.command_available)
        self.assertTrue(diagnostics.ollama.server_ready)
        self.assertTrue(diagnostics.ollama.model_available)
        checks = {check.key: check for check in first_launch_checks(diagnostics)}
        self.assertTrue(checks["ollama_command"].ready)
        self.assertTrue(checks["ollama_server"].ready)
        self.assertTrue(checks["ollama_model"].ready)

    def test_ollama_diagnostics_reject_remote_hosts_without_requesting_them(self):
        with (
            patch("aura.system.runtime_report.check_ollama_command", return_value=True),
            patch("aura.system.runtime_report.ollama_tags") as tags,
        ):
            diagnostics = collect_ollama_diagnostics(
                "https://api.example.com",
                "gemma4:e4b-it-qat",
            )

        tags.assert_not_called()
        self.assertFalse(diagnostics.server_ready)
        self.assertFalse(diagnostics.model_available)
        self.assertIn("localhost", diagnostics.detail)

    def test_ollama_diagnostics_keeps_invalid_local_response_as_not_ready(self):
        with (
            patch("aura.system.runtime_report.check_ollama_command", return_value=True),
            patch("aura.system.runtime_report.ollama_tags", return_value=[]),
        ):
            diagnostics = collect_ollama_diagnostics(
                DEFAULT_OLLAMA_HOST,
                "gemma4:e4b-it-qat",
            )

        self.assertFalse(diagnostics.server_ready)
        self.assertFalse(diagnostics.model_available)
        self.assertIn("invalid", diagnostics.detail.lower())


if __name__ == "__main__":
    unittest.main()
