"""Replayable enhancement consumer of the durable original PCM journal.

Capture ACKs do not depend on this consumer. The journal is the backlog; only a
single transport frame and the model's bounded state are resident in memory.
"""
import os
import json
import threading
from collections import deque


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
        from aura.audio.enhancement_health import EnhancementHealth
        import numpy as np
        core, sid = self.core, self.sid
        directory = core.directory(sid)
        output_path = directory / '.capture/enhanced.pcm'
        output_path.parent.mkdir(exist_ok=True)
        cursor = emitted = boundary_index = 0
        buffer = b''
        vad = intervals = None
        raw_vad = None
        active_gap = None
        source_observations = deque()
        with core.changed:
            policy = core._get(sid)['enhancement'].get('policy', 'reference-v1')
        guard = EnhancementHealth()
        quiet_samples = 0
        recent_levels = deque(maxlen=334)
        try:
            with core.changed:
                known = set()
                for row in core.db.execute("SELECT payload FROM jobs WHERE session=? AND kind='chunk'", (sid,)):
                    payload = json.loads(row['payload'])
                    known.add((payload['start'], payload['end']))
            with output_path.open('wb') as output:
                def enqueue(s, chunk):
                    from aura.reuse_recovery import uncovered_intervals
                    covered = known | {(p['start'], p['end']) for p in
                        (json.loads(r[0]) for r in core.db.execute(
                            "SELECT payload FROM jobs WHERE session=? AND kind='chunk'", (sid,)))}
                    for gap in s['enhancement'].get('gaps', []):
                        if gap.get('live_repair'):
                            covered.update(tuple(r) for r in gap.get('repair_ranges', []))
                    for start, end in uncovered_intervals(chunk.end_sample, covered, chunk.start_sample):
                        s['last_split'] = dict(reason=chunk.split_reason, start_sample=start,
                                              end_sample=end, terminal=chunk.terminal)
                        core._job(s, 'chunk', path=str(output_path), start=start,
                                  end=end, terminal=chunk.terminal, split_reason=chunk.split_reason)
                        known.add((start, end))

                def accept(pcm):
                    nonlocal buffer, emitted, vad, intervals, raw_vad, quiet_samples, active_gap
                    reset = False
                    event = None
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
                            position, source_rms, source_speech = source_observations.popleft()
                            if position != emitted:
                                raise RuntimeError('Source-aligned enhancement evidence is incomplete')
                            event = guard.observe(480, source_rms, rms, source_speech, speech)
                            enhancement = s['enhancement']
                            health = enhancement.setdefault('health', {'status': 'healthy', 'reset_count': 0})
                            gaps = enhancement.setdefault('gaps', [])
                            if (not event and not guard.episode and health.get('status') != 'healthy'
                                    and guard.output_voice >= guard.speech_samples):
                                # A fresh pause/replay interval proves current
                                # output health without rewriting an old gap.
                                health['status'] = 'healthy'
                            if event:
                                if event['event'] == 'suppression':
                                    start = event['start_sample']
                                    gaps.append(dict(id=f'enhancement-{start}', reason='suppression',
                                        start_sample=start, end_sample=event['end_sample'], status='pending'))
                                    active_gap = gaps[-1]
                                    if policy == 'speech-guard-v1':
                                        active_gap['live_repair'] = 'waiting'
                                        active_gap['repair_end_sample'] = event['end_sample']
                                    health.update(status='recovering', reset_count=health.get('reset_count', 0) + 1,
                                                  source_rms=event['source_rms'], output_rms=event['output_rms'])
                                    reset = True
                                elif event['event'] == 'unresolved':
                                    health['status'] = 'blocked'
                                    if active_gap and active_gap.get('live_repair') == 'waiting':
                                        active_gap['repair_end_sample'] = event['end_sample']
                                        active_gap['live_repair'] = 'queued'
                                elif event['event'] == 'restored':
                                    health['status'] = 'healthy'
                                    if active_gap:
                                        active_gap['closed'] = True
                                        if active_gap.get('live_repair') == 'waiting':
                                            active_gap['repair_end_sample'] = event['end_sample']
                                            active_gap['live_repair'] = 'queued'
                                if active_gap:
                                    active_gap['end_sample'] = event['end_sample']
                            if guard.episode and active_gap:
                                active_gap['end_sample'] = emitted + 480
                            signal = s.setdefault('capture_signal', {'peak_rms': 0.0, 'speech_frames': 0})
                            signal['peak_rms'] = max(signal['peak_rms'], rms)
                            signal['speech_frames'] += int(speech)
                            recent_levels.append(source_rms)
                            quiet_samples = 0 if speech else quiet_samples + 480
                            if speech:
                                s.pop('capture_warning', None)
                            elif quiet_samples >= 160000:
                                s['capture_warning'] = 'Audio received, but no speech detected; no audio sent to ASR.' if max(recent_levels, default=0) >= 80 else 'No audible input detected. Check playback and the selected audio source.'
                            chunk = intervals.push(samples, speech)
                            emitted += 480
                            if chunk:
                                enqueue(s, chunk)
                        s['enhancement'].update(processed_samples=emitted, input_samples=cursor,
                                                backlog_samples=max(0, s['samples'] - cursor))
                        s['enhancement']['diagnostics'] = getattr(self.worker, 'diagnostics', {})
                        core.changed.notify_all()
                        if reset or event or emitted % 16320 == 0:
                            core._save(s, progress=True)
                    return reset

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
                            self.worker = factory('live', log_path=directory / 'reuse-live.log', live_policy=policy)
                            with core.changed:
                                s['enhancement']['runtime'] = self.worker.receipt
                        if raw_vad is None:
                            raw_vad = SileroStreamVAD()
                        values = np.frombuffer(raw, '<i2').astype(np.float32)
                        source_rms = float(np.sqrt(np.mean(values ** 2)))
                        source_speech = bool(raw_vad.is_speech(raw.ljust(960, b'\0'), 16000))
                        source_observations.append((cursor, source_rms, source_speech))
                        evidence = {'source_speech': source_speech and source_rms >= 80} if policy == 'speech-guard-v1' else {}
                        pcm = self.worker.push(raw, **evidence)
                        cursor += len(raw) // 2
                        if accept(pcm):
                            # Reset only model state. The STFT and capture clock
                            # continue, and erased audio remains a recovery gap.
                            self.worker.reset()
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
                            raw_vad = None
                            guard = EnhancementHealth()
                            guard.position = emitted
                            active_gap = None
                            quiet_samples = 0
                            recent_levels.clear()
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
