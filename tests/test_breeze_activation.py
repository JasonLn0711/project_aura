import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aura.asr.models import load_model


class BreezeActivationTests(unittest.TestCase):
    def load_with_backend(self, probe, libraries_ready=False):
        backend = SimpleNamespace(__version__="4.7.1", get_supported_compute_types=probe)
        whisper = Mock()
        with patch.dict("sys.modules", {"ctranslate2": backend,
                                        "faster_whisper": SimpleNamespace(WhisperModel=whisper)}), \
                patch("aura.system.cuda.preload_cuda_runtime_libraries",
                      return_value=(libraries_ready, "missing libcublas.so.12")):
            result = load_model("breeze")
        return result, whisper

    def test_cpu_only_backend_reports_build_requirement(self):
        probe = Mock(side_effect=ValueError("This CTranslate2 package was not compiled with CUDA support"))
        with self.assertRaisesRegex(RuntimeError, "CUDA-enabled CTranslate2 build"):
            self.load_with_backend(probe)

    def test_backend_can_validate_native_cuda_despite_legacy_library_names(self):
        probe = Mock(return_value={"int8", "float32"})
        result, whisper = self.load_with_backend(probe)
        probe.assert_called_once_with("cuda")
        self.assertIs(result, whisper.return_value)
        self.assertEqual(whisper.call_args.kwargs["device"], "cuda")
        self.assertEqual(whisper.call_args.kwargs["compute_type"], "int8")
        self.assertTrue(whisper.call_args.kwargs["local_files_only"])

    def test_backend_failure_keeps_library_diagnostic(self):
        with self.assertRaisesRegex(RuntimeError, "missing libcublas.so.12"):
            self.load_with_backend(Mock(side_effect=RuntimeError("CUDA driver unavailable")))

    def test_backend_failure_still_blocks_when_libraries_load(self):
        with self.assertRaisesRegex(RuntimeError, "CUDA driver unavailable"):
            self.load_with_backend(Mock(side_effect=RuntimeError("CUDA driver unavailable")), True)
