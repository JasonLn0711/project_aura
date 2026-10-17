"""NVIDIA model adapter, imported only in the isolated CUDA worker.

Model implementation and weights stay in the pinned Hugging Face snapshot;
AURA does not redistribute NVIDIA's separately licensed implementation.
"""
import ast
import json
from pathlib import Path
import sys
import types

REVISIONS = {
    'live': ('nvidia/Real-time_RE-USE', '4c0c186272ca853cd18d832fc5c28777b62f32d1'),
    'offline': ('nvidia/RE-USE', '0ee310117ef0ae1e652654c821cf140bdcdc8415'),
}


class ReuseModel:
    def __init__(self, mode, root):
        import torch
        from safetensors.torch import load_file
        self.torch = torch
        if not torch.cuda.is_available():
            raise RuntimeError('RE-USE requires a CUDA service host; CPU devices use remote capture')
        repo, revision = REVISIONS[mode]
        torch.set_num_threads(2)
        self.mode = mode
        self.root = Path(root) / repo.split('/')[-1]
        receipt = json.loads((self.root / 'snapshot.json').read_text())
        if receipt['revision'] != revision:
            raise RuntimeError('RE-USE snapshot revision mismatch')
        import hashlib
        for name, digest in receipt['sha256'].items():
            if hashlib.sha256((self.root / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError(f'RE-USE snapshot checksum mismatch: {name}')
        # Both upstream repositories use the generic package name "models".
        # One process owns exactly one model mode, preventing import collisions.
        sys.path.insert(0, str(self.root))
        cfg = json.loads((self.root / 'config.json').read_text())
        if mode == 'live':
            from models.streaming_generator_SEMamba_time_d1_random_layer_ahead_sep_conv import SEMamba_decoder_list
            model = SEMamba_decoder_list(cfg)
        else:
            from models.generator_SEMamba_time_d4 import SEMamba
            model = SEMamba(cfg)
        model.load_state_dict(load_file(str(self.root / 'model.safetensors')))
        self.model = model.eval().float().cuda()
        if mode == 'live':
            # Import only declarations: upstream online_inference.py performs a
            # mutable-main HF download at import time. Do not execute that code.
            tree = ast.parse((self.root / 'online_inference.py').read_text())
            tree.body = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))]
            module = types.ModuleType('aura_pinned_reuse_streaming')
            import torch.nn.functional as F
            module.__dict__.update(torch=torch, nn=torch.nn, F=F)
            exec(compile(tree, str(self.root / 'online_inference.py'), 'exec'), module.__dict__)
            self.stream = module.StreamingSEMamba(self.model).eval()
            self.stream.reset(161)
        self.receipt = dict(backend=repo, revision=revision, torch=torch.__version__,
                            cuda=torch.version.cuda, device=torch.cuda.get_device_name(0),
                            dtype='float32', sample_rate=16000,
                            ptxas=__import__('os').environ.get('TRITON_PTXAS_PATH', 'triton-bundled'))

    def predict(self, spectrum):
        import numpy as np
        t = self.torch
        with t.inference_mode():
            spec = t.as_tensor(spectrum, device='cuda', dtype=t.complex64)
            mag, phase = self.stream(t.log1p(spec.abs())[None, :, None],
                                     spec.angle()[None, :, None], 8, 0)
            amplitude = t.expm1(mag.relu())
            if (amplitude == 0).float().mean().item() > .5:
                amplitude.zero_()
            result = t.polar(amplitude, phase).flatten().cpu().numpy()
        return np.asarray(result, dtype=np.complex64)

    def offline(self, samples):
        import numpy as np
        from models.stfts import mag_phase_stft, mag_phase_istft
        t = self.torch
        length = len(samples)
        # Upstream reflect padding requires more than half a window.
        samples = np.pad(samples, (0, max(0, 321 - length)))
        with t.inference_mode():
            data = t.as_tensor(samples, device='cuda', dtype=t.float32)[None]
            mag, phase, _ = mag_phase_stft(data, 640, 80, 640, 'relu_log1p', True, False)
            mag, phase, _ = self.model(mag, phase)
            mask = (t.expm1(mag.relu()) == 0).float().mean(1) > .5
            mag = mag.masked_fill(mask[:, None, :], 0)
            out = mag_phase_istft(mag, phase, 640, 80, 640, 'relu_log1p').flatten().cpu().numpy()
        out = np.pad(out, (0, max(0, length - len(out))))[:length]
        if not np.isfinite(out).all():
            raise RuntimeError('RE-USE produced non-finite audio')
        return out
