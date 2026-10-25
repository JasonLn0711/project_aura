"""Stopped-recording recovery of unqueued speech through the fixed RE-USE model.

Original audio determines missing source intervals, never ASR input. Each bounded
interval gets fresh model/STFT state and an enhanced, source-aligned journal.
"""
import json
import os
import threading
import uuid

from aura.audio.enhancement_health import EnhancementHealth, pending_gaps


def enhance_source(worker, audio, policy, before_push=None):
    """Send source speech evidence, never source PCM, around the enhancement path."""
    import numpy as np
    from aura.audio.vad import SileroStreamVAD
    detector = SileroStreamVAD() if policy == 'speech-guard-v1' else None
    parts = []
    for offset in range(0, len(audio), 960):
        if before_push:
            before_push()
        pcm = audio[offset:offset + 960]
        evidence = {}
        if detector:
            speech = detector.is_speech(pcm.ljust(960, b'\0'), 16000)
            rms = float(np.sqrt(np.mean(np.frombuffer(pcm, '<i2').astype(np.float32) ** 2)))
            evidence['source_speech'] = bool(speech and rms >= 80)
        parts.append(worker.push(pcm, **evidence))
    if before_push:
        before_push()
    parts.append(worker.flush())
    return b''.join(parts)


def usable_enhancement(original, enhanced, prefix=0):
    """Warm VAD on context, but assess only the missing source interval."""
    import numpy as np
    from aura.audio.vad import SileroStreamVAD
    source_vad, enhanced_vad = SileroStreamVAD(), SileroStreamVAD()
    guard = EnhancementHealth()
    enhanced_speech = suppressed = False
    rms = lambda pcm: float(np.sqrt(np.mean(np.frombuffer(pcm, '<i2').astype(np.float32) ** 2)))
    for offset in range(0, len(original), 960):
        raw, result = original[offset:offset + 960], enhanced[offset:offset + 960]
        source_speech = source_vad.is_speech(raw.ljust(960, b'\0'), 16000)
        voice = enhanced_vad.is_speech(result.ljust(960, b'\0'), 16000)
        begin = max(0, prefix * 2 - offset)
        if begin >= len(raw):
            continue
        raw, result = raw[begin:], result[begin:]
        enhanced_speech |= voice
        event = guard.observe(len(raw) // 2, rms(raw), rms(result), source_speech, voice)
        suppressed |= bool(event and event['event'] == 'suppression')
    return enhanced_speech and not suppressed


def uncovered_intervals(total, covered, start=0):
    cursor = start
    for left, right in sorted(covered):
        if right <= cursor:
            continue
        if left >= total:
            break
        if left > cursor:
            yield cursor, min(left, total)
        cursor = max(cursor, right)
        if cursor >= total:
            return
    if cursor < total:
        yield cursor, total


def resolve_scanned_gaps(session):
    state = session.get('enhancement', {})
    if state.get('recovery_scanning') or state.get('recovery_scanned_samples', -1) < session.get('samples', 0):
        return
    gaps = state.get('gaps', [])
    for gap in gaps:
        eligible = gap['reason'] == 'suppression' or (gap['reason'] == 'live_repair' and not gap.get('submitted'))
        if gap['status'] == 'pending' and eligible and not gap.get('review_required_ranges'):
            children = [g for g in gaps if g['reason'] == 'recovery' and
                        g['start_sample'] < gap['end_sample'] and g['end_sample'] > gap['start_sample']]
            if not any(g['status'] == 'pending' for g in children):
                gap['status'] = 'resolved'
                gap['resolution'] = 'Unqueued source speech scanned and recovery jobs completed'
    if not pending_gaps(session):
        state.setdefault('health', {})['status'] = 'healthy'


def start_recovery(core, session, source):
    sid = session['id']
    previous = core.recoveries.get(sid)
    if previous and previous.thread.is_alive():
        raise ValueError('Enhancement recovery is still running')
    session.update(state='draining', error=None, recovery_active=True, delivery_committed=False)
    if session['options'].get('diarization') and session.get('diarization', {}).get('state') != 'completed':
        session['diarization'] = dict(state='recovering', active=[], processed_sample=0)
    session['enhancement'].update(recovery_scanning=True, recovery_scanned_samples=-1,
                                  recovery_progress=dict(completed_samples=0, total_samples=session['samples']))
    core._recovery_job_options(session)
    core.db.execute("UPDATE jobs SET state='queued' WHERE session=? AND kind='chunk' AND state='failed'", (sid,))
    core._save(session)
    recovery = ReuseRecovery(core, sid, source)
    core.recoveries[sid] = recovery
    recovery.thread.start()
    return session


class ReuseRecovery:
    def __init__(self, core, sid, source):
        self.core, self.sid, self.source = core, sid, source
        self.closed = threading.Event()
        self.worker = None
        self.thread = threading.Thread(target=self._run, name='aura-reuse-recovery', daemon=True)

    def close(self):
        self.closed.set()
        if self.worker:
            self.worker.close()
        self.thread.join(timeout=5)

    def _run(self):
        import numpy as np
        from aura.audio.reuse import ReuseWorker
        from aura.audio.vad import SileroStreamVAD, SpeechIntervals
        from aura.audio.recording_session import write_session_manifest
        core, sid = self.core, self.sid
        directory = core.directory(sid)
        output_path = directory / '.capture' / f'recovery-{uuid.uuid4().hex}.pcm'
        try:
            with core.changed:
                s = core._get(sid)
                total = s['samples']
                if self.source.stat().st_size < total * 2:
                    raise RuntimeError('Retained original audio is incomplete; recovery did not modify the transcript')
                covered = [(p['start'], p['end']) for p in
                    (json.loads(row[0]) for row in core.db.execute(
                        "SELECT payload FROM jobs WHERE session=? AND kind='chunk'", (sid,)))]
                options = dict(s['options'])
                policy = s['enhancement'].get('policy', 'reference-v1')
                manifest_path = directory / 'session.json'
                manifest = json.loads(manifest_path.read_text())
                cleanup = manifest.setdefault('audio_cleanup_pending', [])
                for path in (output_path, self.source):
                    name = str(path.relative_to(directory))
                    if name not in cleanup:
                        cleanup.append(name)
                write_session_manifest(manifest_path, manifest)
            output_path.parent.mkdir(exist_ok=True)
            with self.source.open('rb') as source, output_path.open('wb') as output:
                def process(chunk, limit):
                    if self.closed.is_set():
                        raise InterruptedError('Enhancement recovery interrupted; original audio retained')
                    start, end = chunk.start_sample, min(limit, chunk.end_sample)
                    gap_id = f'recovery-{start}-{end}'
                    with core.changed:
                        gaps = s['enhancement'].setdefault('gaps', [])
                        gap = next((g for g in gaps if g['id'] == gap_id), None)
                        if gap is None:
                            gap = dict(id=gap_id, reason='recovery', start_sample=start,
                                       end_sample=end, status='pending', attempts=0)
                            gaps.append(gap)
                        gap['attempts'] += 1
                        core._save(s)
                    # Two seconds of real source context are discarded from
                    # ASR input. Retry once without context if that context
                    # itself drives the fresh model into suppression.
                    usable = False
                    for context in dict.fromkeys((max(0, start - 32000), start)):
                        if self.worker is None:
                            factory = core.enhancement_worker_factory or ReuseWorker
                            self.worker = factory('live', log_path=directory / 'reuse-recovery.log', live_policy=policy)
                        else:
                            self.worker.reset(new_interval=True)
                        source.seek(context * 2)
                        audio = source.read((end - context) * 2)
                        if len(audio) != (end - context) * 2:
                            raise RuntimeError('Retained recovery interval is incomplete')
                        enhanced = enhance_source(self.worker, audio, policy)
                        if len(enhanced) != len(audio):
                            raise RuntimeError('RE-USE recovery changed the source sample count')
                        usable = usable_enhancement(audio, enhanced, start - context)
                        enhanced = enhanced[(start - context) * 2:]
                        if usable:
                            break
                    if not usable:
                        with core.changed:
                            gap['error'] = 'Fresh RE-USE state still suppressed source speech; original audio retained'
                            s['enhancement'].setdefault('health', {})['status'] = 'blocked'
                            core._save(s)
                        return
                    output.seek(start * 2)
                    output.write(enhanced)
                    output.flush()
                    os.fsync(output.fileno())
                    with core.changed:
                        gap.pop('error', None)
                        core._job(s, 'chunk', path=str(output_path), start=start, end=end,
                                  terminal=True, split_reason='enhancement_recovery', enhancement_gap_id=gap_id)

                for left, right in uncovered_intervals(total, covered):
                    detector = SileroStreamVAD()
                    intervals = SpeechIntervals(480, max_seconds=options.get('live_max_segment_len_sec', 20),
                        silence_ms=options.get('live_silence_ms', 800),
                        segmentation=options.get('live_segmentation', 'adaptive'))
                    intervals.position = left
                    # process() seeks the same source; every scan read uses an
                    # explicit source cursor rather than the shared file offset.
                    position = left
                    while position < right:
                        if self.closed.is_set():
                            raise InterruptedError('Enhancement recovery interrupted; original audio retained')
                        count = min(480, right - position)
                        source.seek(position * 2)
                        pcm = source.read(count * 2)
                        if len(pcm) != count * 2:
                            raise RuntimeError('Original recovery scan is truncated')
                        frame = pcm.ljust(960, b'\0')
                        chunk = intervals.push(np.frombuffer(frame, '<i2'), detector.is_speech(frame, 16000))
                        position += count
                        if chunk:
                            process(chunk, right)
                        if position % 16320 < 480:
                            with core.changed:
                                s['enhancement']['recovery_progress']['completed_samples'] = position
                                core._save(s, progress=True)
                    chunk = intervals.finish('recovery')
                    if chunk:
                        process(chunk, right)
            with core.changed:
                if not (s['artifacts'].get('wav') or s['artifacts'].get('m4a')):
                    # A service may have stopped between live flush and raw
                    # finalization. Reload the manifest including newly
                    # registered recovery journals before preparing delivery.
                    from aura.audio.recording_session import RecordingSession
                    manifest = json.loads((directory / 'session.json').read_text())
                    core.recordings[sid] = RecordingSession(directory, manifest)
                s['enhancement'].update(recovery_scanning=False, recovery_scanned_samples=total,
                    recovery_progress=dict(completed_samples=total, total_samples=total))
                resolve_scanned_gaps(s)
                core._save(s)
                core.changed.notify_all()
        except Exception as exc:
            with core.changed:
                if not core.shutdown:
                    s = core._get(sid)
                    s['enhancement']['recovery_scanning'] = False
                    s.update(state='failed', error=f'Enhancement recovery failed: {exc}')
                    core._save(s)
        finally:
            if self.worker:
                self.worker.close()
                self.worker = None
