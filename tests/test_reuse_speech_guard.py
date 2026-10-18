"""Exercise production spectral gating without loading CUDA or model weights."""
from types import SimpleNamespace
import contextlib
import unittest
import numpy as np
from aura.audio.reuse_model import ReuseModel


class Tensor(np.ndarray):
    def relu(self): return np.maximum(self, 0).view(Tensor)
    def float(self): return self.astype(np.float32)
    def abs(self): return np.abs(self).view(Tensor)
    def angle(self): return np.angle(self).view(Tensor)
    def cpu(self): return self
    def numpy(self): return np.asarray(self)
    def zero_(self): self.fill(0)


class SpectralGuardTests(unittest.TestCase):
    def model(self, positive=121):
        model = ReuseModel.__new__(ReuseModel)
        tensor = lambda x: np.asarray(x).view(Tensor)
        model.torch = SimpleNamespace(inference_mode=contextlib.nullcontext,
            as_tensor=lambda value, **kw: tensor(value), complex64=np.complex64,
            log1p=lambda x: tensor(np.log1p(x)), expm1=lambda x: tensor(np.expm1(x)),
            polar=lambda amplitude, phase: tensor(amplitude * np.exp(1j * phase)))
        magnitude = tensor([-.5] * (321 - positive) + [.25] * positive)[None, :, None]
        model.stream = lambda *args: (magnitude, tensor(np.zeros_like(magnitude)))
        model.live_policy = 'speech-guard-v1'
        model.diagnostics = {}
        return model

    def test_protected_frame_preserves_actual_model_bins(self):
        model = self.model()
        actual = model.predict(np.ones(321, np.complex64), protect_speech=True)
        self.assertEqual(np.count_nonzero(actual), 121)
        np.testing.assert_allclose(actual[-121:].real, np.expm1(.25), rtol=1e-6)

    def test_noise_and_reference_keep_the_original_gate(self):
        for policy, protected in [('speech-guard-v1', False), ('reference-v1', True)]:
            model = self.model()
            model.live_policy = policy
            self.assertFalse(self.model_output(model, protected).any())

    def model_output(self, model, protected):
        return model.predict(np.ones(321, np.complex64), protect_speech=protected)

    def test_native_zero_is_not_replaced_with_original_or_gain(self):
        model = self.model(0)
        self.assertFalse(self.model_output(model, True).any())
        self.assertEqual(model.diagnostics['native_zero_frames'], 1)
        self.assertEqual(model.diagnostics['postfilter_erased_nonzero_frames'], 0)

    def test_non_gated_frame_is_unchanged(self):
        model = self.model(200)
        protected = self.model_output(model, True)
        model.live_policy = 'reference-v1'
        np.testing.assert_array_equal(protected, self.model_output(model, False))


class SourceAlignmentTests(unittest.TestCase):
    def test_window_overlap_hangover_and_no_padding_evidence(self):
        from aura.audio.reuse_policy import SourceSpeechProtection
        evidence = SourceSpeechProtection()
        evidence.push(480, True)
        self.assertTrue(evidence.protected(-320, 320))
        evidence.push(5120, False)
        self.assertTrue(evidence.protected(5280, 5600))
        self.assertFalse(evidence.protected(5600, 5920))
        self.assertFalse(evidence.protected(6000, 6320))
        evidence.push(640, False)
        self.assertFalse(evidence.protected(5600, 6240))

    def test_evidence_is_bounded_and_interval_reset_is_fresh(self):
        from aura.audio.reuse_policy import SourceSpeechProtection
        evidence = SourceSpeechProtection()
        for _ in range(1000):
            evidence.push(480, True)
            self.assertTrue(evidence.protected(evidence.received - 640, evidence.received))
            self.assertLessEqual(len(evidence.ranges), 3)
        self.assertFalse(SourceSpeechProtection().protected(-320, 320))

    def test_invalid_evidence_is_rejected(self):
        from aura.audio.reuse_policy import SourceSpeechProtection
        for count, speech in [(0, True), (-1, False), (480, None), (480, 1)]:
            with self.assertRaises(ValueError):
                SourceSpeechProtection().push(count, speech)
