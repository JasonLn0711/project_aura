import unittest
from unittest.mock import patch

from aura.asr.threads import ModelLoaderThread, REQUIRED_ASR_DEVICE, cuda_required_error


class GpuPolicyTests(unittest.TestCase):
    def test_model_loader_pins_asr_to_cuda_even_if_cpu_requested(self):
        loader = ModelLoaderThread(device="cpu", compute_type="int8")

        self.assertEqual(loader.device, REQUIRED_ASR_DEVICE)
        self.assertEqual(loader.actual_device, REQUIRED_ASR_DEVICE)
        self.assertEqual(loader.requested_device, "cpu")

    def test_model_loader_refuses_cpu_fallback_when_cuda_runtime_is_missing(self):
        errors = []
        statuses = []
        loader = ModelLoaderThread(device="cuda", compute_type="int8")
        loader.error_signal.connect(errors.append)
        loader.status_signal.connect(statuses.append)

        with (
            patch("aura.asr.threads.preload_cuda_runtime_libraries", return_value=(False, "missing cublas")),
            patch("aura.asr.threads.WhisperModel") as whisper_model,
        ):
            loader.run()

        whisper_model.assert_not_called()
        self.assertEqual(errors, [cuda_required_error("missing cublas")])
        self.assertEqual(statuses, [])
        self.assertEqual(loader.actual_device, REQUIRED_ASR_DEVICE)

    def test_model_loader_constructs_whisper_model_only_on_cuda(self):
        loader = ModelLoaderThread(device="cuda", compute_type="int8")

        with (
            patch("aura.asr.threads.preload_cuda_runtime_libraries", return_value=(True, "system")),
            patch("aura.asr.threads.WhisperModel", return_value=object()) as whisper_model,
        ):
            loader.run()

        self.assertEqual(whisper_model.call_args.kwargs["device"], REQUIRED_ASR_DEVICE)
        self.assertEqual(whisper_model.call_args.kwargs["compute_type"], "int8")


if __name__ == "__main__":
    unittest.main()
