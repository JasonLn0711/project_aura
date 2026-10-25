"""Disk-bounded five-second RE-USE overlap-add; never rewrites source media."""
import os
from pathlib import Path
import wave
import numpy as np


def enhance_wav(source, target, predict, progress=None):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise ValueError('Enhancement must preserve its source')
    chunk, hop = 80000, 40000
    with wave.open(str(source), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
            raise ValueError('RE-USE input must be 16 kHz mono signed 16-bit PCM WAV')
        total = audio.getnframes()
        if not total:
            raise ValueError('RE-USE input is empty')
        # Match the official final-window placement, including its overlap with
        # the preceding window. Only the active five seconds stay in memory.
        starts = range(0, max(0, total - chunk), hop)
        def positions():
            yield from starts
            yield max(0, total - chunk)
        window = np.maximum(np.hanning(chunk + 1)[:-1], 1e-7).astype(np.float32)
        accum = np.zeros(chunk, np.float32)
        weight = np.zeros(chunk, np.float32)
        base = 0
        temporary = target.with_suffix(target.suffix + '.partial')
        try:
            with wave.open(str(temporary), 'wb') as output:
                output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                def emit(count):
                    values = accum[:count] / np.maximum(weight[:count], 1e-12)
                    output.writeframesraw((np.clip(values, -1, 32767 / 32768) * 32768).astype('<i2').tobytes())
                for start in positions():
                    shift = start - base
                    if shift:
                        emit(shift)
                        accum[:-shift] = accum[shift:]
                        weight[:-shift] = weight[shift:]
                        accum[-shift:] = weight[-shift:] = 0
                        base = start
                    audio.setpos(start)
                    samples = np.frombuffer(audio.readframes(chunk), '<i2').astype(np.float32) / 32768
                    enhanced = np.asarray(predict(samples), dtype=np.float32)
                    if enhanced.shape != samples.shape or not np.isfinite(enhanced).all():
                        raise ValueError('RE-USE output must preserve finite source samples')
                    count = len(samples)
                    accum[:count] += enhanced * window[:count]
                    weight[:count] += window[:count]
                    if progress:
                        progress(min(total, start + count), total)
                emit(total - base)
            with temporary.open('rb') as f:
                os.fsync(f.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return target
