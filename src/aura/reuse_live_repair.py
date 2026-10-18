"""One bounded, preemptible live enhancement repair worker per service.

Only newly detected guarded-session gaps are eligible. Historical gaps never
start work merely because a service restarts. Original capture remains durable
and independent of this consumer.
"""
import json
import os
import threading
import uuid

from aura.reuse_recovery import enhance_source, uncovered_intervals, usable_enhancement


class LiveRepair:
    def __init__(self, core):
        self.core = core
        self.active_session = None
        self.worker = None
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._run, name='aura-live-repair', daemon=True)
        self.paused = False

    def start(self):
        self.thread.start()

    def close(self):
        self.closed.set()
        with self.core.changed:
            self.core.changed.notify_all()
        if self.worker:
            self.worker.close()
        self.thread.join(timeout=10)
        if self.thread.is_alive():
            raise RuntimeError('Live repair did not stop; source remains retained')

    def _checkpoint(self):
        core = self.core
        with core.changed:
            while True:
                s = core.sessions.get(self.active_session)
                if self.closed.is_set() or core.shutdown or not s or s['state'] != 'recording':
                    raise InterruptedError('Live repair stopped; pending source retained')
                backlog = max(0, s['samples'] - s['enhancement'].get('input_samples', 0))
                if backlog > 16000:
                    self.paused = True
                elif backlog <= 8000:
                    self.paused = False
                if not self.paused:
                    return
                core.changed.wait(.1)

    def _select(self):
        core = self.core
        for s in core.sessions.values():
            enhancement = s.get('enhancement', {})
            if s['state'] != 'recording' or enhancement.get('policy') != 'speech-guard-v1':
                continue
            for gap in enhancement.get('gaps', []):
                if gap.get('live_repair') == 'queued':
                    gap['live_repair'] = 'running'
                    self.active_session = s['id']
                    core._save(s, progress=True)
                    return s, gap
        return None

    def _run(self):
        core = self.core
        while not self.closed.is_set():
            with core.changed:
                if core.shutdown:
                    return
                selected = self._select()
                if not selected:
                    core.changed.wait(.1)
                    continue
            s, parent = selected
            try:
                self._repair(s, parent)
            except Exception as exc:
                with core.changed:
                    parent['live_repair'] = 'pending'
                    parent['repair_error'] = str(exc)[:1000]
                    core._save(s, progress=True)
            finally:
                try:
                    if self.worker:
                        self.worker.close()
                finally:
                    self.worker = None
                    with core.changed:
                        self.active_session = None
                        self.paused = False
                        core.changed.notify_all()

    def _repair(self, s, parent):
        from aura.audio.reuse import ReuseWorker
        from aura.audio.recording_session import write_session_manifest
        core, sid = self.core, s['id']
        directory = core.directory(sid)
        source_path = directory / '.capture/mixed.pcm'
        output_path = directory / '.capture' / f'live-repair-{uuid.uuid4().hex}.pcm'
        with core.changed:
            payloads = [json.loads(r[0]) for r in core.db.execute(
                "SELECT payload FROM jobs WHERE session=? AND kind='chunk'", (sid,))]
            covered = [(p['start'], p['end']) for p in payloads]
            left, right = parent['start_sample'], parent['repair_end_sample']
            parent['review_required_ranges'] = [[max(left, a), min(right, b)]
                for a, b in covered if a < right and b > left]
            ranges = list(uncovered_intervals(right, covered, left))
            parent['repair_ranges'] = [list(r) for r in ranges]
            rec = core.recordings.get(sid)
            manifest = rec.manifest if rec else json.loads((directory / 'session.json').read_text())
            manifest.setdefault('audio_cleanup_pending', []).append(str(output_path.relative_to(directory)))
            write_session_manifest(directory / 'session.json', manifest)
            core._save(s, progress=True)
        maximum = int(s['options'].get('live_max_segment_len_sec', 12) * 16000)
        with source_path.open('rb') as source, output_path.open('wb') as output:
            for left, right in ranges:
                for start in range(left, right, maximum):
                    self._checkpoint()
                    end = min(right, start + maximum)
                    gap = dict(id=f'live-repair-{start}-{end}', reason='live_repair', status='pending',
                               start_sample=start, end_sample=end, attempts=0, parent_id=parent['id'])
                    with core.changed:
                        s['enhancement']['gaps'].append(gap)
                        core._save(s, progress=True)
                    accepted = False
                    for context in dict.fromkeys((max(0, start - 32000), start)):
                        self._checkpoint()
                        with core.changed:
                            gap['attempts'] += 1
                            core._save(s, progress=True)
                        if self.worker is None:
                            factory = core.enhancement_worker_factory or ReuseWorker
                            self.worker = factory('live', live_policy='speech-guard-v1',
                                                  log_path=directory / 'reuse-live-repair.log')
                        else:
                            self.worker.reset(new_interval=True)
                        source.seek(context * 2)
                        audio = source.read((end - context) * 2)
                        if len(audio) != (end - context) * 2:
                            raise RuntimeError('Live repair source range is incomplete')
                        enhanced = enhance_source(self.worker, audio, 'speech-guard-v1', self._checkpoint)
                        if len(enhanced) != len(audio):
                            raise RuntimeError('Live repair changed the source sample count')
                        if usable_enhancement(audio, enhanced, start - context):
                            accepted = True
                            break
                    if not accepted:
                        with core.changed:
                            gap['error'] = 'Fresh RE-USE output remains unusable; original retained'
                            core._save(s, progress=True)
                        continue
                    enhanced = enhanced[(start - context) * 2:]
                    output.seek(start * 2)
                    output.write(enhanced)
                    output.flush()
                    os.fsync(output.fileno())
                    with core.changed:
                        self._checkpoint()
                        # Reservations exclude this range from the primary
                        # consumer while repair runs. Recheck after inference.
                        covered_now = [(p['start'], p['end']) for p in
                            (json.loads(r[0]) for r in core.db.execute(
                                "SELECT payload FROM jobs WHERE session=? AND kind='chunk'", (sid,)))]
                        if list(uncovered_intervals(end, covered_now, start)) != [(start, end)]:
                            gap['error'] = 'Source range already submitted; review retained interval'
                            continue
                        core._job(s, 'chunk', path=str(output_path), start=start, end=end, terminal=True,
                                  split_reason='live_enhancement_repair', enhancement_gap_id=gap['id'])
                        gap['submitted'] = True
                        core._save(s, progress=True)
        with core.changed:
            parent['live_repair'] = 'finished'
            resolve_live_gaps(s)
            core._save(s, progress=True)


def resolve_live_gaps(session):
    gaps = session.get('enhancement', {}).get('gaps', [])
    for parent in gaps:
        if (parent.get('live_repair') != 'finished' or not parent.get('closed')
                or parent.get('review_required_ranges')):
            continue
        children = [g for g in gaps if g.get('parent_id') == parent['id']]
        if children and all(g['status'] == 'resolved' for g in children):
            parent['status'] = 'resolved'
            parent['resolution'] = 'Missing live intervals enhanced and ASR jobs completed'
