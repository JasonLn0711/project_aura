"""Bounded centered STFT/overlap-add for RE-USE's 16 kHz stream.

The predictor owns model state; this module owns sample alignment. One instance
covers one continuous capture interval, independently of ASR segmentation.
"""
import numpy as np


class StreamingEnhancer:
    n_fft = 640
    hop = 320

    def __init__(self, predict):
        self.predict = predict
        self.window = np.hanning(self.n_fft + 1)[:-1].astype(np.float32)
        self.pending = np.empty(0, dtype=np.float32)
        self.tail = np.empty(0, dtype=np.float32)
        self.ola = np.zeros(self.n_fft, dtype=np.float32)
        self.weight = np.zeros(self.n_fft, dtype=np.float32)
        self.received = self.emitted = self.frames = 0
        self.started = self.closed = False

    def push(self, samples):
        if self.closed:
            raise ValueError('Stream is already closed')
        samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim != 1 or not np.isfinite(samples).all():
            raise ValueError('Expected finite mono samples')
        self.received += len(samples)
        self.tail = np.concatenate((self.tail, samples))[-self.n_fft:]
        self.pending = np.concatenate((self.pending, samples))
        if not self.started and len(self.pending) > self.hop:
            self.pending = np.concatenate((self.pending[1:self.hop + 1][::-1], self.pending))
            self.started = True
        return self._drain() if self.started else np.empty(0, np.float32)

    def _drain(self):
        outputs = []
        while len(self.pending) >= self.n_fft:
            spectrum = np.fft.rfft(self.pending[:self.n_fft] * self.window)
            enhanced = np.asarray(self.predict(spectrum), dtype=np.complex64)
            if enhanced.shape != spectrum.shape or not np.isfinite(enhanced).all():
                raise ValueError('Enhancer returned invalid spectrum')
            self.ola += np.fft.irfft(enhanced, n=self.n_fft).astype(np.float32) * self.window
            self.weight += self.window ** 2
            # The first half-window precedes source sample zero.
            if self.frames:
                count = min(self.hop, self.received - self.emitted)
                outputs.append((self.ola[:count] / np.maximum(self.weight[:count], 1e-12)).copy())
                self.emitted += count
            self.frames += 1
            self.ola[:-self.hop] = self.ola[self.hop:]
            self.ola[-self.hop:] = 0
            self.weight[:-self.hop] = self.weight[self.hop:]
            self.weight[-self.hop:] = 0
            self.pending = self.pending[self.hop:]
        return np.concatenate(outputs) if outputs else np.empty(0, np.float32)

    def flush(self):
        if self.closed:
            raise ValueError('Stream is already closed')
        self.closed = True
        if not self.received:
            return np.empty(0, np.float32)
        if not self.started:
            # Reflect padding has no definition for one sample; edge extension
            # gives a deterministic extension for short continuous intervals.
            mode = 'reflect' if self.received > 1 else 'edge'
            self.pending = np.pad(self.pending, (self.hop, 0), mode=mode)
            self.started = True
        # Include one additional frame to retain a partial final hop. Padding
        # does not advance the capture clock or get sent to ASR.
        mode = 'reflect' if len(self.tail) > 1 else 'edge'
        right = np.pad(self.tail, (0, self.n_fft), mode=mode)[len(self.tail):]
        self.pending = np.concatenate((self.pending, right))
        output = self._drain()
        if self.emitted != self.received:
            raise RuntimeError('Enhancement did not preserve the capture length')
        return output
