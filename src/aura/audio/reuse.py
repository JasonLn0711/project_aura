"""CPU-safe client for the isolated, fixed-revision RE-USE CUDA worker."""
import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import threading

STRATEGY = 'reuse-v1'


class ReuseWorker:
    def __init__(self, mode, *, progress=None, log_path=None, live_policy='reference-v1'):
        runtime = Path(os.environ.get('AURA_REUSE_RUNTIME', Path(__file__).resolve().parents[3] / 'runtime'))
        python = runtime / 'reuse-venv/bin/python'
        if not python.is_file():
            raise RuntimeError('RE-USE runtime is unavailable. On the CUDA host run: python3 scripts/setup_reuse_runtime.py')
        self.log = open(log_path, 'ab', buffering=0) if log_path else None
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]), HF_HUB_OFFLINE='1')
        ptxas = Path(os.environ.get('CUDA_HOME', '/usr/local/cuda')) / 'bin/ptxas'
        if ptxas.is_file():
            env.setdefault('TRITON_PTXAS_PATH', str(ptxas))
        if (runtime / 'reuse-headers/python3.12/Python.h').is_file():
            env['CPATH'] = os.pathsep.join([str(runtime / 'reuse-headers/python3.12'), str(runtime / 'reuse-headers'), env.get('CPATH', '')])
        self.process = subprocess.Popen([str(python), '-m', 'aura.audio.reuse_worker'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1, env=env)
        self.closed = False
        self.close_lock = threading.Lock()
        self.responses = queue.Queue()
        self.progress = progress
        self.diagnostics = {}
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.receipt = self.call(action='load', mode=mode, root=str(runtime / 'reuse-source'), live_policy=live_policy)
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.process.stdout:
                self.responses.put(json.loads(line))
        except Exception as exc:
            self.responses.put({'ok': False, 'error': str(exc)})
        finally:
            self.responses.put({'ok': False, 'error': 'RE-USE worker exited; original audio retained'})

    def call(self, **request):
        try:
            self.process.stdin.write(json.dumps(request) + '\n')
            self.process.stdin.flush()
            while True:
                reply = self.responses.get(timeout=300)
                if 'progress' in reply:
                    if self.progress:
                        self.progress(reply['progress'])
                    continue
                if not reply['ok']:
                    raise RuntimeError(reply['error'])
                return reply['result']
        except (OSError, queue.Empty) as exc:
            self.close()
            raise RuntimeError('RE-USE worker unavailable; original audio retained for recovery') from exc

    def push(self, pcm, *, source_speech=None):
        evidence = {} if source_speech is None else {'source_speech': source_speech}
        result = self.call(action='push', pcm=base64.b64encode(pcm).decode(), **evidence)
        self.diagnostics = result.get('diagnostics', {})
        return base64.b64decode(result['pcm'])

    def flush(self):
        result = self.call(action='flush')
        self.diagnostics = result.get('diagnostics', {})
        return base64.b64decode(result['pcm'])

    def reset(self, *, new_interval=False):
        return self.call(action='reset', new_interval=new_interval)

    def enhance_file(self, source, target):
        return self.call(action='file', source=str(source), target=str(target))

    def close(self):
        with self.close_lock:
            if self.closed:
                return
            self.closed = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process.stdin.close()
        self.process.stdout.close()
        self.reader.join(timeout=1)
        if self.log:
            self.log.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
