"""Bounded source evidence for live spectral gating; never an ASR audio path."""
from collections import deque

REFERENCE = 'reference-v1'
SPEECH_GUARD = 'speech-guard-v1'
POLICIES = (REFERENCE, SPEECH_GUARD)


class SourceSpeechProtection:
    hangover = 5120  # 320 ms at 16 kHz

    def __init__(self):
        self.received = self.until = 0
        self.ranges = deque()

    def push(self, count, speech):
        if type(count) is not int or count <= 0 or type(speech) is not bool:
            raise ValueError('Source evidence requires a positive sample count and boolean speech')
        start = self.received
        self.received += count
        if speech:
            self.until = self.received + self.hangover
        end = min(self.received, self.until)
        if end > start:
            if self.ranges and self.ranges[-1][1] >= start:
                self.ranges[-1] = (self.ranges[-1][0], end)
            else:
                self.ranges.append((start, end))

    def protected(self, start, end):
        start, end = max(0, start), min(self.received, end)
        while self.ranges and self.ranges[0][1] <= start:
            self.ranges.popleft()
        return end > start and any(left < end and right > start for left, right in self.ranges)
