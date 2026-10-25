"""Session-owned streaming coordination, independent from the ASR queue."""
import json
from pathlib import Path

from aura.diarization.nemotron import MODEL_ID, NemotronWorker
from aura.diarization.speaker_assignment import SpeakerTurn, TranscriptSegment, speaker_for_segment


def label_segments(segments, turns, processed_sample, finalized=None):
    finalized = finalized if finalized is not None else set()
    changed = False
    for segment in segments:
        if segment['segment_id'] in finalized or segment.get('state') == 'confirmed' or segment['end_ms'] * 16 > processed_sample:
            continue
        finalized.add(segment['segment_id'])
        target = TranscriptSegment(segment['start_ms'] / 1000, segment['end_ms'] / 1000, segment['text'])
        speaker = speaker_for_segment(target, turns)
        flags = set(segment.get('review_flags', ())) - {'unknown_speaker', 'speaker_overlap'}
        if speaker == 'SPEAKER_UNKNOWN':
            flags.add('unknown_speaker')
        if len({t.speaker for t in turns if t.start < target.end and t.end > target.start}) > 1:
            flags.add('speaker_overlap')
        flags = sorted(flags)
        if speaker != segment.get('speaker') or flags != list(segment.get('review_flags', ())):
            segment.update(speaker=speaker, review_flags=flags, revision=segment.get('revision', 0) + 1)
            changed = True
    return changed


class LiveDiarization:
    def __init__(self, directory, source, *, media=False, worker_factory=NemotronWorker):
        self.worker = worker_factory(Path(directory) / '.runtime')
        try:
            self.worker.request('reset', path=str(source), media=media)
        except BaseException:
            self.worker.close()
            raise
        self.turns = []
        self.finalized = set()
        self.sequence = 0
        self.output = Path(directory) / 'diarization.jsonl'
        # Recovery keeps the earlier receipt instead of silently replacing it.
        if self.output.exists():
            import uuid
            self.output.rename(self.output.with_name(f'diarization-{uuid.uuid4().hex}.jsonl'))
        self.journal = self.output.open('w', encoding='utf-8')
        self.media = media
        self.source = Path(source)
        self.status = dict(state='ready', model_id=MODEL_ID, runtime=self.worker.receipt,
                           processed_sample=0, sequence=0, active=[], error=None)

    def advance(self, available, final):
        event = self.worker.request('advance', available=available, final=final)
        if event.get('waiting'):
            return None
        self.sequence += 1
        self.turns.extend(SpeakerTurn(**t) for t in event['turns'])
        event['sequence'] = self.sequence
        self.journal.write(json.dumps(event) + '\n')
        self.journal.flush()
        self.status.update(state='completed' if event['done'] else 'running',
            sequence=self.sequence, active=[] if event['done'] else event['active'],
            processed_sample=event['processed_sample'], error=None)
        return event

    def close(self):
        self.worker.close()
        self.journal.close()


def status_text(status):
    if not status:
        return 'Nemotron · awaiting session'
    state = status.get('state', 'unknown')
    if state == 'failed':
        return 'Diarization failed · ' + status.get('error', '')
    lag = status.get('lag_seconds', 0)
    activity = ', '.join(status.get('active', [])) or 'silence'
    if lag > 3:
        return f'Diarization catching up · {lag:.1f}s behind'
    return f'Nemotron · {state} · {activity}'
