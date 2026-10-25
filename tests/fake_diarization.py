"""Explicit no-GPU test double for existing session lifecycle tests."""
from pathlib import Path


class FakeDiarization:
    def __init__(self, directory, source, media=False):
        self.source = Path(source)
        self.media = media
        self.turns = []
        self.finalized = set()
        self.output = Path(directory) / 'diarization.jsonl'
        self.status = dict(state='ready', processed_sample=0, active=[], sequence=0)

    def advance(self, available, final):
        self.status.update(state='completed' if final else 'running', processed_sample=available,
                           sequence=self.status['sequence'] + 1)
        return dict(done=final, turns=[])

    def close(self):
        pass
