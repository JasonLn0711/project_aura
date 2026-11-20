"""Content-free streaming diagnostics; source positions are never word accuracy."""
import json
import time
from contextlib import contextmanager


class StageTimings:
    def __init__(self):
        self.values = {}

    @contextmanager
    def measure(self, stage):
        start = time.perf_counter()
        try:
            yield
        finally:
            value = self.values.setdefault(stage, dict(calls=0, seconds=0.0, max_seconds=0.0))
            elapsed = time.perf_counter() - start
            value['calls'] += 1
            value['seconds'] += elapsed
            value['max_seconds'] = max(value['max_seconds'], elapsed)

    @contextmanager
    def locked(self, lock):
        with self.measure('core_lock_wait'):
            lock.acquire()
        try:
            with self.measure('core_lock_held'):
                yield
        finally:
            lock.release()


def streaming_status(session):
    enhancement = session.get('enhancement', {})
    processed = enhancement.get('processed_samples')
    pending = sum(g.get('status') == 'pending' for g in enhancement.get('gaps', []))
    pending += sum(g.get('status') == 'pending' for g in session.get('asr_issues', []))
    repair = enhancement.get('live_repair_work', {})
    return dict(version=1,
        captured_samples=session.get('samples'),
        durable_source_samples=session.get('stream', {}).get('durable_sequence', session.get('input_sequence', 0)) * 480,
        enhanced_samples=processed, durable_enhanced_samples=enhancement.get('durable_samples'),
        enhancement_lag_seconds=None if processed is None else max(0, session.get('samples', 0) - processed) / 16000,
        pending_intervals=pending,
        transcript_status='pending_review' if pending else ('settled' if session.get('state') == 'ready' else 'in_progress'),
        audio_ready=bool(session.get('artifacts', {}).get('m4a')),
        waiting_reason=('primary_backlog' if repair.get('paused') else
                        'stopped_with_pending_gaps' if pending and session.get('state') == 'ready' else None),
        last_progress_at=enhancement.get('last_progress_at'))


class TraceWriter:
    def __init__(self, path):
        self.path = path
        self.last = 0.0

    def write(self, session, timings, *, force=False):
        now = time.monotonic()
        if not force and now - self.last < 1:
            return
        self.last = now
        row = dict(monotonic=now, event='streaming.progress', session_id=session['id'],
                   generation=session.get('enhancement', {}).get('generation'),
                   state=session['state'], status=streaming_status(session), stages=timings.values)
        with self.path.open('a', encoding='utf-8') as output:
            output.write(json.dumps(row) + '\n')
