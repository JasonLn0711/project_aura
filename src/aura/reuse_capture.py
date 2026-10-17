"""Replayable enhancement consumer of the durable original PCM journal.

Capture ACKs do not depend on this consumer. The journal is the backlog; only a
single transport frame and the model's bounded state are resident in memory.
"""
import os
import json
import threading


class ReuseCapture:
    def __init__(self, core, sid):
        self.core, self.sid = core, sid
        self.worker = None
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._run, name='aura-reuse-capture', daemon=True)
        self.thread.start()

    def close(self):
        self.closed.set()
        if self.worker:
            self.worker.close()
        self.thread.join(timeout=5)

    def _run(self):
        from aura.audio.reuse import ReuseWorker
        from aura.audio.vad import SileroStreamVAD, SpeechIntervals
        import numpy as np
        core, sid = self.core, self.sid
        directory = core.directory(sid)
        output_path = directory / '.capture/enhanced.pcm'
        output_path.parent.mkdir(exist_ok=True)
        cursor = emitted = boundary_index = 0
        buffer = b''
        vad = intervals = None
        try:
            with core.changed:
                known = set()
                for row in core.db.execute("SELECT payload FROM jobs WHERE session=? AND kind='chunk'", (sid,)):
                    payload = json.loads(row['payload'])
                    known.add((payload['start'], payload['end']))
            with output_path.open('wb') as output:
                def enqueue(s, chunk):
                    key = (chunk.start_sample, chunk.end_sample)
                    if key in known:
                        return
                    s['last_split'] = dict(reason=chunk.split_reason, start_sample=chunk.start_sample,
                                           end_sample=chunk.end_sample, terminal=chunk.terminal)
                    core._job(s, 'chunk', path=str(output_path), start=chunk.start_sample,
                              end=chunk.end_sample, terminal=chunk.terminal, split_reason=chunk.split_reason)
                    known.add(key)

                def accept(pcm):
                    nonlocal buffer, emitted, vad, intervals
                    output.write(pcm)
                    output.flush()
                    os.fsync(output.fileno())
                    buffer += pcm
                    with core.changed:
                        s = core._get(sid)
                        if intervals is None:
                            vad = SileroStreamVAD()
                            intervals = SpeechIntervals(480,
                                max_seconds=s['options'].get('live_max_segment_len_sec', 12),
                                silence_ms=s['options'].get('live_silence_ms', 800),
                                segmentation=s['options'].get('live_segmentation', 'fixed'))
                            intervals.position = emitted
                            core.detectors[sid] = (vad, intervals, {})
                        while len(buffer) >= 960:
                            raw, buffer = buffer[:960], buffer[960:]
                            samples = np.frombuffer(raw, '<i2')
                            speech = vad.is_speech(raw, 16000)
                            rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
                            signal = s.setdefault('capture_signal', {'peak_rms': 0.0, 'speech_frames': 0})
                            signal['peak_rms'] = max(signal['peak_rms'], rms)
                            signal['speech_frames'] += int(speech)
                            if signal['speech_frames']:
                                s.pop('capture_warning', None)
                            elif emitted + 480 >= 160000:
                                s['capture_warning'] = 'Audio received, but no speech detected; no audio sent to ASR.' if signal['peak_rms'] >= 80 else 'No audible input detected. Check playback and the selected audio source.'
                            chunk = intervals.push(samples, speech)
                            emitted += 480
                            if chunk:
                                enqueue(s, chunk)
                        s['enhancement'].update(processed_samples=emitted, input_samples=cursor,
                                                backlog_samples=max(0, s['samples'] - cursor))
                        if emitted % 16320 == 0:
                            core._save(s, progress=True)

                while not self.closed.is_set():
                    with core.changed:
                        s = core._get(sid)
                        if core.shutdown or s['state'] in ('failed', 'cancelled', 'deleting'):
                            return
                        state = s['enhancement']
                        boundaries = state.get('boundaries', [])
                        boundary = boundaries[boundary_index] if boundary_index < len(boundaries) else None
                        limit = boundary['sample'] if boundary else s.get('stream', {}).get('durable_sequence', s['input_sequence']) * 480
                        if cursor < limit:
                            path = directory / '.capture/mixed.pcm'
                            with path.open('rb') as source:
                                source.seek(cursor * 2)
                                raw = source.read(min(480, limit - cursor) * 2)
                            if len(raw) != min(480, limit - cursor) * 2:
                                raise RuntimeError('Durable original audio journal is incomplete')
                        else:
                            raw = None
                    if raw:
                        if self.worker is None:
                            factory = core.enhancement_worker_factory or ReuseWorker
                            self.worker = factory('live', log_path=directory / 'reuse-live.log')
                            with core.changed:
                                s['enhancement']['runtime'] = self.worker.receipt
                        pcm = self.worker.push(raw)
                        cursor += len(raw) // 2
                        accept(pcm)
                    elif boundary:
                        if self.worker:
                            accept(self.worker.flush())
                            self.worker.close()
                            self.worker = None
                        if buffer or emitted != cursor:
                            raise RuntimeError('RE-USE boundary length mismatch')
                        with core.changed:
                            if intervals:
                                chunk = intervals.finish(boundary['action'])
                                if chunk:
                                    enqueue(s, chunk)
                            intervals = vad = None
                            boundary_index += 1
                            state['completed_boundaries'] = boundary_index
                            if boundary['action'] == 'pause' and s['state'] == 'pausing':
                                s['state'] = 'paused'
                            if boundary['action'] == 'stop':
                                state['live_complete'] = True
                                core._save(s)
                                core.changed.notify_all()
                                return
                            core._save(s)
                    else:
                        self.closed.wait(.02)
        except Exception as exc:
            with core.changed:
                if not core.shutdown:
                    s = core._get(sid)
                    s.update(state='failed', error=f'RE-USE enhancement failed: {exc}. Original audio retained; use /recover after repair.')
                    s['enhancement']['error'] = str(exc)
                    core._save(s)
        finally:
            if self.worker:
                self.worker.close()
                self.worker = None
