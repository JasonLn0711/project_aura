"""Nemotron's isolated runtime; no model libraries are imported by clients."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
from dataclasses import dataclass

from aura.diarization.speaker_assignment import SpeakerTurn

MODEL_ID = 'nvidia/Nemotron-3-Diarization'
MODEL_REVISION = 'f667ed73aee57d40cc39428eb768b4fd87a0a29e'
TRANSFORMERS_REVISION = '50e35cc0ca18ec19b80653690de553e6decf74f5'


class DiarizationDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiarizationSettings:
    enabled: bool = True
    model_id: str = MODEL_ID
    device: str = 'cuda'

    def __post_init__(self):
        if self.model_id != MODEL_ID or self.device != 'cuda':
            raise ValueError('Diarization requires the pinned Nemotron model on CUDA')


def runtime_python():
    return Path(os.environ.get('AURA_NEMOTRON_PYTHON',
        Path(__file__).resolve().parents[3] / '.venv-nemotron/bin/python'))


def validate_diarization_runtime(settings):
    if settings.enabled and not runtime_python().is_file():
        raise DiarizationDependencyError('Nemotron runtime missing; run python3 scripts/setup_nemotron.py')


class NemotronWorker:
    """Single caller per worker; bounded requests and explicit process ownership."""
    def __init__(self, directory):
        validate_diarization_runtime(DiarizationSettings())
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.log = (directory / 'nemotron.stderr.log').open('a', encoding='utf-8')
        env = dict(os.environ, HF_HUB_DISABLE_PROGRESS_BARS='1', TOKENIZERS_PARALLELISM='false')
        self.process = subprocess.Popen([str(runtime_python()), '-u', str(Path(__file__).with_name('worker.py'))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1, env=env, start_new_session=True)
        self.closed = False
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        try:
            self.receipt = self.request('load', timeout=300)
        except BaseException:
            self.close()
            raise

    def request(self, command, timeout=60, **values):
        if self.process.poll() is not None:
            raise DiarizationDependencyError('Nemotron worker exited; inspect nemotron.stderr.log')
        self.process.stdin.write(json.dumps(dict(command=command, **values)) + '\n')
        self.process.stdin.flush()
        if not self.selector.select(timeout):
            self.close()
            raise TimeoutError(f'Nemotron {command} watchdog expired')
        line = self.process.stdout.readline()
        if not line:
            raise DiarizationDependencyError('Nemotron worker closed its output; inspect nemotron.stderr.log')
        result = json.loads(line)
        if 'error' in result:
            raise DiarizationDependencyError(result['error'])
        return result

    def close(self):
        if self.closed:
            return
        self.closed = True
        if os.name == 'posix':
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if os.name == 'posix':
            # A decoder may outlive a crashed worker; both belong to this process group.
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.selector.close()
        for stream in (self.process.stdin, self.process.stdout, self.log):
            stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def merge_turns(turns):
    """Join adjacent slices from the same channel without removing overlap."""
    result = []
    last = {}
    for turn in sorted(turns, key=lambda t: (t.start, t.speaker)):
        index = last.get(turn.speaker)
        if index is not None and abs(result[index].end - turn.start) < 0.00001:
            old = result[index]
            result[index] = SpeakerTurn(old.start, turn.end, old.speaker)
        else:
            last[turn.speaker] = len(result)
            result.append(turn)
    return sorted(result, key=lambda t: (t.start, t.speaker))


def diarize_audio_file(audio_path, settings, cancellation=None):
    if not settings.enabled:
        return []
    from aura.system.runtime_paths import runtime_dir
    turns = []
    with NemotronWorker(runtime_dir()) as worker:
        worker.request('reset', path=str(Path(audio_path).resolve()), media=True)
        while True:
            if cancellation:
                cancellation.raise_if_cancelled()
            event = worker.request('advance', final=True)
            turns.extend(SpeakerTurn(**t) for t in event['turns'])
            if event['done']:
                break
    return merge_turns(turns)
