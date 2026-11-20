"""A regenerable output journal with an explicit ASR durability barrier."""
import os
import time


class EnhancedJournal:
    def __init__(self, output, *, grouped=False, timings=None):
        self.output = output
        self.grouped = grouped
        self.timings = timings
        self.samples = self.durable_samples = 0
        self.last_checkpoint = time.monotonic()

    def write(self, pcm):
        if len(pcm) % 2:
            raise ValueError('Enhanced PCM must contain complete samples')
        self.output.write(pcm)
        self.output.flush()
        self.samples += len(pcm) // 2
        if not self.grouped or time.monotonic() - self.last_checkpoint >= 1:
            self.checkpoint()

    def checkpoint(self):
        if self.samples == self.durable_samples:
            return self.durable_samples
        from contextlib import nullcontext
        with self.timings.measure('enhanced_fsync') if self.timings else nullcontext():
            self.output.flush()
            os.fsync(self.output.fileno())
        # Never publish a durable cursor before fsync has succeeded.
        self.durable_samples = self.samples
        self.last_checkpoint = time.monotonic()
        return self.durable_samples
