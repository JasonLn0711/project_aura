"""Explicit model doubles for control/transport tests; not inference evidence."""
import shutil
from unittest.mock import patch
from aura.session_core import SessionCore as RealSessionCore


class IdentityReuseWorker:
    def __init__(self, mode, **kwargs):
        self.mode = mode
        self.receipt = {'backend': 'identity-test-double', 'mode': mode}
    def push(self, pcm, **kwargs):
        return pcm
    def flush(self):
        return b''
    def reset(self, *, new_interval=False):
        pass
    def enhance_file(self, source, target):
        shutil.copyfile(source, target)
        return {'path': str(target), **self.receipt}
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass


class SessionCore(RealSessionCore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, enhancement_worker_factory=IdentityReuseWorker, **kwargs)
    def _execute(self, kind, payload):
        if kind == 'export':
            with patch('aura.audio.reuse.ReuseWorker', IdentityReuseWorker):
                return super()._execute(kind, payload)
        return super()._execute(kind, payload)
